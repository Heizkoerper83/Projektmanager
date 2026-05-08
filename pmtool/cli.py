"""Command line interface for the local project management tool."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from pmtool.collab_accounts import (
    DEFAULT_ACCOUNTS_PATH,
    create_account,
    activate_account,
    delete_account,
    list_accounts,
    rotate_api_key,
    set_password,
    set_account_enabled,
    set_account_role,
)
from pmtool.core import (
    DB_PATH,
    DUE_FILTER_CHOICES,
    ENERGY_LEVEL_CHOICES,
    PROJECT_STATUS_CHOICES,
    TASK_STATUS_CHOICES,
    add_milestone,
    add_project,
    add_task,
    add_task_note,
    add_template,
    build_task_summary,
    complete_task,
    create_task_from_template,
    delete_project,
    delete_milestone,
    delete_task,
    delete_template,
    export_csv,
    export_json,
    format_date,
    generate_project_report,
    generate_weekly_project_report,
    import_csv,
    import_json,
    init_db,
    list_milestones,
    list_next_tasks,
    list_projects,
    list_task_history,
    list_task_notes,
    list_tasks,
    list_templates,
    project_label,
    task_dashboard_counts,
    task_label,
    update_project,
    update_milestone,
    update_task,
    update_template,
)


def print_table(rows: Sequence[Sequence[object]], headers: Sequence[str]) -> None:
    if not rows:
        print("Keine Einträge gefunden.")
        return
    columns = [list(map(str, headers))]
    for row in rows:
        columns.append([str(value) for value in row])
    widths = [max(len(part) for part in column) for column in zip(*columns)]
    header_line = " | ".join(header.ljust(width) for header, width in zip(headers, widths))
    separator = "-+-".join("-" * width for width in widths)
    print(header_line)
    print(separator)
    for row in rows:
        print(" | ".join(str(value).ljust(width) for value, width in zip(row, widths)))


def show_projects() -> None:
    rows = list_projects()
    if not rows:
        print("Keine Projekte vorhanden.")
        return
    formatted_rows = []
    for row in rows:
        formatted_rows.append(
            [
                row["id"],
                row["name"],
                row["team"] or "-",
                project_label(row["status"]),
                row["task_count"],
                row["open_tasks"] or 0,
                row["blocked_tasks"] or 0,
                row["goal"] or "-",
                row["milestone"] or "-",
                row["risk"] or "-",
                row["risk_probability"],
                row["risk_impact"],
                row["risk_countermeasure"] or "-",
                row["next_review_date"] or "-",
            ]
        )
    print_table(
        formatted_rows,
        ["ID", "Projekt", "Team", "Status", "Aufgaben", "Offen", "Blockiert", "Ziel", "Meilenstein", "Risiko", "Wahrsch.", "Ausmaß", "Gegenmaßnahme", "Review"],
    )


def show_tasks(rows=None) -> None:
    tasks = list(rows) if rows is not None else list_tasks()
    if not tasks:
        print("Keine Aufgaben vorhanden.")
        return
    formatted_rows = []
    for row in tasks:
        formatted_rows.append(
            [
                row["id"],
                row["project_name"] or "-",
                row["title"],
                task_label(row["status"]),
                row["priority"],
                format_date(row["due_date"]),
                row["risk"] or "-",
                row["risk_probability"],
                row["risk_impact"],
                row["risk_countermeasure"] or "-",
                row["energy_level"],
                ",".join(row["tags"].split(",") if row["tags"] else []),
            ]
        )
    print_table(formatted_rows, ["ID", "Projekt", "Titel", "Status", "Prio", "Fällig", "Risiko", "Wahrsch.", "Ausmaß", "Gegenmaßnahme", "Energie", "Tags"])


def show_overview() -> None:
    task_counts = task_dashboard_counts()
    summary = build_task_summary()
    next_tasks = list_next_tasks(limit=5)
    projects = list_projects()

    total_tasks = sum(summary.values())
    open_tasks = summary["open"] + summary["in_progress"] + summary["blocked"]
    completed_tasks = summary["done"]

    print("Projektübersicht")
    print(f"Projekte: {len(projects)}")
    print(f"Aufgaben gesamt: {total_tasks}")
    print(f"Offen: {open_tasks} | Erledigt: {completed_tasks}")
    print(f"Heute fällig: {task_counts['today']} | Überfällig: {task_counts['overdue']} | Blockiert: {task_counts['blocked']}")
    print("Status: " + ", ".join(f"{task_label(status)}={count}" for status, count in summary.items()))
    print()
    print("Nächste Aufgaben")
    show_tasks(next_tasks)


def show_notes(task_id: int) -> None:
    rows = list_task_notes(task_id)
    if not rows:
        print("Keine Notizen vorhanden.")
        return
    print_table([[row["id"], row["created_at"], row["note"]] for row in rows], ["ID", "Zeit", "Notiz"])



def show_history(task_id: int) -> None:
    rows = list_task_history(task_id)
    if not rows:
        print("Kein Verlauf vorhanden.")
        return
    print_table([[row["id"], row["created_at"], row["action"], row["details"]] for row in rows], ["ID", "Zeit", "Aktion", "Details"])



def show_templates() -> None:
    rows = list_templates()
    if not rows:
        print("Keine Vorlagen vorhanden.")
        return
    formatted_rows = []
    for row in rows:
        formatted_rows.append(
            [
                row["id"],
                row["name"],
                row["title"],
                row["priority"],
                task_label(row["status"]),
                row["tags"],
                row["recurrence_days"] or "-",
            ]
        )
    print_table(formatted_rows, ["ID", "Name", "Titel", "Prio", "Status", "Tags", "Wiederholung"])



def show_milestones(project_id: int | None = None) -> None:
    rows = list_milestones(project_id)
    if not rows:
        print("Keine Meilensteine vorhanden.")
        return
    print_table(
        [[row["id"], row["project_name"] or "-", row["title"], row["due_date"] or "-", task_label(row["status"])] for row in rows],
        ["ID", "Projekt", "Titel", "Fällig", "Status"],
    )



def add_project_command(args: argparse.Namespace) -> None:
    add_project(
        args.name,
        args.description,
        args.status,
        team=args.team,
        goal=args.goal,
        milestone=args.milestone,
        risk=args.risk,
        risk_probability=args.risk_probability,
        risk_impact=args.risk_impact,
        risk_weight=args.risk_weight,
        risk_countermeasure=args.risk_countermeasure,
        next_review_date=args.next_review_date,
    )
    print(f"Projekt angelegt: {args.name}")



def update_project_command(args: argparse.Namespace) -> None:
    update_project(
        args.id,
        name=args.name,
        team=args.team,
        description=args.description,
        status=args.status,
        goal=args.goal,
        milestone=args.milestone,
        risk_probability=args.risk_probability,
        risk_impact=args.risk_impact,
        risk=args.risk,
        risk_weight=args.risk_weight,
        risk_countermeasure=args.risk_countermeasure,
        next_review_date=args.next_review_date,
    )
    print(f"Projekt aktualisiert: {args.id}")



def add_task_command(args: argparse.Namespace) -> None:
    add_task(
        args.title,
        project_id=args.project_id,
        details=args.details,
        status=args.status,
        priority=args.priority,
        due_date=args.due_date,
        blocked_reason=args.blocked_reason,
        risk_probability=args.risk_probability,
        risk_impact=args.risk_impact,
        risk=args.risk,
        risk_weight=args.risk_weight,
        risk_countermeasure=args.risk_countermeasure,
        context=args.context,
        energy_level=args.energy_level,
        estimate_minutes=args.estimate_minutes,
        tags=args.tags,
        recurrence_days=args.recurrence_days,
    )
    print(f"Aufgabe angelegt: {args.title}")



def update_task_command(args: argparse.Namespace) -> None:
    update_task(
        args.id,
        title=args.title,
        details=args.details,
        status=args.status,
        priority=args.priority,
        due_date=args.due_date,
        blocked_reason=args.blocked_reason,
        risk_probability=args.risk_probability,
        risk_impact=args.risk_impact,
        risk=args.risk,
        risk_weight=args.risk_weight,
        risk_countermeasure=args.risk_countermeasure,
        project_id=args.project_id,
        context=args.context,
        energy_level=args.energy_level,
        estimate_minutes=args.estimate_minutes,
        tags=args.tags,
        recurrence_days=args.recurrence_days,
    )
    print(f"Aufgabe aktualisiert: {args.id}")



def delete_task_command(args: argparse.Namespace) -> None:
    delete_task(args.id)
    print(f"Aufgabe gelöscht: {args.id}")



def delete_project_command(args: argparse.Namespace) -> None:
    delete_project(args.id)
    print(f"Projekt gelöscht: {args.id}")



def complete_task_command(args: argparse.Namespace) -> None:
    complete_task(args.id)
    print(f"Aufgabe erledigt: {args.id}")



def note_command(args: argparse.Namespace) -> None:
    add_task_note(args.task_id, args.note)
    print(f"Notiz hinzugefügt für Aufgabe {args.task_id}")



def template_add_command(args: argparse.Namespace) -> None:
    add_template(
        args.name,
        title=args.title,
        details=args.details,
        project_id=args.project_id,
        status=args.status,
        priority=args.priority,
        due_offset_days=args.due_offset_days,
        context=args.context,
        energy_level=args.energy_level,
        tags=args.tags,
        recurrence_days=args.recurrence_days,
    )
    print(f"Vorlage angelegt: {args.name}")



def template_update_command(args: argparse.Namespace) -> None:
    update_template(
        args.id,
        name=args.name,
        title=args.title,
        details=args.details,
        project_id=args.project_id,
        status=args.status,
        priority=args.priority,
        due_offset_days=args.due_offset_days,
        context=args.context,
        energy_level=args.energy_level,
        tags=args.tags,
        recurrence_days=args.recurrence_days,
    )
    print(f"Vorlage aktualisiert: {args.id}")



def template_use_command(args: argparse.Namespace) -> None:
    task_id = create_task_from_template(args.id, title=args.title, project_id=args.project_id, due_date=args.due_date)
    print(f"Aufgabe aus Vorlage erstellt: {task_id}")



def template_delete_command(args: argparse.Namespace) -> None:
    delete_template(args.id)
    print(f"Vorlage gelöscht: {args.id}")



def milestone_add_command(args: argparse.Namespace) -> None:
    add_milestone(args.project_id, args.title, args.due_date, args.status)
    print(f"Meilenstein angelegt: {args.title}")


def milestone_update_command(args: argparse.Namespace) -> None:
    update_milestone(args.id, title=args.title, due_date=args.due_date, status=args.status, project_id=args.project_id)
    print(f"Meilenstein aktualisiert: {args.id}")


def milestone_delete_command(args: argparse.Namespace) -> None:
    delete_milestone(args.id)
    print(f"Meilenstein gelöscht: {args.id}")



def export_json_command(args: argparse.Namespace) -> None:
    path = export_json(args.path)
    print(f"JSON-Backup erstellt: {path}")



def import_json_command(args: argparse.Namespace) -> None:
    import_json(args.path, replace=not args.merge)
    print(f"JSON importiert: {args.path}")



def export_csv_command(args: argparse.Namespace) -> None:
    path = export_csv(args.path)
    print(f"CSV-Backup erstellt: {path}")



def import_csv_command(args: argparse.Namespace) -> None:
    import_csv(args.path, replace=not args.merge)
    print(f"CSV importiert: {args.path}")



def list_tasks_command(args: argparse.Namespace) -> None:
    show_tasks(list_tasks(
        project_id=args.project_id,
        status=args.status,
        search=args.search,
        due_filter=args.due_filter,
        tag=args.tag,
        context=args.context,
        energy_level=args.energy_level,
        include_done=args.include_done,
    ))



def next_tasks_command(args: argparse.Namespace) -> None:
    show_tasks(list_next_tasks(limit=args.limit))



def overview_command(_: argparse.Namespace) -> None:
    show_overview()



def gui_command(_: argparse.Namespace) -> int:
    from pmtool.gui import launch_gui

    return launch_gui()


def collab_add_user_command(args: argparse.Namespace) -> None:
    import getpass

    password = args.password
    if not password:
        while True:
            password = getpass.getpass("Passwort (min. 8 Zeichen): ")
            password_confirm = getpass.getpass("Passwort wiederholen: ")
            if password != password_confirm:
                print("✗ Passwoerter stimmen nicht ueberein")
                continue
            try:
                from pmtool.collab_accounts import _validate_password

                _validate_password(password)
                break
            except ValueError as e:
                print(f"✗ {e}")

    try:
        account = create_account(args.email, password, role=args.role, path=args.accounts_path)
        print("✓ Account erstellt (pending Aktivierung):")
        print(f"  E-Mail: {account['email']}")
        print(f"  Rolle: {account['role']}")
        print(f"  Aktivierungs-API-Key: {account['activation_api_key']}")
        print("  Hinweis: Diesen Key fuer die finale Aktivierung verwenden.")
        print(f"  Befehl: python pr.py collab-activate-user {account['email']} --api-key {account['activation_api_key']}")
    except ValueError as e:
        print(f"✗ Fehler: {e}")


def collab_list_users_command(args: argparse.Namespace) -> None:
    rows = list_accounts(args.accounts_path)
    if not rows:
        print("Keine Accounts vorhanden.")
        return
    table_rows = []
    for row in rows:
        table_rows.append([
            row["email"],
            row["role"],
            "ja" if row["enabled"] else "nein",
            "ja" if row.get("has_api_key", False) else "nein",
            row["created_at"] or "-",
            row["last_used_at"] or "-",
        ])
    print_table(table_rows, ["E-Mail", "Rolle", "Aktiv", "API-Key", "Erstellt", "Zuletzt genutzt"])


def collab_disable_user_command(args: argparse.Namespace) -> None:
    set_account_enabled(args.email, False, path=args.accounts_path)
    print(f"Account deaktiviert: {args.email}")


def collab_enable_user_command(args: argparse.Namespace) -> None:
    set_account_enabled(args.email, True, path=args.accounts_path)
    print(f"Account aktiviert: {args.email}")


def collab_activate_user_command(args: argparse.Namespace) -> None:
    try:
        result = activate_account(args.email, args.api_key, path=args.accounts_path)
        print(f"✓ Account final aktiviert: {result['email']}")
    except ValueError as e:
        print(f"✗ Fehler: {e}")


def collab_set_role_command(args: argparse.Namespace) -> None:
    set_account_role(args.email, args.role, path=args.accounts_path)
    print(f"✓ Rolle aktualisiert: {args.email} -> {args.role}")


def collab_set_password_command(args: argparse.Namespace) -> None:
    import getpass
    password = args.password
    if not password:
        password = getpass.getpass("Neues Passwort: ")
        password_confirm = getpass.getpass("Passwort wiederholen: ")
        if password != password_confirm:
            print("Fehler: Passwörter stimmen nicht überein")
            return
    
    try:
        set_password(args.email, password, path=args.accounts_path)
        print(f"✓ Passwort aktualisiert für: {args.email}")
    except ValueError as e:
        print(f"✗ Fehler: {e}")


def collab_delete_user_command(args: argparse.Namespace) -> None:
    delete_account(args.email, path=args.accounts_path)
    print(f"✓ Account gelöscht: {args.email}")


def collab_rotate_key_command(args: argparse.Namespace) -> None:
    try:
        result = rotate_api_key(args.email, path=args.accounts_path)
        print("✓ API-Key rotiert:")
        print(f"  E-Mail: {result['email']}")
        print(f"  API-Key: {result['api_key']}")
        print("  Hinweis: Dieser API-Key wird nur für neue Account-Erstellung benötigt.")
    except ValueError as e:
        print(f"✗ Fehler: {e}")




def generate_report_command(args: argparse.Namespace) -> None:
    """Generate a project report in Markdown format."""
    # Get project ID
    if not args.project_id:
        # List available projects
        projects = list_projects()
        if not projects:
            print("❌ Keine Projekte vorhanden.")
            return
        
        print("\n📋 Verfügbare Projekte:\n")
        for proj in projects:
            print(f"  ID: {proj['id']:2} | {proj['name']}")
        print()
        try:
            project_id = int(input("Projekt-ID eingeben: "))
        except ValueError:
            print("❌ Ungültige Projekt-ID")
            return
    else:
        project_id = args.project_id
    
    # Collect data interactively if not provided
    team = args.team or input("🧑‍💼 Projektteam (Enter zum Überspringen): ") or ""
    planned = args.planned or input("📅 Geplante Inhalte (Enter zum Überspringen): ") or ""
    achieved = args.achieved or input("✅ Erreichte Inhalte (Enter zum Überspringen): ") or ""
    status = args.status or input("📊 Status und SLAs (offen/in_arbeit/blockiert/erledigt), Enter zum Überspringen: ") or ""
    countermeasures = args.countermeasures or input("⚠️ Gegenmaßnahmen (Enter zum Überspringen): ") or ""
    risks = args.risks or input("🚨 Risiken (Enter zum Überspringen): ") or ""
    milestone = args.milestone or input("🎯 Nächster Meilenstein (Enter zum Überspringen): ") or ""
    
    try:
        # Generate report
        output_file = generate_project_report(
            project_id=project_id,
            team=team,
            planned_items=planned,
            achieved_items=achieved,
            status_flags=status,
            countermeasures=countermeasures,
            risks=risks,
            next_milestone=milestone,
        )
        print(f"\n✅ Bericht generiert: {output_file}")
    except ValueError as e:
        print(f"❌ Fehler: {e}")


def generate_weekly_report_command(args: argparse.Namespace) -> None:
    output_file = generate_weekly_project_report(
        output_path=args.output,
        date_value=args.date,
        planned_items=[args.plan1, args.plan2, args.plan3],
        achieved_items=[args.goal1, args.goal2, args.goal3],
        status_text=args.status,
        delay_measures=[args.delay1, args.delay2],
        risks=[args.risk1, args.risk2, args.risk3],
        risk_measures=[args.risk_measure1, args.risk_measure2, args.risk_measure3],
        next_milestone=args.milestone,
        next_milestone_date=args.milestone_date,
    )
    print(f"✅ Wochenbericht generiert: {output_file}")


def init_command(_: argparse.Namespace) -> None:
    init_db()
    print(f"Datenbank bereit: {DB_PATH}")



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lokales Projektmanagement-Tool für Projekte, Aufgaben und Reviews.")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Datenbank anlegen")
    init_parser.set_defaults(func=init_command)

    project_parser = subparsers.add_parser("add-project", help="Neues Projekt anlegen")
    project_parser.add_argument("name", help="Projektname")
    project_parser.add_argument("--team", default="", help="Projektteam")
    project_parser.add_argument("-d", "--description", default="", help="Beschreibung")
    project_parser.add_argument("--goal", default="", help="Projektziel")
    project_parser.add_argument("--milestone", default="", help="Aktueller Meilenstein")
    project_parser.add_argument("--risk", default="", help="Projekt-Risiko")
    project_parser.add_argument("--risk-probability", type=int, default=3, help="Wahrscheinlichkeit 1-5")
    project_parser.add_argument("--risk-impact", type=int, default=3, help="Ausmaß 1-5")
    project_parser.add_argument("--risk-weight", type=int, default=3, help="Legacy-Risiko-Gewichtung 1-5")
    project_parser.add_argument("--risk-countermeasure", default="", help="Gegenmaßnahmen zum Risiko")
    project_parser.add_argument("--next-review-date", help="Review-Datum YYYY-MM-DD")
    project_parser.add_argument(
        "-s",
        "--status",
        default="active",
        choices=PROJECT_STATUS_CHOICES,
        help="Projektstatus",
    )
    project_parser.set_defaults(func=add_project_command)

    update_project_parser = subparsers.add_parser("update-project", help="Projekt ändern")
    update_project_parser.add_argument("id", type=int, help="Projekt-ID")
    update_project_parser.add_argument("--name", help="Neuer Name")
    update_project_parser.add_argument("--team", help="Neues Projektteam")
    update_project_parser.add_argument("--description", help="Neue Beschreibung")
    update_project_parser.add_argument("--goal", help="Neues Ziel")
    update_project_parser.add_argument("--milestone", help="Neuer Meilenstein")
    update_project_parser.add_argument("--risk", help="Neues Projekt-Risiko")
    update_project_parser.add_argument("--risk-probability", type=int, help="Neue Wahrscheinlichkeit 1-5")
    update_project_parser.add_argument("--risk-impact", type=int, help="Neues Ausmaß 1-5")
    update_project_parser.add_argument("--risk-weight", type=int, help="Legacy-Risiko-Gewichtung 1-5")
    update_project_parser.add_argument("--risk-countermeasure", help="Neue Gegenmaßnahmen zum Risiko")
    update_project_parser.add_argument("--next-review-date", help="Neues Review-Datum YYYY-MM-DD")
    update_project_parser.add_argument(
        "--status",
        choices=PROJECT_STATUS_CHOICES,
        help="Neuer Status",
    )
    update_project_parser.set_defaults(func=update_project_command)

    list_projects_parser = subparsers.add_parser("list-projects", help="Projekte anzeigen")
    list_projects_parser.set_defaults(func=lambda _: show_projects())

    gui_parser = subparsers.add_parser("gui", help="Grafische Oberfläche starten")
    gui_parser.set_defaults(func=gui_command)

    collab_add_user_parser = subparsers.add_parser("collab-add-user", help="Collab-Account anlegen")
    collab_add_user_parser.add_argument("email", help="E-Mail-Adresse")
    collab_add_user_parser.add_argument("--password", help="Passwort (wird abgefragt, wenn nicht gegeben)")
    collab_add_user_parser.add_argument("--role", default="reader", choices=["reader", "editor"], help="Rolle")
    collab_add_user_parser.add_argument("--accounts-path", default=str(DEFAULT_ACCOUNTS_PATH), help="Pfad zur Accounts-Datei")
    collab_add_user_parser.set_defaults(func=collab_add_user_command)

    collab_list_users_parser = subparsers.add_parser("collab-list-users", help="Collab-Accounts anzeigen")
    collab_list_users_parser.add_argument("--accounts-path", default=str(DEFAULT_ACCOUNTS_PATH), help="Pfad zur Accounts-Datei")
    collab_list_users_parser.set_defaults(func=collab_list_users_command)

    collab_disable_user_parser = subparsers.add_parser("collab-disable-user", help="Collab-Account deaktivieren")
    collab_disable_user_parser.add_argument("email", help="E-Mail-Adresse")
    collab_disable_user_parser.add_argument("--accounts-path", default=str(DEFAULT_ACCOUNTS_PATH), help="Pfad zur Accounts-Datei")
    collab_disable_user_parser.set_defaults(func=collab_disable_user_command)

    collab_enable_user_parser = subparsers.add_parser("collab-enable-user", help="Collab-Account aktivieren")
    collab_enable_user_parser.add_argument("email", help="E-Mail-Adresse")
    collab_enable_user_parser.add_argument("--accounts-path", default=str(DEFAULT_ACCOUNTS_PATH), help="Pfad zur Accounts-Datei")
    collab_enable_user_parser.set_defaults(func=collab_enable_user_command)

    collab_activate_user_parser = subparsers.add_parser("collab-activate-user", help="Pending Collab-Account final aktivieren")
    collab_activate_user_parser.add_argument("email", help="E-Mail-Adresse")
    collab_activate_user_parser.add_argument("--api-key", required=True, help="Aktivierungs-API-Key")
    collab_activate_user_parser.add_argument("--accounts-path", default=str(DEFAULT_ACCOUNTS_PATH), help="Pfad zur Accounts-Datei")
    collab_activate_user_parser.set_defaults(func=collab_activate_user_command)

    collab_set_role_parser = subparsers.add_parser("collab-set-role", help="Collab-Rolle setzen")
    collab_set_role_parser.add_argument("email", help="E-Mail-Adresse")
    collab_set_role_parser.add_argument("role", choices=["reader", "editor"], help="Neue Rolle")
    collab_set_role_parser.add_argument("--accounts-path", default=str(DEFAULT_ACCOUNTS_PATH), help="Pfad zur Accounts-Datei")
    collab_set_role_parser.set_defaults(func=collab_set_role_command)

    collab_set_password_parser = subparsers.add_parser("collab-set-password", help="Passwort eines Accounts ändern")
    collab_set_password_parser.add_argument("email", help="E-Mail-Adresse")
    collab_set_password_parser.add_argument("--password", help="Neues Passwort (wird abgefragt, wenn nicht gegeben)")
    collab_set_password_parser.add_argument("--accounts-path", default=str(DEFAULT_ACCOUNTS_PATH), help="Pfad zur Accounts-Datei")
    collab_set_password_parser.set_defaults(func=collab_set_password_command)

    collab_delete_user_parser = subparsers.add_parser("collab-delete-user", help="Collab-Account löschen")
    collab_delete_user_parser.add_argument("email", help="E-Mail-Adresse")
    collab_delete_user_parser.add_argument("--accounts-path", default=str(DEFAULT_ACCOUNTS_PATH), help="Pfad zur Accounts-Datei")
    collab_delete_user_parser.set_defaults(func=collab_delete_user_command)

    collab_rotate_key_parser = subparsers.add_parser("collab-rotate-key", help="API-Key eines Accounts rotieren")
    collab_rotate_key_parser.add_argument("email", help="E-Mail-Adresse")
    collab_rotate_key_parser.add_argument("--accounts-path", default=str(DEFAULT_ACCOUNTS_PATH), help="Pfad zur Accounts-Datei")
    collab_rotate_key_parser.set_defaults(func=collab_rotate_key_command)

    task_parser = subparsers.add_parser("add-task", help="Neue Aufgabe anlegen")
    task_parser.add_argument("title", help="Aufgabentitel")
    task_parser.add_argument("-p", "--project-id", type=int, help="Projekt-ID")
    task_parser.add_argument("-d", "--details", default="", help="Details")
    task_parser.add_argument("--context", default="", help="Kontext")
    task_parser.add_argument("--energy-level", default="medium", choices=ENERGY_LEVEL_CHOICES, help="Energielevel")
    task_parser.add_argument("--estimate-minutes", type=int, default=0, help="Geschätzte Minuten")
    task_parser.add_argument("--tags", default="", help="Tags, kommagetrennt")
    task_parser.add_argument("--recurrence-days", type=int, help="Wiederholung in Tagen")
    task_parser.add_argument(
        "-s",
        "--status",
        default="open",
        choices=TASK_STATUS_CHOICES,
        help="Aufgabenstatus",
    )
    task_parser.add_argument("--priority", type=int, default=3, help="Priorität 1-5")
    task_parser.add_argument("--due-date", help="Fälligkeitsdatum YYYY-MM-DD")
    task_parser.add_argument("--blocked-reason", default="", help="Warum blockiert")
    task_parser.add_argument("--risk", default="", help="Aufgaben-Risiko")
    task_parser.add_argument("--risk-probability", type=int, default=3, help="Wahrscheinlichkeit 1-5")
    task_parser.add_argument("--risk-impact", type=int, default=3, help="Ausmaß 1-5")
    task_parser.add_argument("--risk-weight", type=int, default=3, help="Legacy-Risiko-Gewichtung 1-5")
    task_parser.add_argument("--risk-countermeasure", default="", help="Gegenmaßnahmen zum Risiko")
    task_parser.set_defaults(func=add_task_command)

    update_task_parser = subparsers.add_parser("update-task", help="Aufgabe ändern")
    update_task_parser.add_argument("id", type=int, help="Aufgaben-ID")
    update_task_parser.add_argument("--title", help="Neuer Titel")
    update_task_parser.add_argument("--details", help="Neue Details")
    update_task_parser.add_argument(
        "--status",
        choices=TASK_STATUS_CHOICES,
        help="Neuer Status",
    )
    update_task_parser.add_argument("--priority", type=int, help="Neue Priorität")
    update_task_parser.add_argument("--due-date", help="Neues Fälligkeitsdatum YYYY-MM-DD")
    update_task_parser.add_argument("--blocked-reason", help="Neuer Blocker-Grund")
    update_task_parser.add_argument("--risk", help="Neues Aufgaben-Risiko")
    update_task_parser.add_argument("--risk-probability", type=int, help="Neue Wahrscheinlichkeit 1-5")
    update_task_parser.add_argument("--risk-impact", type=int, help="Neues Ausmaß 1-5")
    update_task_parser.add_argument("--risk-weight", type=int, help="Legacy-Risiko-Gewichtung 1-5")
    update_task_parser.add_argument("--risk-countermeasure", help="Neue Gegenmaßnahmen zum Risiko")
    update_task_parser.add_argument("-p", "--project-id", type=int, help="Neue Projekt-ID")
    update_task_parser.add_argument("--context", help="Neuer Kontext")
    update_task_parser.add_argument("--energy-level", choices=ENERGY_LEVEL_CHOICES, help="Neues Energielevel")
    update_task_parser.add_argument("--estimate-minutes", type=int, help="Neue Schätzung")
    update_task_parser.add_argument("--tags", help="Neue Tags")
    update_task_parser.add_argument("--recurrence-days", type=int, help="Neue Wiederholung")
    update_task_parser.set_defaults(func=update_task_command)

    delete_task_parser = subparsers.add_parser("delete-task", help="Aufgabe löschen")
    delete_task_parser.add_argument("id", type=int, help="Aufgaben-ID")
    delete_task_parser.set_defaults(func=delete_task_command)

    complete_task_parser = subparsers.add_parser("complete-task", help="Aufgabe erledigen")
    complete_task_parser.add_argument("id", type=int, help="Aufgaben-ID")
    complete_task_parser.set_defaults(func=complete_task_command)

    delete_project_parser = subparsers.add_parser("delete-project", help="Projekt löschen")
    delete_project_parser.add_argument("id", type=int, help="Projekt-ID")
    delete_project_parser.set_defaults(func=delete_project_command)

    list_tasks_parser = subparsers.add_parser("list-tasks", help="Aufgaben anzeigen")
    list_tasks_parser.add_argument("-p", "--project-id", type=int, help="Nur Aufgaben eines Projekts")
    list_tasks_parser.add_argument("-s", "--status", choices=TASK_STATUS_CHOICES, help="Nur Aufgaben mit diesem Status")
    list_tasks_parser.add_argument("--search", help="Suche in Titel, Details, Tags, Kontext")
    list_tasks_parser.add_argument("--due-filter", choices=DUE_FILTER_CHOICES, help="Fälligkeitsfilter")
    list_tasks_parser.add_argument("--tag", help="Tag-Filter")
    list_tasks_parser.add_argument("--context", help="Kontext-Filter")
    list_tasks_parser.add_argument("--energy-level", choices=ENERGY_LEVEL_CHOICES, help="Energiefilter")
    list_tasks_parser.add_argument("--include-done", action="store_true", help="Erledigte Aufgaben mit anzeigen")
    list_tasks_parser.set_defaults(func=list_tasks_command)

    next_parser = subparsers.add_parser("next", help="Die nächsten sinnvollen Aufgaben anzeigen")
    next_parser.add_argument("-n", "--limit", type=int, default=10, help="Anzahl")
    next_parser.set_defaults(func=next_tasks_command)

    overview_parser = subparsers.add_parser("overview", help="Gesamtübersicht anzeigen")
    overview_parser.set_defaults(func=overview_command)

    note_parser = subparsers.add_parser("add-note", help="Notiz an eine Aufgabe anhängen")
    note_parser.add_argument("task_id", type=int, help="Aufgaben-ID")
    note_parser.add_argument("note", help="Notiztext")
    note_parser.set_defaults(func=note_command)

    notes_parser = subparsers.add_parser("list-notes", help="Notizen anzeigen")
    notes_parser.add_argument("task_id", type=int, help="Aufgaben-ID")
    notes_parser.set_defaults(func=lambda args: show_notes(args.task_id))

    history_parser = subparsers.add_parser("history", help="Verlauf anzeigen")
    history_parser.add_argument("task_id", type=int, help="Aufgaben-ID")
    history_parser.set_defaults(func=lambda args: show_history(args.task_id))

    template_add_parser = subparsers.add_parser("add-template", help="Neue Vorlage anlegen")
    template_add_parser.add_argument("name", help="Vorlagenname")
    template_add_parser.add_argument("title", help="Titel")
    template_add_parser.add_argument("-d", "--details", default="", help="Details")
    template_add_parser.add_argument("-p", "--project-id", type=int, help="Projekt-ID")
    template_add_parser.add_argument("-s", "--status", default="open", choices=TASK_STATUS_CHOICES, help="Status")
    template_add_parser.add_argument("--priority", type=int, default=3, help="Priorität")
    template_add_parser.add_argument("--due-offset-days", type=int, help="Fälligkeits-Offset")
    template_add_parser.add_argument("--context", default="", help="Kontext")
    template_add_parser.add_argument("--energy-level", default="medium", choices=ENERGY_LEVEL_CHOICES, help="Energielevel")
    template_add_parser.add_argument("--tags", default="", help="Tags")
    template_add_parser.add_argument("--recurrence-days", type=int, help="Wiederholung")
    template_add_parser.set_defaults(func=template_add_command)

    template_update_parser = subparsers.add_parser("update-template", help="Vorlage ändern")
    template_update_parser.add_argument("id", type=int, help="Vorlagen-ID")
    template_update_parser.add_argument("--name")
    template_update_parser.add_argument("--title")
    template_update_parser.add_argument("--details")
    template_update_parser.add_argument("--project-id", type=int)
    template_update_parser.add_argument("--status", choices=TASK_STATUS_CHOICES)
    template_update_parser.add_argument("--priority", type=int)
    template_update_parser.add_argument("--due-offset-days", type=int)
    template_update_parser.add_argument("--context")
    template_update_parser.add_argument("--energy-level", choices=ENERGY_LEVEL_CHOICES)
    template_update_parser.add_argument("--tags")
    template_update_parser.add_argument("--recurrence-days", type=int)
    template_update_parser.set_defaults(func=template_update_command)

    template_use_parser = subparsers.add_parser("use-template", help="Aufgabe aus Vorlage erstellen")
    template_use_parser.add_argument("id", type=int, help="Vorlagen-ID")
    template_use_parser.add_argument("--title", help="Überschreiben des Titels")
    template_use_parser.add_argument("--project-id", type=int, help="Projekt-ID")
    template_use_parser.add_argument("--due-date", help="Fälligkeitsdatum YYYY-MM-DD")
    template_use_parser.set_defaults(func=template_use_command)

    template_delete_parser = subparsers.add_parser("delete-template", help="Vorlage löschen")
    template_delete_parser.add_argument("id", type=int, help="Vorlagen-ID")
    template_delete_parser.set_defaults(func=template_delete_command)

    list_templates_parser = subparsers.add_parser("list-templates", help="Vorlagen anzeigen")
    list_templates_parser.set_defaults(func=lambda _: show_templates())

    milestone_add_parser = subparsers.add_parser("add-milestone", help="Meilenstein anlegen")
    milestone_add_parser.add_argument("project_id", type=int, help="Projekt-ID")
    milestone_add_parser.add_argument("title", help="Titel")
    milestone_add_parser.add_argument("--due-date", help="Fälligkeitsdatum YYYY-MM-DD")
    milestone_add_parser.add_argument("--status", default="open", choices=TASK_STATUS_CHOICES)
    milestone_add_parser.set_defaults(func=milestone_add_command)

    milestone_update_parser = subparsers.add_parser("update-milestone", help="Meilenstein ändern")
    milestone_update_parser.add_argument("id", type=int, help="Meilenstein-ID")
    milestone_update_parser.add_argument("--project-id", type=int, help="Neue Projekt-ID")
    milestone_update_parser.add_argument("--title", help="Neuer Titel")
    milestone_update_parser.add_argument("--due-date", help="Neues Fälligkeitsdatum YYYY-MM-DD")
    milestone_update_parser.add_argument("--status", choices=TASK_STATUS_CHOICES)
    milestone_update_parser.set_defaults(func=milestone_update_command)

    milestone_delete_parser = subparsers.add_parser("delete-milestone", help="Meilenstein löschen")
    milestone_delete_parser.add_argument("id", type=int, help="Meilenstein-ID")
    milestone_delete_parser.set_defaults(func=milestone_delete_command)

    list_milestones_parser = subparsers.add_parser("list-milestones", help="Meilensteine anzeigen")
    list_milestones_parser.add_argument("--project-id", type=int, help="Projekt-ID")
    list_milestones_parser.set_defaults(func=lambda args: show_milestones(args.project_id))

    export_json_parser = subparsers.add_parser("export-json", help="Vollbackup als JSON schreiben")
    export_json_parser.add_argument("path", help="Zielpfad")
    export_json_parser.set_defaults(func=export_json_command)

    import_json_parser = subparsers.add_parser("import-json", help="Vollbackup aus JSON laden")
    import_json_parser.add_argument("path", help="Quelldatei")
    import_json_parser.add_argument("--merge", action="store_true", help="Daten ergänzen statt ersetzen")
    import_json_parser.set_defaults(func=import_json_command)

    export_csv_parser = subparsers.add_parser("export-csv", help="Backup als CSV-Ordner schreiben")
    export_csv_parser.add_argument("path", help="Zielordner")
    export_csv_parser.set_defaults(func=export_csv_command)

    import_csv_parser = subparsers.add_parser("import-csv", help="Backup aus CSV-Ordner laden")
    import_csv_parser.add_argument("path", help="Quelldordner")
    import_csv_parser.add_argument("--merge", action="store_true", help="Daten ergänzen statt ersetzen")
    import_csv_parser.set_defaults(func=import_csv_command)

    report_parser = subparsers.add_parser("generate-report", help="Projektbericht als .md-Datei generieren")
    report_parser.add_argument("-p", "--project-id", type=int, help="Projekt-ID (wird abgefragt, wenn nicht gegeben)")
    report_parser.add_argument("--team", help="Projektteam")
    report_parser.add_argument("--planned", help="Geplante Inhalte")
    report_parser.add_argument("--achieved", help="Erreichte Inhalte")
    report_parser.add_argument("--status", help="Status und SLAs")
    report_parser.add_argument("--countermeasures", help="Gegenmaßnahmen")
    report_parser.add_argument("--risks", help="Risiken")
    report_parser.add_argument("--milestone", help="Nächster Meilenstein")
    report_parser.set_defaults(func=generate_report_command)

    weekly_report_parser = subparsers.add_parser(
        "generate-weekly-report",
        help="Woechentlichen Projektbericht als .md-Datei generieren",
    )
    weekly_report_parser.add_argument("--output", help="Zielpfad der .md-Datei")
    weekly_report_parser.add_argument("--date", help="Datum")
    weekly_report_parser.add_argument("--plan1", help="Plan 1")
    weekly_report_parser.add_argument("--plan2", help="Plan 2")
    weekly_report_parser.add_argument("--plan3", help="Plan 3")
    weekly_report_parser.add_argument("--goal1", help="Ziel 1")
    weekly_report_parser.add_argument("--goal2", help="Ziel 2")
    weekly_report_parser.add_argument("--goal3", help="Ziel 3")
    weekly_report_parser.add_argument("--status", help="Im Plan / Im Verzug / Schneller als geplant")
    weekly_report_parser.add_argument("--delay1", help="Gegenmassnahme 1 bei Verzug")
    weekly_report_parser.add_argument("--delay2", help="Gegenmassnahme 2 bei Verzug")
    weekly_report_parser.add_argument("--risk1", help="Risiko 1")
    weekly_report_parser.add_argument("--risk2", help="Risiko 2")
    weekly_report_parser.add_argument("--risk3", help="Risiko 3")
    weekly_report_parser.add_argument("--risk-measure1", dest="risk_measure1", help="Gegenmassnahme zu Risiko 1")
    weekly_report_parser.add_argument("--risk-measure2", dest="risk_measure2", help="Gegenmassnahme zu Risiko 2")
    weekly_report_parser.add_argument("--risk-measure3", dest="risk_measure3", help="Gegenmassnahme zu Risiko 3")
    weekly_report_parser.add_argument("--milestone", help="Meilenstein")
    weekly_report_parser.add_argument("--milestone-date", help="Geplantes Datum Meilenstein")
    weekly_report_parser.set_defaults(func=generate_weekly_report_command)

    return parser



def main(argv: Sequence[str] | None = None) -> int:
    init_db()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        result = args.func(args)
        if isinstance(result, int):
            return result
    except ValueError as exc:
        print(f"Fehler: {exc}")
        return 1
    return 0
