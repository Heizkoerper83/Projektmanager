"""Core logic for the local project management tool.

This module owns the SQLite schema, migrations, CRUD helpers, filters,
notes/history, templates, recurring tasks, and backup import/export.
"""

from __future__ import annotations

import csv
import contextvars
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from pmtool.core.models import ProjectInput, RiskData, TaskInput
from pmtool.paths import get_db_path
from pmtool.reports.weekly import build_weekly_project_report_markdown, generate_weekly_project_report


DB_PATH = get_db_path()

TASK_STATUS_LABELS = {
    "open": "offen",
    "in_progress": "in Arbeit",
    "blocked": "blockiert",
    "done": "erledigt",
}

PROJECT_STATUS_LABELS = {
    "active": "aktiv",
    "paused": "pausiert",
    "done": "abgeschlossen",
}

ENERGY_LEVELS = {
    "low": "niedrig",
    "medium": "mittel",
    "high": "hoch",
}

STATUS_ALIASES = {
    "offen": "open",
    "open": "open",
    "todo": "open",
    "in_bearbeitung": "in_progress",
    "inarbeit": "in_progress",
    "in_progress": "in_progress",
    "doing": "in_progress",
    "blockiert": "blocked",
    "blocked": "blocked",
    "done": "done",
    "erledigt": "done",
}

PROJECT_STATUS_ALIASES = {
    "aktiv": "active",
    "active": "active",
    "pausiert": "paused",
    "paused": "paused",
    "abgeschlossen": "done",
    "done": "done",
}

ENERGY_ALIASES = {
    "low": "low",
    "niedrig": "low",
    "medium": "medium",
    "mittel": "medium",
    "high": "high",
    "hoch": "high",
}

TASK_STATUS_CHOICES = ["open", "in_progress", "blocked", "done", "offen", "in_bearbeitung", "blockiert", "erledigt"]
PROJECT_STATUS_CHOICES = ["active", "paused", "done", "aktiv", "pausiert", "abgeschlossen"]
ENERGY_LEVEL_CHOICES = ["low", "medium", "high", "niedrig", "mittel", "hoch"]
DUE_FILTER_CHOICES = ["today", "week", "overdue", "blocked"]


TABLES = [
    "project_shares",
    "task_history",
    "task_notes",
    "task_templates",
    "project_milestones",
    "tasks",
    "projects",
]

_CURRENT_PRINCIPAL: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "pmtool_current_principal",
    default=None,
)


def set_current_principal(principal: dict[str, Any] | None) -> None:
    if principal is None:
        _CURRENT_PRINCIPAL.set(None)
        return
    name = str(principal.get("name", "")).strip().lower()
    role = str(principal.get("role", "reader")).strip().lower() or "reader"
    if not name:
        _CURRENT_PRINCIPAL.set(None)
        return
    _CURRENT_PRINCIPAL.set({"name": name, "role": role})


def clear_current_principal() -> None:
    _CURRENT_PRINCIPAL.set(None)


def current_principal() -> dict[str, Any] | None:
    return _CURRENT_PRINCIPAL.get()


def _current_account_name() -> str | None:
    principal = current_principal()
    if not principal:
        return None
    name = str(principal.get("name", "")).strip().lower()
    return name or None


def _current_role() -> str:
    principal = current_principal()
    if not principal:
        return "editor"
    return str(principal.get("role", "reader")).strip().lower() or "reader"


def _require_editor_role() -> None:
    role = _current_role()
    if role not in ("editor", "admin"):
        raise ValueError("Account hat nur Lesezugriff")


def _project_access_clause(project_alias: str = "p") -> tuple[str, list[object]]:
    account = _current_account_name()
    if not account:
        return "", []
    return (
        f"AND ({project_alias}.owner_account = '' OR LOWER({project_alias}.owner_account) = ? OR EXISTS ("
        "SELECT 1 FROM project_shares ps "
        f"WHERE ps.project_id = {project_alias}.id AND LOWER(ps.account_name) = ?"
        "))",
        [account, account],
    )


def _task_access_clause(task_alias: str = "t", project_alias: str = "p") -> tuple[str, list[object]]:
    account = _current_account_name()
    if not account:
        return "", []
    return (
        f"AND ({task_alias}.project_id IS NOT NULL AND ({project_alias}.owner_account = '' OR LOWER({project_alias}.owner_account) = ? OR EXISTS ("
        "SELECT 1 FROM project_shares ps "
        f"WHERE ps.project_id = {project_alias}.id AND LOWER(ps.account_name) = ?"
        ")))",
        [account, account],
    )


def _project_exists(conn: sqlite3.Connection, project_id: int) -> bool:
    return conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is not None


def _has_project_access(conn: sqlite3.Connection, project_id: int) -> bool:
    account = _current_account_name()
    if not account:
        return _project_exists(conn, project_id)
    row = conn.execute(
        """
        SELECT 1
        FROM projects p
        WHERE p.id = ?
          AND (
                p.owner_account = ''
                OR LOWER(p.owner_account) = ?
                OR EXISTS (
                    SELECT 1
                    FROM project_shares ps
                    WHERE ps.project_id = p.id AND LOWER(ps.account_name) = ?
                )
          )
        """,
        (project_id, account, account),
    ).fetchone()
    return row is not None


def _has_project_write_access(conn: sqlite3.Connection, project_id: int) -> bool:
    if _current_role() not in ("editor", "admin"):
        return False
    return _has_project_access(conn, project_id)


