"""Remote API client for server-only mode (no local database)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from http.cookies import SimpleCookie

# HINWEIS: Direkte Importe aus pmtool.core.legacy / pmtool.core.reports
# (nicht über pmtool.core, da dort ein sys.modules-Swap-Trick verwendet wird,
# den PyInstaller im frozen build nicht korrekt auflösen kann.)
from pmtool.core.legacy import (
    DUE_FILTER_CHOICES,
    ENERGY_LEVEL_CHOICES,
    PROJECT_STATUS_CHOICES,
    TASK_STATUS_CHOICES,
    export_csv,
    export_json,
    format_date,
    import_csv,
    import_json,
    normalize_energy_level,
    normalize_tags,
    parse_due_date,
    project_label,
    task_label,
)
from pmtool.core.reports import (
    build_weekly_project_report_markdown,
    generate_weekly_project_report,
)


class RemoteError(RuntimeError):
    """Generic remote API error."""


class RemoteAuthError(RemoteError):
    """Authentication or authorization error."""


class RemoteConnectionError(RemoteError):
    """Raised when the server is unreachable."""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


@dataclass
class RemoteSession:
    base_url: str
    session_id: str
    account: dict[str, Any] | None = None

    def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | bytes | None = None,
        expect_json: bool = True,
        content_type: str = "application/json",
    ) -> Any:
        url = urljoin(self.base_url, path)
        headers = {
            "Accept": "application/json",
            "Content-Type": content_type,
            "Cookie": f"PMTOOL_SESSION={self.session_id}",
        }
        payload: bytes | None
        if isinstance(data, bytes):
            payload = data
        elif data is not None:
            payload = json.dumps(data).encode("utf-8")
        else:
            payload = None
        request = Request(url, data=payload, headers=headers, method=method)
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read()
            if not expect_json:
                return raw
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            try:
                raw = exc.read()
                if raw:
                    payload = json.loads(raw.decode("utf-8"))
                    message = payload.get("error") if isinstance(payload, dict) else str(payload)
                else:
                    message = exc.reason
            except Exception:
                message = exc.reason
            if exc.code in (401, 403):
                raise RemoteAuthError(str(message)) from exc
            raise RemoteError(str(message)) from exc
        except URLError as exc:
            raise RemoteConnectionError(str(exc)) from exc


_SESSION: RemoteSession | None = None


def configure_session(base_url: str, session_id: str, account: dict[str, Any] | None = None) -> RemoteSession:
    global _SESSION
    _SESSION = RemoteSession(base_url=base_url.rstrip("/"), session_id=session_id, account=account)
    return _SESSION


def clear_session() -> None:
    global _SESSION
    _SESSION = None


def require_session() -> RemoteSession:
    if _SESSION is None:
        raise RemoteAuthError("Keine aktive Server-Sitzung gefunden.")
    return _SESSION


def _extract_cookie_value(cookie_header: str, key: str) -> str | None:
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get(key)
    if morsel is None:
        return None
    return morsel.value


def login(base_url: str, email: str, password: str) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    form_data = urlencode({"email": email, "password": password, "desktop_token": ""}).encode("utf-8")
    opener = build_opener(_NoRedirectHandler())
    request = Request(urljoin(base_url, "/login"), data=form_data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        response = opener.open(request, timeout=10)
        headers = response.headers
        response.close()
    except HTTPError as exc:
        headers = exc.headers
        if exc.code not in (302, 303):
            raise RemoteAuthError("Login fehlgeschlagen.") from exc
    cookie_header = headers.get("Set-Cookie", "")
    session_id = _extract_cookie_value(cookie_header, "PMTOOL_SESSION")
    if not session_id:
        raise RemoteAuthError("Login fehlgeschlagen (keine Session).")

    session = configure_session(base_url, session_id)
    account = session._request("GET", "/api/me")
    session.account = account.get("account") if isinstance(account, dict) else None
    return {"session_id": session_id, "account": session.account or {}}


def register(base_url: str, email: str, password: str) -> None:
    base_url = base_url.rstrip("/")
    form_data = urlencode({"email": email, "password": password}).encode("utf-8")
    request = Request(urljoin(base_url, "/register"), data=form_data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
        if "Account erstellt" not in body:
            raise RemoteError("Registrierung fehlgeschlagen.")
    except HTTPError as exc:
        raise RemoteError("Registrierung fehlgeschlagen.") from exc
    except URLError as exc:
        raise RemoteConnectionError(str(exc)) from exc


# --- Data access helpers ---


def list_projects() -> list[dict[str, Any]]:
    return require_session()._request("GET", "/api/projects")


def list_project_shares(project_id: int) -> list[dict[str, Any]]:
    return require_session()._request("GET", f"/api/projects/{project_id}/shares")


def share_project(project_id: int, account_name: str) -> None:
    require_session()._request("POST", f"/api/projects/{project_id}/share", {"account_name": account_name})


def unshare_project(project_id: int, account_name: str) -> None:
    require_session()._request("POST", f"/api/projects/{project_id}/unshare", {"account_name": account_name})


def add_project(*args, **kwargs) -> None:
    payload = _project_payload(*args, **kwargs)
    require_session()._request("POST", "/api/projects", payload)


def update_project(project_id: int, **kwargs) -> None:
    payload = _project_payload(**kwargs)
    require_session()._request("PATCH", f"/api/projects/{project_id}", payload)


def delete_project(project_id: int) -> None:
    require_session()._request("DELETE", f"/api/projects/{project_id}")


def _project_payload(
    name: str | None = None,
    team: str | None = None,
    description: str | None = None,
    status: str | None = None,
    goal: str | None = None,
    milestone: str | None = None,
    risk: str | None = None,
    risk_rows: list[dict[str, Any]] | None = None,
    risk_probability: int | None = None,
    risk_impact: int | None = None,
    risk_weight: int | None = None,
    risk_countermeasure: str | None = None,
    next_review_date: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in {
        "name": name,
        "team": team,
        "description": description,
        "status": status,
        "goal": goal,
        "milestone": milestone,
        "risk": risk,
        "risk_rows_json": json.dumps(risk_rows) if risk_rows is not None else None,
        "risk_probability": risk_probability,
        "risk_impact": risk_impact,
        "risk_weight": risk_weight,
        "risk_countermeasure": risk_countermeasure,
        "next_review_date": next_review_date,
    }.items():
        if value is not None:
            payload[key] = value
    return payload


def list_tasks(
    project_id: int | None = None,
    status: str | None = None,
    search: str | None = None,
    due_filter: str | None = None,
    tag: str | None = None,
    context: str | None = None,
    energy_level: str | None = None,
    include_done: bool = True,
) -> list[dict[str, Any]]:
    query: list[str] = []
    if project_id is not None:
        query.append(f"project_id={project_id}")
    if status:
        query.append(f"status={status}")
    if search:
        query.append(f"search={search}")
    if due_filter:
        query.append(f"due_filter={due_filter}")
    if tag:
        query.append(f"tag={tag}")
    if context:
        query.append(f"context={context}")
    if energy_level:
        query.append(f"energy_level={energy_level}")
    if include_done:
        query.append("include_done=true")
    path = "/api/tasks"
    if query:
        path += "?" + "&".join(query)
    return require_session()._request("GET", path)


def get_task(task_id: int) -> dict[str, Any] | None:
    payload = require_session()._request("GET", f"/api/tasks/{task_id}")
    return payload or None


def add_task(*args, **kwargs) -> int | None:
    payload = _task_payload(*args, **kwargs)
    require_session()._request("POST", "/api/tasks", payload)
    return None


def update_task(task_id: int, **kwargs) -> None:
    payload = _task_payload(**kwargs)
    require_session()._request("PATCH", f"/api/tasks/{task_id}", payload)


def complete_task(task_id: int) -> None:
    update_task(task_id, status="done")


def delete_task(task_id: int) -> None:
    require_session()._request("DELETE", f"/api/tasks/{task_id}")


def _task_payload(
    title: str | None = None,
    project_id: int | None = None,
    details: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    due_date: str | None = None,
    blocked_reason: str | None = None,
    risk: str | None = None,
    risk_rows: list[dict[str, Any]] | None = None,
    risk_probability: int | None = None,
    risk_impact: int | None = None,
    risk_weight: int | None = None,
    risk_countermeasure: str | None = None,
    context: str | None = None,
    energy_level: str | None = None,
    estimate_minutes: int | None = None,
    tags: str | None = None,
    recurrence_days: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in {
        "title": title,
        "project_id": project_id,
        "details": details,
        "status": status,
        "priority": priority,
        "due_date": due_date,
        "blocked_reason": blocked_reason,
        "risk": risk,
        "risk_rows_json": json.dumps(risk_rows) if risk_rows is not None else None,
        "risk_probability": risk_probability,
        "risk_impact": risk_impact,
        "risk_weight": risk_weight,
        "risk_countermeasure": risk_countermeasure,
        "context": context,
        "energy_level": energy_level,
        "estimate_minutes": estimate_minutes,
        "tags": tags,
        "recurrence_days": recurrence_days,
    }.items():
        if value is not None:
            payload[key] = value
    return payload


def list_task_notes(task_id: int) -> list[dict[str, Any]]:
    return require_session()._request("GET", f"/api/tasks/{task_id}/notes")


def list_task_history(task_id: int) -> list[dict[str, Any]]:
    return require_session()._request("GET", f"/api/tasks/{task_id}/history")


def add_task_note(task_id: int, note: str) -> None:
    require_session()._request("POST", f"/api/tasks/{task_id}/notes", {"note": note})


def list_milestones(project_id: int | None = None) -> list[dict[str, Any]]:
    path = "/api/milestones"
    if project_id is not None:
        path += f"?project_id={project_id}"
    return require_session()._request("GET", path)


def add_milestone(project_id: int, title: str, due_date: str | None = None, status: str = "open") -> None:
    require_session()._request(
        "POST",
        "/api/milestones",
        {"project_id": project_id, "title": title, "due_date": due_date, "status": status},
    )


def update_milestone(
    milestone_id: int,
    *,
    title: str | None = None,
    due_date: str | None = None,
    status: str | None = None,
    project_id: int | None = None,
) -> None:
    payload = {k: v for k, v in {"title": title, "due_date": due_date, "status": status, "project_id": project_id}.items() if v is not None}
    require_session()._request("PATCH", f"/api/milestones/{milestone_id}", payload)


def delete_milestone(milestone_id: int) -> None:
    require_session()._request("DELETE", f"/api/milestones/{milestone_id}")


def list_templates() -> list[dict[str, Any]]:
    return require_session()._request("GET", "/api/templates")


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
    tags: str | None = None,
    recurrence_days: int | None = None,
) -> None:
    payload = {
        "name": name,
        "title": title,
        "details": details,
        "project_id": project_id,
        "status": status,
        "priority": priority,
        "due_offset_days": due_offset_days,
        "context": context,
        "energy_level": energy_level,
        "tags": tags,
        "recurrence_days": recurrence_days,
    }
    require_session()._request("POST", "/api/templates", payload)


def update_template(template_id: int, **kwargs) -> None:
    payload = {k: v for k, v in kwargs.items() if v is not None}
    require_session()._request("PATCH", f"/api/templates/{template_id}", payload)


def delete_template(template_id: int) -> None:
    require_session()._request("DELETE", f"/api/templates/{template_id}")


def create_task_from_template(template_id: int, *, title: str | None = None, project_id: int | None = None, due_date: str | None = None) -> int:
    payload = {"template_id": template_id, "title": title, "project_id": project_id, "due_date": due_date}
    result = require_session()._request("POST", "/api/tasks/from-template", payload)
    if not isinstance(result, dict) or "task_id" not in result:
        raise RemoteError("Fehler beim Erstellen der Aufgabe aus Vorlage.")
    return int(result["task_id"])


def list_next_tasks(limit: int = 10) -> list[dict[str, Any]]:
    return list_tasks(include_done=False)[:limit]


def task_dashboard_counts() -> dict[str, int]:
    payload = require_session()._request("GET", "/api/dashboard")
    return payload.get("tasks", {}) if isinstance(payload, dict) else {}


def project_dashboard_counts() -> dict[str, int]:
    payload = require_session()._request("GET", "/api/dashboard")
    return payload.get("projects", {}) if isinstance(payload, dict) else {}


def build_task_summary() -> dict[str, int]:
    counts: dict[str, int] = {"open": 0, "in_progress": 0, "blocked": 0, "done": 0}
    for row in list_tasks(include_done=True):
        status = str(row.get("status", ""))
        if status in counts:
            counts[status] += 1
    return counts


def _default_project_report_filename(project_name: str) -> str:
    safe_name = "".join(c for c in project_name if c.isalnum() or c in ("-", "_", " ")).replace(" ", "_")
    return f"bericht_{safe_name}_{date.today().isoformat().replace('-', '')}.md"


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
    projects = list_projects()
    project = next((row for row in projects if int(row.get("id", -1)) == project_id), None)
    if not project:
        raise RemoteError(f"Projekt {project_id} existiert nicht.")

    tasks = list_tasks(project_id=project_id)
    task_counts = {
        "open": sum(1 for t in tasks if t.get("status") == "open"),
        "in_progress": sum(1 for t in tasks if t.get("status") == "in_progress"),
        "blocked": sum(1 for t in tasks if t.get("status") == "blocked"),
        "done": sum(1 for t in tasks if t.get("status") == "done"),
    }

    report_md = f"""# Projektbericht: {project.get('name', '')}