def _is_project_owner(conn: sqlite3.Connection, project_id: int) -> bool:
    account = _current_account_name()
    if not account:
        return True
    row = conn.execute("SELECT owner_account FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return False
    owner = str(row["owner_account"] or "").strip().lower()
    if not owner:
        return True
    return owner == account


def _ensure_project_read_access(project_id: int) -> None:
    with get_connection() as conn:
        if not _project_exists(conn, project_id):
            raise ValueError(f"Projekt {project_id} existiert nicht.")
        if not _has_project_access(conn, project_id):
            raise ValueError(f"Kein Zugriff auf Projekt {project_id}.")


def _ensure_project_write_access(project_id: int) -> None:
    _require_editor_role()
    with get_connection() as conn:
        if not _project_exists(conn, project_id):
            raise ValueError(f"Projekt {project_id} existiert nicht.")
        if not _has_project_write_access(conn, project_id):
            raise ValueError(f"Kein Schreibzugriff auf Projekt {project_id}.")


def _ensure_project_owner_access(project_id: int) -> None:
    _require_editor_role()
    with get_connection() as conn:
        if not _project_exists(conn, project_id):
            raise ValueError(f"Projekt {project_id} existiert nicht.")
        if not _is_project_owner(conn, project_id):
            raise ValueError("Nur der Projektinhaber darf Freigaben ändern")


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today_text() -> str:
    return date.today().isoformat()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> bool:
    if column_name not in table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
        return True
    return False


def normalize_task_status(value: str) -> str:
    try:
        return STATUS_ALIASES[value.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"Unbekannter Aufgabenstatus: {value}") from exc


def normalize_project_status(value: str) -> str:
    try:
        return PROJECT_STATUS_ALIASES[value.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"Unbekannter Projektstatus: {value}") from exc


def normalize_energy_level(value: str) -> str:
    try:
        return ENERGY_ALIASES[value.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"Unbekanntes Energieniveau: {value}") from exc


def parse_due_date(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("Fälligkeitsdatum muss im Format YYYY-MM-DD sein.") from exc


def parse_int_or_none(value: str | int | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Wert muss eine ganze Zahl sein.") from exc


def normalize_risk_weight(value: int | str | None) -> int:
    if value in (None, ""):
        return 3
    try:
        weight = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Risiko-Gewichtung muss eine Zahl zwischen 1 und 5 sein.") from exc
    if weight < 1 or weight > 5:
        raise ValueError("Risiko-Gewichtung muss zwischen 1 und 5 liegen.")
    return weight


def normalize_risk_level(value: int | str | None) -> int:
    return normalize_risk_weight(value)


def normalize_risk_rows(
    rows: Sequence[dict[str, Any]] | None,
    *,
    fallback_risk: str = "",
    fallback_countermeasure: str = "",
    fallback_probability: int = 3,
    fallback_impact: int = 3,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows or []:
        risk_text = str(row.get("risk", "")).strip()
        if not risk_text:
            continue
        probability = normalize_risk_level(row.get("probability", fallback_probability))
        impact = normalize_risk_level(row.get("impact", fallback_impact))
        countermeasure = str(row.get("countermeasure", "")).strip()
        normalized.append(
            {
                "risk": risk_text,
                "probability": probability,
                "impact": impact,
                "countermeasure": countermeasure,
            }
        )

    if normalized:
        return normalized

    fallback_risk_text = str(fallback_risk).strip()
    if not fallback_risk_text:
        return []
    return [
        {
            "risk": fallback_risk_text,
            "probability": normalize_risk_level(fallback_probability),
            "impact": normalize_risk_level(fallback_impact),
            "countermeasure": str(fallback_countermeasure).strip(),
        }
    ]


def risk_rows_to_json(rows: Sequence[dict[str, Any]] | None) -> str:
    return json.dumps(normalize_risk_rows(rows), ensure_ascii=False)


def risk_rows_from_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    safe_rows: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        risk_text = str(item.get("risk", "")).strip()
        if not risk_text:
            continue
        safe_rows.append(
            {
                "risk": risk_text,
                "probability": normalize_risk_level(item.get("probability", 3)),
                "impact": normalize_risk_level(item.get("impact", 3)),
                "countermeasure": str(item.get("countermeasure", "")).strip(),
            }
        )
    return safe_rows


def normalize_tags(tags: str | Iterable[str] | None) -> str:
    if tags is None:
        return ""
    if isinstance(tags, str):
        raw_tags = tags.replace(";", ",").split(",")
    else:
        raw_tags = list(tags)
    cleaned = []
    seen = set()
    for raw_tag in raw_tags:
        tag = str(raw_tag).strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        cleaned.append(tag)
    return ",".join(cleaned)


def tags_as_list(tags: str | None) -> list[str]:
    if not tags:
        return []
    return [tag for tag in (part.strip() for part in tags.split(",")) if tag]


def tags_match_clause(tag: str) -> tuple[str, list[str]]:
    normalized = tag.strip().lower()
    if not normalized:
        return "", []
    return "AND (',' || LOWER(t.tags) || ',') LIKE ?", [f"%,{normalized},%"]


def project_label(status: str) -> str:
    return PROJECT_STATUS_LABELS.get(status, status)


def task_label(status: str) -> str:
    return TASK_STATUS_LABELS.get(status, status)


def energy_label(value: str) -> str:
    return ENERGY_LEVELS.get(value, value)


def format_date(value: str | None) -> str:
    return value if value else "-"


def ensure_project_exists(project_id: int | None) -> None:
    if project_id is None:
        return
    _ensure_project_read_access(project_id)


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                owner_account TEXT NOT NULL DEFAULT '',
                team TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                goal TEXT NOT NULL DEFAULT '',
                milestone TEXT NOT NULL DEFAULT '',
                risk TEXT NOT NULL DEFAULT '',
                risk_rows_json TEXT NOT NULL DEFAULT '[]',
                risk_probability INTEGER NOT NULL DEFAULT 3,
                risk_impact INTEGER NOT NULL DEFAULT 3,
                risk_weight INTEGER NOT NULL DEFAULT 3,
                risk_countermeasure TEXT NOT NULL DEFAULT '',
                next_review_date TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                account_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(project_id, account_name),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                title TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                priority INTEGER NOT NULL DEFAULT 3,
                due_date TEXT,
                blocked_reason TEXT NOT NULL DEFAULT '',
                risk TEXT NOT NULL DEFAULT '',
                risk_rows_json TEXT NOT NULL DEFAULT '[]',
                risk_probability INTEGER NOT NULL DEFAULT 3,
                risk_impact INTEGER NOT NULL DEFAULT 3,
                risk_weight INTEGER NOT NULL DEFAULT 3,
                risk_countermeasure TEXT NOT NULL DEFAULT '',
                context TEXT NOT NULL DEFAULT '',
                energy_level TEXT NOT NULL DEFAULT 'medium',
                estimate_minutes INTEGER NOT NULL DEFAULT 0,
                tags TEXT NOT NULL DEFAULT '',
                recurrence_days INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                project_id INTEGER,
                title TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                priority INTEGER NOT NULL DEFAULT 3,
                due_offset_days INTEGER,
                context TEXT NOT NULL DEFAULT '',
                energy_level TEXT NOT NULL DEFAULT 'medium',
                tags TEXT NOT NULL DEFAULT '',
                recurrence_days INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
            )
            """
        )

        # Legacy migrations.
        project_risk_probability_added = ensure_column(conn, "projects", "risk_probability", "INTEGER NOT NULL DEFAULT 3")
        project_risk_impact_added = ensure_column(conn, "projects", "risk_impact", "INTEGER NOT NULL DEFAULT 3")
        task_risk_probability_added = ensure_column(conn, "tasks", "risk_probability", "INTEGER NOT NULL DEFAULT 3")
        task_risk_impact_added = ensure_column(conn, "tasks", "risk_impact", "INTEGER NOT NULL DEFAULT 3")
        ensure_column(conn, "projects", "goal", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "projects", "milestone", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "projects", "owner_account", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "projects", "team", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "projects", "risk", "TEXT NOT NULL DEFAULT ''")
        project_risk_rows_json_added = ensure_column(conn, "projects", "risk_rows_json", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(conn, "projects", "risk_weight", "INTEGER NOT NULL DEFAULT 3")
        ensure_column(conn, "projects", "risk_countermeasure", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "projects", "next_review_date", "TEXT")
        ensure_column(conn, "tasks", "context", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "tasks", "risk", "TEXT NOT NULL DEFAULT ''")
        task_risk_rows_json_added = ensure_column(conn, "tasks", "risk_rows_json", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(conn, "tasks", "risk_weight", "INTEGER NOT NULL DEFAULT 3")
        ensure_column(conn, "tasks", "risk_countermeasure", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "tasks", "energy_level", "TEXT NOT NULL DEFAULT 'medium'")
        ensure_column(conn, "tasks", "estimate_minutes", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "tasks", "tags", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "tasks", "recurrence_days", "INTEGER")
        ensure_column(conn, "tasks", "project_id", "INTEGER")
        ensure_column(conn, "tasks", "details", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "tasks", "priority", "INTEGER NOT NULL DEFAULT 3")
        ensure_column(conn, "tasks", "due_date", "TEXT")
        ensure_column(conn, "tasks", "blocked_reason", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "tasks", "updated_at", "TEXT")
        ensure_column(conn, "tasks", "completed_at", "TEXT")

        if project_risk_probability_added or project_risk_impact_added:
            conn.execute(
                "UPDATE projects SET risk_probability = COALESCE(risk_weight, 3), risk_impact = COALESCE(risk_weight, 3)"
            )
        if task_risk_probability_added or task_risk_impact_added:
            conn.execute(
                "UPDATE tasks SET risk_probability = COALESCE(risk_weight, 3), risk_impact = COALESCE(risk_weight, 3)"
            )

        if project_risk_rows_json_added:
            project_rows = conn.execute(
                "SELECT id, risk, risk_probability, risk_impact, risk_countermeasure FROM projects"
            ).fetchall()
            for row in project_rows:
                rows = normalize_risk_rows(
                    None,
                    fallback_risk=row["risk"],
                    fallback_countermeasure=row["risk_countermeasure"],
                    fallback_probability=row["risk_probability"],
                    fallback_impact=row["risk_impact"],
                )
                conn.execute("UPDATE projects SET risk_rows_json = ? WHERE id = ?", (risk_rows_to_json(rows), row["id"]))

        if task_risk_rows_json_added:
            task_rows = conn.execute(
                "SELECT id, risk, risk_probability, risk_impact, risk_countermeasure FROM tasks"
            ).fetchall()
            for row in task_rows:
                rows = normalize_risk_rows(
                    None,
                    fallback_risk=row["risk"],
                    fallback_countermeasure=row["risk_countermeasure"],
                    fallback_probability=row["risk_probability"],
                    fallback_impact=row["risk_impact"],
                )
                conn.execute("UPDATE tasks SET risk_rows_json = ? WHERE id = ?", (risk_rows_to_json(rows), row["id"]))

        if "offen" in task_status_values(conn):
            conn.execute("UPDATE tasks SET status = 'open' WHERE status = 'offen'")
        if "erledigt" in task_status_values(conn):
            conn.execute("UPDATE tasks SET status = 'done' WHERE status = 'erledigt'")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_shares_project_id ON project_shares(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_shares_account_name ON project_shares(account_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_notes_task_id ON task_notes(task_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_history_task_id ON task_history(task_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_milestones_project_id ON project_milestones(project_id)")
        conn.commit()


def task_status_values(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT DISTINCT status FROM tasks").fetchall()
    return {row[0] for row in rows}


def project_fields() -> str:
    return (
        "p.id, p.name, p.owner_account, p.team, p.description, p.goal, p.milestone, p.risk, p.risk_rows_json, p.risk_probability, p.risk_impact, p.risk_weight, p.risk_countermeasure, "
        "p.next_review_date, p.status, p.created_at, p.updated_at"
    )


def task_fields() -> str:
    return (
        "t.id, t.project_id, p.name AS project_name, t.title, t.details, t.status, t.priority, "
        "t.due_date, t.blocked_reason, t.risk, t.risk_rows_json, t.risk_probability, t.risk_impact, t.risk_weight, t.risk_countermeasure, t.context, "
        "t.energy_level, t.estimate_minutes, t.tags, "
        "t.recurrence_days, t.created_at, t.updated_at, t.completed_at"
    )


def record_task_history(task_id: int, action: str, details: str = "") -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO task_history (task_id, action, details, created_at) VALUES (?, ?, ?, ?)",
            (task_id, action, details, now_text()),
        )
        conn.commit()


def add_task_note(task_id: int, note: str) -> None:
    if not note.strip():
        raise ValueError("Die Notiz darf nicht leer sein.")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO task_notes (task_id, note, created_at) VALUES (?, ?, ?)",
            (task_id, note.strip(), now_text()),
        )
        conn.commit()
    record_task_history(task_id, "note", note.strip())


def add_project(
    name: str,
    description: str = "",
    status: str = "active",
    team: str = "",
    goal: str = "",
    milestone: str = "",
    risk: str = "",
    risk_rows: Sequence[dict[str, Any]] | None = None,
    risk_probability: int = 3,
    risk_impact: int = 3,
    risk_weight: int | None = None,
    risk_countermeasure: str = "",
    next_review_date: str | None = None,
) -> None:
    """Create a new project. (Deprecated: Use add_project_from_input instead)
    
    This function maintains backward compatibility. Consider using
    add_project_from_input(ProjectInput(...)) for cleaner code.
    """
    risk_data = RiskData(
        description=risk,
        rows=risk_rows,
        probability=risk_probability,
        impact=risk_impact,
        weight=risk_weight,
        countermeasure=risk_countermeasure,
    )
    
    project_input = ProjectInput(
        name=name,
        description=description,
        status=status,
        team=team,
        goal=goal,
        milestone=milestone,
        risk=risk_data,
        next_review_date=next_review_date,
    )
    
    add_project_from_input(project_input)


def add_project_from_input(project_input: ProjectInput) -> None:
    """Create a new project from ProjectInput data structure.
    
    Preferred method for creating projects. Provides cleaner API than add_project().
    
    Args:
        project_input: ProjectInput dataclass with all project data
        
    Raises:
        ValueError: If project data is invalid or duplicate name
    """
    init_db()
    _require_editor_role()
    
    normalized_status = normalize_project_status(project_input.status)
    owner_account = _current_account_name() or ""
    timestamp = now_text()
    
    # Ensure risk data is set
    risk_data = project_input.risk or RiskData()
    
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    name, owner_account, team, description, goal, milestone, risk, risk_rows_json, risk_probability, risk_impact, risk_weight,
                    risk_countermeasure, next_review_date, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_input.name,
                    owner_account,
                    project_input.team,
                    project_input.description,
                    project_input.goal,
                    project_input.milestone,
                    risk_data.description,
                    risk_rows_to_json(
                        normalize_risk_rows(
                            risk_data.rows,
                            fallback_risk=risk_data.description,
                            fallback_countermeasure=risk_data.countermeasure,
                            fallback_probability=risk_data.probability,
                            fallback_impact=risk_data.impact,
                        )
                    ),
                    normalize_risk_level(risk_data.probability),
                    normalize_risk_level(risk_data.impact),
                    normalize_risk_weight(risk_data.weight if risk_data.weight is not None else max(normalize_risk_level(risk_data.probability), normalize_risk_level(risk_data.impact))),
                    risk_data.countermeasure,
                    parse_due_date(project_input.next_review_date),
                    normalized_status,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"Projekt '{project_input.name}' existiert bereits.") from exc


def update_project(
    project_id: int,
    *,
    name: str | None = None,
    team: str | None = None,
    description: str | None = None,
    status: str | None = None,
    goal: str | None = None,
    milestone: str | None = None,
    risk: str | None = None,
    risk_rows: Sequence[dict[str, Any]] | None = None,
    risk_probability: int | None = None,
    risk_impact: int | None = None,
    risk_weight: int | None = None,
    risk_countermeasure: str | None = None,
    next_review_date: str | None = None,
) -> None:
    init_db()
    _ensure_project_write_access(project_id)
    updates: list[str] = []
    values: list[object] = []
    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if team is not None:
        updates.append("team = ?")
        values.append(team)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if status is not None:
        updates.append("status = ?")
        values.append(normalize_project_status(status))
    if goal is not None:
        updates.append("goal = ?")
        values.append(goal)
    if milestone is not None:
        updates.append("milestone = ?")
        values.append(milestone)
    if risk is not None:
        updates.append("risk = ?")
        values.append(risk)
    if risk_rows is not None:
        updates.append("risk_rows_json = ?")
        values.append(risk_rows_to_json(risk_rows))
    if risk_probability is not None:
        updates.append("risk_probability = ?")
        values.append(normalize_risk_level(risk_probability))
    if risk_impact is not None:
        updates.append("risk_impact = ?")
        values.append(normalize_risk_level(risk_impact))
    if risk_weight is not None:
        updates.append("risk_weight = ?")
        values.append(normalize_risk_weight(risk_weight))
    if risk_countermeasure is not None:
        updates.append("risk_countermeasure = ?")
        values.append(risk_countermeasure)
    if next_review_date is not None:
        updates.append("next_review_date = ?")
        values.append(parse_due_date(next_review_date))
    if not updates:
        return
    updates.append("updated_at = ?")
    values.append(now_text())
    values.append(project_id)
    with get_connection() as conn:
        result = conn.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    if result.rowcount == 0:
        raise ValueError(f"Projekt {project_id} existiert nicht.")


def delete_project(project_id: int) -> None:
    init_db()
    _ensure_project_write_access(project_id)
    with get_connection() as conn:
        result = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    if result.rowcount == 0:
        raise ValueError(f"Projekt {project_id} existiert nicht.")


def list_projects() -> list[sqlite3.Row]:
    init_db()
    access_clause, access_params = _project_access_clause("p")
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {project_fields()},
                   COUNT(t.id) AS task_count,
                   SUM(CASE WHEN t.status != 'done' THEN 1 ELSE 0 END) AS open_tasks,
                   SUM(CASE WHEN t.status = 'blocked' THEN 1 ELSE 0 END) AS blocked_tasks
            FROM projects p
            LEFT JOIN tasks t ON t.project_id = p.id
            WHERE 1 = 1
            {access_clause}
            GROUP BY p.id
            ORDER BY CASE p.status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END, p.name COLLATE NOCASE
            """
            ,
            access_params,
        ).fetchall()
    return rows


def list_project_shares(project_id: int) -> list[sqlite3.Row]:
    init_db()
    _ensure_project_read_access(project_id)
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, project_id, account_name, created_at FROM project_shares WHERE project_id = ? ORDER BY account_name COLLATE NOCASE",
            (project_id,),
        ).fetchall()


def share_project(project_id: int, account_name: str) -> None:
    init_db()
    _ensure_project_owner_access(project_id)
    target = account_name.strip().lower()
    if not target:
        raise ValueError("Accountname darf nicht leer sein")
    with get_connection() as conn:
        owner_row = conn.execute("SELECT owner_account FROM projects WHERE id = ?", (project_id,)).fetchone()
        if owner_row is None:
            raise ValueError(f"Projekt {project_id} existiert nicht.")
        owner = str(owner_row["owner_account"] or "").strip().lower()
        if owner and owner == target:
            raise ValueError("Projektinhaber ist immer automatisch freigeschaltet")
        conn.execute(
            "INSERT OR IGNORE INTO project_shares (project_id, account_name, created_at) VALUES (?, ?, ?)",
            (project_id, target, now_text()),
        )
        conn.commit()


def unshare_project(project_id: int, account_name: str) -> None:
    init_db()
    _ensure_project_owner_access(project_id)
    target = account_name.strip().lower()
    if not target:
        raise ValueError("Accountname darf nicht leer sein")
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM project_shares WHERE project_id = ? AND LOWER(account_name) = ?",
            (project_id, target),
        )
        conn.commit()


def add_milestone(project_id: int, title: str, due_date: str | None = None, status: str = "open") -> None:
    init_db()
    _ensure_project_write_access(project_id)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO project_milestones (project_id, title, due_date, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, title, parse_due_date(due_date), normalize_task_status(status), now_text(), now_text()),
        )
        conn.commit()


def list_milestones(project_id: int | None = None) -> list[sqlite3.Row]:
    init_db()
    query = [
        "SELECT m.id, m.project_id, p.name AS project_name, m.title, m.due_date, m.status, m.created_at, m.updated_at FROM project_milestones m LEFT JOIN projects p ON p.id = m.project_id WHERE 1 = 1"
    ]
    params: list[object] = []
    access_clause, access_params = _project_access_clause("p")
    if access_clause:
        query.append(access_clause)
        params.extend(access_params)
    if project_id is not None:
        _ensure_project_read_access(project_id)
        query.append("AND m.project_id = ?")
        params.append(project_id)
    query.append("ORDER BY CASE WHEN m.due_date IS NULL THEN 1 ELSE 0 END, m.due_date, m.id")
    with get_connection() as conn:
        return conn.execute(" ".join(query), params).fetchall()


def _task_query_base() -> str:
    return (
        "SELECT "
        + task_fields()
        + " FROM tasks t LEFT JOIN projects p ON p.id = t.project_id WHERE 1 = 1"
    )