**Generiert am:** {date.today().isoformat()}
**Projekt-ID:** {project_id}

## Projektuebersicht

- **Beschreibung:** {project.get('description', '—')}
- **Ziel:** {project.get('goal', '—')}
- **Status:** {project_label(str(project.get('status', '')))}
- **Naechste Review:** {format_date(project.get('next_review_date'))}

## Statistik

- **Offene Aufgaben:** {task_counts['open']}
- **In Arbeit:** {task_counts['in_progress']}
- **Blockiert:** {task_counts['blocked']}
- **Erledigt:** {task_counts['done']}

## Projektteam

{team if team else '—'}

## Geplante Inhalte

{planned_items if planned_items else '—'}

## Erreichte Inhalte

{achieved_items if achieved_items else '—'}

## Projektstatus

{status_flags if status_flags else '—'}

## Gegenmassnahmen

{countermeasures if countermeasures else '—'}

## Risiken

{risks if risks else '—'}

## Naechster Meilenstein

{next_milestone if next_milestone else '—'}

---

*Erstellt mit Projektmanager*
"""

    if output_path is None:
        output_path = Path(_default_project_report_filename(str(project.get("name", ""))))
    else:
        output_path = Path(output_path)
    output_path.write_text(report_md, encoding="utf-8")
    return output_path


def list_accounts() -> list[dict[str, Any]]:
    return require_session()._request("GET", "/api/sync/accounts")


__all__ = [
    "RemoteError",
    "RemoteAuthError",
    "RemoteConnectionError",
    "configure_session",
    "clear_session",
    "login",
    "register",
    "list_projects",
    "list_project_shares",
    "share_project",
    "unshare_project",
    "add_project",
    "update_project",
    "delete_project",
    "list_tasks",
    "get_task",
    "add_task",
    "update_task",
    "complete_task",
    "delete_task",
    "list_task_notes",
    "list_task_history",
    "add_task_note",
    "list_milestones",
    "add_milestone",
    "update_milestone",
    "delete_milestone",
    "list_templates",
    "add_template",
    "update_template",
    "delete_template",
    "create_task_from_template",
    "export_csv",
    "export_json",
    "import_csv",
    "import_json",
    "list_next_tasks",
    "task_dashboard_counts",
    "project_dashboard_counts",
    "build_task_summary",
    "list_accounts",
    "DUE_FILTER_CHOICES",
    "ENERGY_LEVEL_CHOICES",
    "PROJECT_STATUS_CHOICES",
    "TASK_STATUS_CHOICES",
    "build_weekly_project_report_markdown",
    "format_date",
    "generate_weekly_project_report",
    "generate_project_report",
    "normalize_energy_level",
    "normalize_tags",
    "parse_due_date",
    "project_label",
    "task_label",
]