def _search_terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9][a-z0-9+#._-]*", query.lower()) if term]


def list_tasks(
    project_id: int | None = None,
    status: str | None = None,
    search: str | None = None,
    due_filter: str | None = None,
    tag: str | None = None,
    context: str | None = None,
    energy_level: str | None = None,
    include_done: bool = True,
) -> list[sqlite3.Row]:
    init_db()
    query = [_task_query_base()]
    params: list[object] = []
    access_clause, access_params = _task_access_clause("t", "p")
    if access_clause:
        query.append(access_clause)
        params.extend(access_params)
    if project_id is not None:
        _ensure_project_read_access(project_id)
        query.append("AND t.project_id = ?")
        params.append(project_id)
    if status is not None:
        query.append("AND t.status = ?")
        params.append(normalize_task_status(status))
    elif not include_done:
        query.append("AND t.status != 'done'")
    if search:
        search_terms = _search_terms(search)
        if search_terms:
            searchable_fields = [
                "LOWER(t.title)",
                "LOWER(t.details)",
                "LOWER(t.blocked_reason)",
                "LOWER(t.context)",
                "LOWER(t.tags)",
                "LOWER(COALESCE(p.name, ''))",
                "LOWER(COALESCE(p.goal, ''))",
            ]
            term_clauses: list[str] = []
            for term in search_terms:
                term_clauses.append("(" + " OR ".join(f"{field} LIKE ?" for field in searchable_fields) + ")")
                params.extend([f"%{term}%"] * len(searchable_fields))
            query.append("AND (" + " AND ".join(term_clauses) + ")")
    if due_filter == "today":
        query.append("AND t.due_date = ?")
        params.append(today_text())
    elif due_filter == "week":
        query.append("AND t.due_date BETWEEN ? AND ?")
        params.extend([today_text(), (date.today() + timedelta(days=7)).isoformat()])
    elif due_filter == "overdue":
        query.append("AND t.due_date IS NOT NULL AND t.due_date < ? AND t.status != 'done'")
        params.append(today_text())
    elif due_filter == "blocked":
        query.append("AND t.status = 'blocked'")
    if tag:
        clause, clause_params = tags_match_clause(tag)
        if clause:
            query.append(clause)
            params.extend(clause_params)
    if context:
        query.append("AND LOWER(t.context) LIKE ?")
        params.append(f"%{context.lower()}%")
    if energy_level:
        query.append("AND t.energy_level = ?")
        params.append(normalize_energy_level(energy_level))
    query.append(
        """
        ORDER BY
            CASE t.status WHEN 'blocked' THEN 0 WHEN 'open' THEN 1 WHEN 'in_progress' THEN 2 WHEN 'done' THEN 3 ELSE 4 END,
            CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END,
            t.due_date ASC,
            t.priority ASC,
            t.id ASC
        """
    )
    with get_connection() as conn:
        return conn.execute("\n".join(query), params).fetchall()


def get_task(task_id: int) -> sqlite3.Row | None:
    init_db()
    access_clause, access_params = _task_access_clause("t", "p")
    with get_connection() as conn:
        return conn.execute(
            f"SELECT {task_fields()} FROM tasks t LEFT JOIN projects p ON p.id = t.project_id WHERE t.id = ? {access_clause}",
            [task_id, *access_params],
        ).fetchone()


def list_next_tasks(limit: int = 10) -> list[sqlite3.Row]:
    return list_tasks(include_done=False)[:limit]


def task_dashboard_counts() -> dict[str, int]:
    today = today_text()
    week_end = (date.today() + timedelta(days=7)).isoformat()
    visible_tasks = [dict(row) for row in list_tasks(include_done=True)]
    return {
        "open": sum(1 for row in visible_tasks if row["status"] == "open"),
        "in_progress": sum(1 for row in visible_tasks if row["status"] == "in_progress"),
        "blocked": sum(1 for row in visible_tasks if row["status"] == "blocked"),
        "done": sum(1 for row in visible_tasks if row["status"] == "done"),
        "today": sum(1 for row in visible_tasks if row["status"] != "done" and row["due_date"] == today),
        "week": sum(
            1
            for row in visible_tasks
            if row["status"] != "done" and row["due_date"] and today <= row["due_date"] <= week_end
        ),
        "overdue": sum(1 for row in visible_tasks if row["status"] != "done" and row["due_date"] and row["due_date"] < today),
    }


def project_dashboard_counts() -> dict[str, int]:
    counts = {"active": 0, "paused": 0, "done": 0}
    for row in list_projects():
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return counts


def build_task_summary() -> dict[str, int]:
    counts = {status: 0 for status in TASK_STATUS_LABELS}
    for row in list_tasks(include_done=True):
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return counts


def list_task_notes(task_id: int) -> list[sqlite3.Row]:
    init_db()
    task = get_task(task_id)
    if task is None:
        return []
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, task_id, note, created_at FROM task_notes WHERE task_id = ? ORDER BY id DESC",
            (task_id,),
        ).fetchall()


def list_task_history(task_id: int) -> list[sqlite3.Row]:
    init_db()
    task = get_task(task_id)
    if task is None:
        return []
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, task_id, action, details, created_at FROM task_history WHERE task_id = ? ORDER BY id DESC",
            (task_id,),
        ).fetchall()


def list_templates() -> list[sqlite3.Row]:
    init_db()
    access_clause, access_params = _project_access_clause("p")
    where_clause = ""
    params: list[object] = []
    if access_clause:
        where_clause = f"AND (tt.project_id IS NOT NULL {access_clause.replace('AND ', 'AND ')})"
        params.extend(access_params)
    with get_connection() as conn:
        return conn.execute(
            "SELECT tt.id, tt.name, tt.project_id, tt.title, tt.details, tt.status, tt.priority, tt.due_offset_days, tt.context, tt.energy_level, tt.tags, tt.recurrence_days, tt.created_at, tt.updated_at FROM task_templates tt LEFT JOIN projects p ON p.id = tt.project_id WHERE 1 = 1 "
            + where_clause
            + " ORDER BY tt.name COLLATE NOCASE",
            params,
        ).fetchall()


def add_template(
    name: str,
    title: str,
    details: str = "",
    project_id: int | None = None,
    status: str = "open",
    priority: int = 3,
    due_offset_days: int | None = None,
    context: str = "",
    energy_level: str = "medium",
    tags: str | Iterable[str] | None = None,
    recurrence_days: int | None = None,
) -> None:
    init_db()
    _require_editor_role()
    if project_id is not None:
        _ensure_project_write_access(project_id)
    elif _current_account_name() is not None:
        raise ValueError("Vorlagen müssen einem Projekt zugeordnet sein")
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO task_templates (
                    name, project_id, title, details, status, priority, due_offset_days,
                    context, energy_level, tags, recurrence_days, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    project_id,
                    title,
                    details,
                    normalize_task_status(status),
                    priority,
                    due_offset_days,
                    context,
                    normalize_energy_level(energy_level),
                    normalize_tags(tags),
                    recurrence_days,
                    now_text(),
                    now_text(),
                ),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"Vorlage '{name}' existiert bereits.") from exc


def update_milestone(
    milestone_id: int,
    *,
    title: str | None = None,
    due_date: str | None = None,
    status: str | None = None,
    project_id: int | None = None,
) -> None:
    init_db()
    _require_editor_role()
    updates: list[str] = []
    values: list[object] = []
    with get_connection() as conn:
        row = conn.execute("SELECT project_id FROM project_milestones WHERE id = ?", (milestone_id,)).fetchone()
    if row is None:
        raise ValueError(f"Meilenstein {milestone_id} existiert nicht.")
    _ensure_project_write_access(int(row["project_id"]))
    if project_id is not None:
        _ensure_project_write_access(project_id)
        updates.append("project_id = ?")
        values.append(project_id)
    if title is not None:
        updates.append("title = ?")
        values.append(title)
    if due_date is not None:
        updates.append("due_date = ?")
        values.append(parse_due_date(due_date))
    if status is not None:
        updates.append("status = ?")
        values.append(normalize_task_status(status))
    if not updates:
        return
    updates.append("updated_at = ?")
    values.append(now_text())
    values.append(milestone_id)
    with get_connection() as conn:
        result = conn.execute(f"UPDATE project_milestones SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    if result.rowcount == 0:
        raise ValueError(f"Meilenstein {milestone_id} existiert nicht.")


def delete_milestone(milestone_id: int) -> None:
    init_db()
    _require_editor_role()
    with get_connection() as conn:
        row = conn.execute("SELECT project_id FROM project_milestones WHERE id = ?", (milestone_id,)).fetchone()
    if row is None:
        raise ValueError(f"Meilenstein {milestone_id} existiert nicht.")
    _ensure_project_write_access(int(row["project_id"]))
    with get_connection() as conn:
        result = conn.execute("DELETE FROM project_milestones WHERE id = ?", (milestone_id,))
        conn.commit()
    if result.rowcount == 0:
        raise ValueError(f"Meilenstein {milestone_id} existiert nicht.")


def create_task_from_template(
    template_id: int,
    *,
    title: str | None = None,
    project_id: int | None = None,
    due_date: str | None = None,
) -> int:
    init_db()
    _require_editor_role()
    with get_connection() as conn:
        template = conn.execute(
            "SELECT * FROM task_templates WHERE id = ?",
            (template_id,),
        ).fetchone()
    if template is None:
        raise ValueError(f"Vorlage {template_id} existiert nicht.")
    if template["project_id"] is not None:
        _ensure_project_write_access(int(template["project_id"]))
    resolved_due_date = due_date
    if resolved_due_date is None and template["due_offset_days"] is not None:
        resolved_due_date = (date.today() + timedelta(days=int(template["due_offset_days"]))).isoformat()
    return add_task(
        title or template["title"],
        project_id=project_id if project_id is not None else template["project_id"],
        details=template["details"],
        status=template["status"],
        priority=template["priority"],
        due_date=resolved_due_date,
        blocked_reason="",
        context=template["context"],
        energy_level=template["energy_level"],
        tags=template["tags"],
        recurrence_days=template["recurrence_days"],
        return_id=True,
    )


def update_template(
    template_id: int,
    *,
    name: str | None = None,
    title: str | None = None,
    details: str | None = None,
    project_id: int | None = None,
    status: str | None = None,
    priority: int | None = None,
    due_offset_days: int | None = None,
    context: str | None = None,
    energy_level: str | None = None,
    tags: str | Iterable[str] | None = None,
    recurrence_days: int | None = None,
) -> None:
    init_db()
    _require_editor_role()
    updates: list[str] = []
    values: list[object] = []
    with get_connection() as conn:
        current = conn.execute("SELECT project_id FROM task_templates WHERE id = ?", (template_id,)).fetchone()
    if current is None:
        raise ValueError(f"Vorlage {template_id} existiert nicht.")
    if current["project_id"] is not None:
        _ensure_project_write_access(int(current["project_id"]))
    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if title is not None:
        updates.append("title = ?")
        values.append(title)
    if details is not None:
        updates.append("details = ?")
        values.append(details)
    if project_id is not None:
        _ensure_project_write_access(project_id)
        updates.append("project_id = ?")
        values.append(project_id)
    if status is not None:
        updates.append("status = ?")
        values.append(normalize_task_status(status))
    if priority is not None:
        updates.append("priority = ?")
        values.append(priority)
    if due_offset_days is not None:
        updates.append("due_offset_days = ?")
        values.append(due_offset_days)
    if context is not None:
        updates.append("context = ?")
        values.append(context)
    if energy_level is not None:
        updates.append("energy_level = ?")
        values.append(normalize_energy_level(energy_level))
    if tags is not None:
        updates.append("tags = ?")
        values.append(normalize_tags(tags))
    if recurrence_days is not None:
        updates.append("recurrence_days = ?")
        values.append(recurrence_days)
    if not updates:
        return
    updates.append("updated_at = ?")
    values.append(now_text())
    values.append(template_id)
    with get_connection() as conn:
        result = conn.execute(f"UPDATE task_templates SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    if result.rowcount == 0:
        raise ValueError(f"Vorlage {template_id} existiert nicht.")


def delete_template(template_id: int) -> None:
    init_db()
    _require_editor_role()
    with get_connection() as conn:
        row = conn.execute("SELECT project_id FROM task_templates WHERE id = ?", (template_id,)).fetchone()
    if row is None:
        raise ValueError(f"Vorlage {template_id} existiert nicht.")
    if row["project_id"] is not None:
        _ensure_project_write_access(int(row["project_id"]))
    with get_connection() as conn:
        result = conn.execute("DELETE FROM task_templates WHERE id = ?", (template_id,))
        conn.commit()
    if result.rowcount == 0:
        raise ValueError(f"Vorlage {template_id} existiert nicht.")


def _spawn_recurring_copy(task: sqlite3.Row) -> None:
    recurrence_days = task["recurrence_days"]
    if not recurrence_days:
        return
    due_date_value = task["due_date"] or today_text()
    next_due_date = (date.fromisoformat(due_date_value) + timedelta(days=int(recurrence_days))).isoformat()
    add_task(
        task["title"],
        project_id=task["project_id"],
        details=task["details"],
        status="open",
        priority=task["priority"],
        due_date=next_due_date,
        blocked_reason="",
        risk=task["risk"],
        risk_rows=risk_rows_from_json(task["risk_rows_json"] if "risk_rows_json" in task.keys() else ""),
        risk_probability=task["risk_probability"],
        risk_impact=task["risk_impact"],
        risk_weight=task["risk_weight"],
        risk_countermeasure=task["risk_countermeasure"],
        context=task["context"],
        energy_level=task["energy_level"],
        tags=task["tags"],
        recurrence_days=task["recurrence_days"],
    )


def _describe_changes(old_row: sqlite3.Row, changes: dict[str, Any]) -> str:
    parts = []
    for key, value in changes.items():
        old_value = old_row[key]
        if old_value != value:
            parts.append(f"{key}: {old_value!r} -> {value!r}")
    return "; ".join(parts)



def add_task(
    title: str,
    project_id: int | None = None,
    details: str = "",
    status: str = "open",
    priority: int = 3,
    due_date: str | None = None,
    blocked_reason: str = "",
    risk: str = "",
    risk_rows: Sequence[dict[str, Any]] | None = None,
    risk_probability: int = 3,
    risk_impact: int = 3,
    risk_weight: int | None = None,
    risk_countermeasure: str = "",
    context: str = "",
    energy_level: str = "medium",
    estimate_minutes: int = 0,
    tags: str | Iterable[str] | None = None,
    recurrence_days: int | None = None,
    return_id: bool = False,
) -> int | None:
    """Create a new task. (Deprecated: Use add_task_from_input instead)
    
    This function maintains backward compatibility. Consider using
    add_task_from_input(TaskInput(...)) for cleaner code.
    """
    risk_data = RiskData(
        description=risk,
        rows=risk_rows,
        probability=risk_probability,
        impact=risk_impact,
        weight=risk_weight,
        countermeasure=risk_countermeasure,
    )
    
    task_input = TaskInput(
        title=title,
        project_id=project_id,
        details=details,
        status=status,
        priority=priority,
        due_date=due_date,
        blocked_reason=blocked_reason,
        risk=risk_data,
        context=context,
        energy_level=energy_level,
        estimate_minutes=estimate_minutes,
        tags=tags,
        recurrence_days=recurrence_days,
    )
    
    return add_task_from_input(task_input, return_id=return_id)


def add_task_from_input(
    task_input: TaskInput,
    return_id: bool = False,
) -> int | None:
    """Create a new task from TaskInput data structure.
    
    Preferred method for creating tasks. Provides cleaner API than add_task().
    
    Args:
        task_input: TaskInput dataclass with all task data
        return_id: Whether to return the created task ID
        
    Returns:
        Task ID if return_id=True, otherwise None
        
    Raises:
        ValueError: If task data is invalid
    """
    init_db()
    _require_editor_role()
    
    # Normalize all inputs
    normalized_status = normalize_task_status(task_input.status)
    normalized_due_date = parse_due_date(task_input.due_date)
    normalized_energy = normalize_energy_level(task_input.energy_level)
    normalized_tags = normalize_tags(task_input.tags)
    
    # Validate
    if task_input.project_id is None and _current_account_name() is not None:
        raise ValueError("Aufgaben müssen einem Projekt zugeordnet sein")
    ensure_project_exists(task_input.project_id)
    if task_input.project_id is not None:
        _ensure_project_write_access(task_input.project_id)
    
    # Ensure risk data is set
    risk_data = task_input.risk or RiskData()
    
    timestamp = now_text()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (
                project_id, title, details, status, priority, due_date, blocked_reason,
                risk, risk_rows_json, risk_probability, risk_impact, risk_weight, risk_countermeasure, context, energy_level, estimate_minutes, tags, recurrence_days,
                created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_input.project_id,
                task_input.title,
                task_input.details,
                normalized_status,
                task_input.priority,
                normalized_due_date,
                task_input.blocked_reason,
                risk_data.description,
                risk_rows_to_json(
                    normalize_risk_rows(
                        risk_data.rows,
                        fallback_risk=risk_data.description,
                        fallback_countermeasure=risk_data.countermeasure,
                        fallback_probability=risk_data.probability,
                        fallback_impact=risk_data.impact,
                    )
                ),
                normalize_risk_level(risk_data.probability),
                normalize_risk_level(risk_data.impact),
                normalize_risk_weight(risk_data.weight if risk_data.weight is not None else max(normalize_risk_level(risk_data.probability), normalize_risk_level(risk_data.impact))),
                risk_data.countermeasure,
                task_input.context,
                normalized_energy,
                task_input.estimate_minutes,
                normalized_tags,
                task_input.recurrence_days,
                timestamp,
                timestamp,
                timestamp if normalized_status == "done" else None,
            ),
        )
        task_id = cursor.lastrowid
        conn.commit()
    record_task_history(task_id, "created", task_input.title)
    if return_id:
        return int(task_id)
    return None




def update_task(
    task_id: int,
    *,
    title: str | None = None,
    details: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    due_date: str | None = None,
    blocked_reason: str | None = None,
    risk: str | None = None,
    risk_rows: Sequence[dict[str, Any]] | None = None,
    risk_probability: int | None = None,
    risk_impact: int | None = None,
    risk_weight: int | None = None,
    risk_countermeasure: str | None = None,
    project_id: int | None = None,
    context: str | None = None,
    energy_level: str | None = None,
    estimate_minutes: int | None = None,
    tags: str | Iterable[str] | None = None,
    recurrence_days: int | None = None,
) -> None:
    init_db()
    _require_editor_role()
    old_task = get_task(task_id)
    if old_task is None:
        raise ValueError(f"Aufgabe {task_id} existiert nicht.")
    if old_task["project_id"] is not None:
        _ensure_project_write_access(int(old_task["project_id"]))
    ensure_project_exists(project_id)
    if project_id is not None:
        _ensure_project_write_access(project_id)
    updates: list[str] = []
    values: list[object] = []

    changed_values: dict[str, Any] = {}

    if title is not None:
        updates.append("title = ?")
        values.append(title)
        changed_values["title"] = title
    if details is not None:
        updates.append("details = ?")
        values.append(details)
        changed_values["details"] = details
    if status is not None:
        normalized_status = normalize_task_status(status)
        updates.append("status = ?")
        values.append(normalized_status)
        changed_values["status"] = normalized_status
        if normalized_status == "done":
            if old_task["status"] != "done":
                updates.append("completed_at = ?")
                values.append(now_text())
        else:
            updates.append("completed_at = NULL")
    if priority is not None:
        updates.append("priority = ?")
        values.append(priority)
        changed_values["priority"] = priority
    if due_date is not None:
        normalized_due_date = parse_due_date(due_date)
        updates.append("due_date = ?")
        values.append(normalized_due_date)
        changed_values["due_date"] = normalized_due_date
    if blocked_reason is not None:
        updates.append("blocked_reason = ?")
        values.append(blocked_reason)
        changed_values["blocked_reason"] = blocked_reason
    if risk is not None:
        updates.append("risk = ?")
        values.append(risk)
        changed_values["risk"] = risk
    if risk_rows is not None:
        normalized_rows = normalize_risk_rows(risk_rows)
        updates.append("risk_rows_json = ?")
        values.append(risk_rows_to_json(normalized_rows))
        changed_values["risk_rows_json"] = risk_rows_to_json(normalized_rows)
    if risk_probability is not None:
        normalized_probability = normalize_risk_level(risk_probability)
        updates.append("risk_probability = ?")
        values.append(normalized_probability)
        changed_values["risk_probability"] = normalized_probability
    if risk_impact is not None:
        normalized_impact = normalize_risk_level(risk_impact)
        updates.append("risk_impact = ?")
        values.append(normalized_impact)
        changed_values["risk_impact"] = normalized_impact
    if risk_weight is not None:
        normalized_weight = normalize_risk_weight(risk_weight)
        updates.append("risk_weight = ?")
        values.append(normalized_weight)
        changed_values["risk_weight"] = normalized_weight
    if risk_countermeasure is not None:
        updates.append("risk_countermeasure = ?")
        values.append(risk_countermeasure)
        changed_values["risk_countermeasure"] = risk_countermeasure
    if project_id is not None:
        updates.append("project_id = ?")
        values.append(project_id)
        changed_values["project_id"] = project_id
    if context is not None:
        updates.append("context = ?")
        values.append(context)
        changed_values["context"] = context
    if energy_level is not None:
        normalized_energy = normalize_energy_level(energy_level)
        updates.append("energy_level = ?")
        values.append(normalized_energy)
        changed_values["energy_level"] = normalized_energy
    if estimate_minutes is not None:
        updates.append("estimate_minutes = ?")
        values.append(estimate_minutes)
        changed_values["estimate_minutes"] = estimate_minutes
    if tags is not None:
        normalized_tags = normalize_tags(tags)
        updates.append("tags = ?")
        values.append(normalized_tags)
        changed_values["tags"] = normalized_tags
    if recurrence_days is not None:
        updates.append("recurrence_days = ?")
        values.append(recurrence_days)
        changed_values["recurrence_days"] = recurrence_days

    if not updates:
        return

    updates.append("updated_at = ?")
    values.append(now_text())
    values.append(task_id)

    with get_connection() as conn:
        result = conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    if result.rowcount == 0:
        raise ValueError(f"Aufgabe {task_id} existiert nicht.")

    details_text = _describe_changes(old_task, changed_values) if changed_values else "updated"
    if details_text:
        record_task_history(task_id, "updated", details_text)

    if status is not None and normalize_task_status(status) == "done" and old_task["status"] != "done":
        record_task_history(task_id, "completed", "Aufgabe abgeschlossen")
        with get_connection() as conn:
            current_task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if current_task and current_task["recurrence_days"]:
            _spawn_recurring_copy(current_task)
            record_task_history(task_id, "recurring", f"N\u00e4chste Aufgabe in {current_task['recurrence_days']} Tagen erstellt")



def complete_task(task_id: int) -> None:
    update_task(task_id, status="done")



def delete_task(task_id: int) -> None:
    init_db()
    _require_editor_role()
    task = get_task(task_id)
    if task is None:
        raise ValueError(f"Aufgabe {task_id} existiert nicht.")
    if task["project_id"] is not None:
        _ensure_project_write_access(int(task["project_id"]))
    with get_connection() as conn:
        result = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    if result.rowcount == 0:
        raise ValueError(f"Aufgabe {task_id} existiert nicht.")


def export_json(output_path: str | Path) -> Path:
    init_db()
    payload = {
        "projects": [dict(row) for row in list_all_rows("projects")],
        "project_shares": [dict(row) for row in list_all_rows("project_shares")],
        "tasks": [dict(row) for row in list_all_rows("tasks")],
        "milestones": [dict(row) for row in list_all_rows("project_milestones")],
        "notes": [dict(row) for row in list_all_rows("task_notes")],
        "history": [dict(row) for row in list_all_rows("task_history")],
        "templates": [dict(row) for row in list_all_rows("task_templates")],
    }
    path = Path(output_path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path



def import_json(input_path: str | Path, replace: bool = True) -> None:
    path = Path(input_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    init_db()
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        if replace:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM sqlite_sequence")
        _import_table_rows(conn, "projects", payload.get("projects", []))
        _import_table_rows(conn, "project_shares", payload.get("project_shares", []))
        _import_table_rows(conn, "task_templates", payload.get("templates", []))
        _import_table_rows(conn, "tasks", payload.get("tasks", []))
        _import_table_rows(conn, "project_milestones", payload.get("milestones", []))
        _import_table_rows(conn, "task_notes", payload.get("notes", []))
        _import_table_rows(conn, "task_history", payload.get("history", []))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()



def export_csv(output_dir: str | Path) -> Path:
    init_db()
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    table_names = ["projects", "project_shares", "tasks", "project_milestones", "task_templates", "task_notes", "task_history"]
    for table_name in table_names:
        rows = list_all_rows(table_name)
        path = base / f"{table_name}.csv"
        if not rows:
            path.write_text("", encoding="utf-8")
            continue
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
    return base



def import_csv(input_dir: str | Path, replace: bool = True) -> None:
    base = Path(input_dir)
    init_db()
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        if replace:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM sqlite_sequence")
        for table_name in ["projects", "project_shares", "task_templates", "tasks", "project_milestones", "task_notes", "task_history"]:
            path = base / f"{table_name}.csv"
            if not path.exists() or path.stat().st_size == 0:
                continue
            with path.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                _import_table_rows(conn, table_name, list(reader))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()



def list_all_rows(table_name: str) -> list[sqlite3.Row]:
    init_db()
    with get_connection() as conn:
        return conn.execute(f"SELECT * FROM {table_name} ORDER BY id").fetchall()



def _import_table_rows(conn: sqlite3.Connection, table_name: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join(["?" for _ in columns])
    column_sql = ", ".join(columns)
    for row in rows:
        values = [None if row[column] in (None, "", "NULL") else row[column] for column in columns]
        conn.execute(f"INSERT OR REPLACE INTO {table_name} ({column_sql}) VALUES ({placeholders})", values)



def generate_project_report(
    project_id: int,
    output_path: str | Path | None = None,
    team: str = "",
    planned_items: str = "",
    achieved_items: str = "",
    status_flags: str = "",
    countermeasures: str = "",
    risks: str = "",
    next_milestone: str = "",
) -> Path:
    """Generate a project report as Markdown file.
    
    Args:
        project_id: Project ID
        output_path: Where to save the .md file (auto-generated if None)
        team: Team members
        planned_items: Planned items
        achieved_items: Achieved items
        status_flags: Project status (e.g., "in_progress, on_track, blocked")
        countermeasures: Countermeasures
        risks: Risks
        next_milestone: Next milestone
        
    Returns:
        Path to generated report file
    """
    init_db()
    
    # Get project
    with get_connection() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    
    if not project:
        raise ValueError(f"Projekt {project_id} existiert nicht.")
    
    project_dict = dict(project)  # Convert Row to dict
    
    # Get project task counts
    tasks = list_tasks(project_id=project_id)
    
    task_counts = {
        "open": sum(1 for t in tasks if t["status"] == "open"),
        "in_progress": sum(1 for t in tasks if t["status"] == "in_progress"),
        "blocked": sum(1 for t in tasks if t["status"] == "blocked"),
        "done": sum(1 for t in tasks if t["status"] == "done"),
    }
    
    # Build Markdown content
    report_md = f"""# Projektbericht: {project_dict["name"]}

**Generiert am:** {today_text()}
**Projekt-ID:** {project_id}

## Projekt\u00fcbersicht

- **Beschreibung:** {project_dict.get("description", "\u2014")}
- **Ziel:** {project_dict.get("goal", "\u2014")}
- **Status:** {PROJECT_STATUS_LABELS.get(project_dict.get("status", ""), "\u2014")}
- **N\u00e4chste Review:** {format_date(project_dict.get("next_review_date"))}

## Statistik

- **Offene Aufgaben:** {task_counts["open"]}
- **In Arbeit:** {task_counts["in_progress"]}
- **Blockiert:** {task_counts["blocked"]}
- **Erledigt:** {task_counts["done"]}

## Projektteam

{team if team else "\u2014"}

## Geplante Inhalte

{planned_items if planned_items else "\u2014"}

## Erreichte Inhalte

{achieved_items if achieved_items else "\u2014"}

## Projektstatus

{status_flags if status_flags else "\u2014"}

## Gegenma\u00dfnahmen

{countermeasures if countermeasures else "\u2014"}

## Risiken

{risks if risks else "\u2014"}

## N\u00e4chster Meilenstein

{next_milestone if next_milestone else "\u2014"}

---

*Erstellt mit Projektmanager*
"""
    
    # Determine output path
    if output_path is None:
        filename = _default_project_report_filename(project_dict["name"])
        output_path = Path(filename)
    else:
        output_path = Path(output_path)
    
    # Write file
    output_path.write_text(report_md, encoding="utf-8")
    return output_path


def generate_weekly_project_report(
    output_path: str | Path | None = None,
    *,
    date_value: str | None = None,
    planned_items: Sequence[str] | None = None,
    achieved_items: Sequence[str] | None = None,
    not_achieved_items: Sequence[str] | None = None,
    status_text: str | None = None,
    delay_measures: Sequence[str] | None = None,
    risks: Sequence[str] | None = None,
    risk_measures: Sequence[str] | None = None,
    project_risks: Sequence[dict[str, str]] | None = None,
    task_risks: Sequence[dict[str, str]] | None = None,
    next_milestone: str | None = None,
    next_milestone_date: str | None = None,
) -> Path:
    """Generate a weekly project report markdown file in a strict template format."""

    report_md = build_weekly_project_report_markdown(
        date_value=date_value,
        planned_items=planned_items,
        achieved_items=achieved_items,
        not_achieved_items=not_achieved_items,
        status_text=status_text,
        delay_measures=delay_measures,
        risks=risks,
        risk_measures=risk_measures,
        project_risks=project_risks,
        task_risks=task_risks,
        next_milestone=next_milestone,
        next_milestone_date=next_milestone_date,
    )

    if output_path is None:
        output_path = Path(f"wochenbericht_{today_text().replace('-', '')}.md")
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_md, encoding="utf-8")
    return output_path


def build_weekly_project_report_markdown(
    *,
    date_value: str | None = None,
    planned_items: Sequence[str] | None = None,
    achieved_items: Sequence[str] | None = None,
    not_achieved_items: Sequence[str] | None = None,
    status_text: str | None = None,
    delay_measures: Sequence[str] | None = None,
    risks: Sequence[str] | None = None,
    risk_measures: Sequence[str] | None = None,
    project_risks: Sequence[dict[str, str]] | None = None,
    task_risks: Sequence[dict[str, str]] | None = None,
    next_milestone: str | None = None,
    next_milestone_date: str | None = None,
) -> str:
    """Build weekly project report markdown using the exact report template."""

    def _pick(values: Sequence[str] | None, index: int, placeholder: str) -> str:
        if not values or index >= len(values):
            return placeholder
        value = (values[index] or "").strip()
        return value if value else placeholder

    def _bullet_lines(values: Sequence[str] | None, placeholder: str) -> str:
        if not values:
            return f"- {placeholder}"
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        if not cleaned:
            return f"- {placeholder}"
        return "\n".join(f"- {value}" for value in cleaned)

    def _risk_table(rows: Sequence[dict[str, str]] | None, placeholder_label: str) -> str:
        header = "| Risiko | Wahrscheinlichkeit | Ausmaß | Gegenmaßnahme |"
        divider = "| --- | --- | --- | --- |"
        if not rows:
            return "\n".join(
                [
                    header,
                    divider,
                    f"| [Platzhalter: {placeholder_label}] | [Platzhalter: Wahrscheinlichkeit] | [Platzhalter: Ausmaß] | [Platzhalter: Gegenmaßnahme] |",
                ]
            )

        normalized_rows = []
        for row in rows:
            risk = str(row.get("risk", "")).strip()
            probability = str(row.get("probability", "")).strip()
            impact = str(row.get("impact", "")).strip()
            countermeasure = str(row.get("countermeasure", "")).strip()
            if not risk:
                continue
            normalized_rows.append(
                (
                    risk,
                    probability or "-",
                    impact or "-",
                    countermeasure or "-",
                )
            )

        if not normalized_rows:
            return "\n".join(
                [
                    header,
                    divider,
                    f"| [Platzhalter: {placeholder_label}] | [Platzhalter: Wahrscheinlichkeit] | [Platzhalter: Ausmaß] | [Platzhalter: Gegenmaßnahme] |",
                ]
            )

        body = "\n".join(f"| {risk} | {probability} | {impact} | {countermeasure} |" for risk, probability, impact, countermeasure in normalized_rows)
        return "\n".join([header, divider, body])

    def _legacy_risk_rows(
        old_risks: Sequence[str] | None,
        old_measures: Sequence[str] | None,
    ) -> list[dict[str, str]]:
        legacy_rows: list[dict[str, str]] = []
        max_len = max(len(old_risks or []), len(old_measures or []))
        for idx in range(max_len):
            risk = ""
            if old_risks and idx < len(old_risks):
                risk = (old_risks[idx] or "").strip()
            if not risk:
                continue
            countermeasure = ""
            if old_measures and idx < len(old_measures):
                countermeasure = (old_measures[idx] or "").strip()
            legacy_rows.append(
                {
                    "risk": risk,
                    "probability": "-",
                    "impact": "-",
                    "countermeasure": countermeasure or "-",
                }
            )
        return legacy_rows

    date_text = (date_value or "").strip() or "[Platzhalter: Datum]"
    planned_lines = _bullet_lines(planned_items, "[Platzhalter: Plan]")
    achieved_lines = _bullet_lines(achieved_items, "[Platzhalter: Ziel]")
    not_achieved_lines = _bullet_lines(not_achieved_items, "[Platzhalter: Nicht erreicht]")
    status_value = (status_text or "").strip() or "[Platzhalter: Im Plan / Im Verzug / Schneller als geplant]"
    delay_1 = _pick(delay_measures, 0, "[Platzhalter: Ma\u00dfnahme 1]")
    delay_2 = _pick(delay_measures, 1, "[Platzhalter: Ma\u00dfnahme 2]")
    project_risk_rows = list(project_risks or [])
    task_risk_rows = list(task_risks or [])
    if not task_risk_rows:
        task_risk_rows = _legacy_risk_rows(risks, risk_measures)
    project_risk_table = _risk_table(project_risk_rows, "Projektrisiko")
    task_risk_table = _risk_table(task_risk_rows, "Aufgabenrisiko")
    milestone_text = (next_milestone or "").strip() or "[Platzhalter: Meilenstein]"
    milestone_date_text = (next_milestone_date or "").strip() or "[Platzhalter: Datum]"

    return f"""# Projektbericht

## Allgemeine Angaben
- **Projekttitel:** Raspberry Pi Pico 2 Mainboard
- **Projektteam:** Maximilian Str\u00f6hle, Florian Burtscher
- **Datum:** {date_text}

## Was haben wir in dieser Woche geplant?
{planned_lines}

## Was haben wir tats\u00e4chlich erreicht?
{achieved_lines}

## Was haben wir nicht erreicht?
{not_achieved_lines}

## Projektstatus
**Wir sind:** {status_value}

## Bei Verzug: Gegenma\u00dfnahmen
- {delay_1}
- {delay_2}

## Projektrisiko
{project_risk_table}

## Aufgabenrisiko
{task_risk_table}

## N\u00e4chster Meilenstein
- **Bezeichnung:** {milestone_text}
- **Geplantes Datum:** {milestone_date_text}
"""


def _default_project_report_filename(project_name: str) -> str:
    safe_name = "".join(c for c in project_name if c.isalnum() or c in ("-", "_", " ")).replace(" ", "_")
    return f"bericht_{safe_name}_{today_text().replace('-', '')}.md"

