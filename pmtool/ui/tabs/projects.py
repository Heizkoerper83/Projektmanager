from __future__ import annotations

from datetime import date, timedelta
import json
import tkinter as tk
from tkinter import messagebox, ttk

from pmtool.core import format_date, list_milestones, list_projects, list_tasks, list_templates, project_label, task_label


def _risk_rows_text(project: dict[str, object]) -> tuple[str, str]:
    raw_json = str(project.get("risk_rows_json", "") or "")
    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            lines: list[str] = []
            for index, row in enumerate(parsed, start=1):
                if not isinstance(row, dict):
                    continue
                risk = str(row.get("risk", "")).strip()
                if not risk:
                    continue
                try:
                    probability = int(row.get("probability", project.get("risk_probability", 3)))
                except (TypeError, ValueError):
                    probability = 3
                try:
                    impact = int(row.get("impact", project.get("risk_impact", 3)))
                except (TypeError, ValueError):
                    impact = 3
                countermeasure = str(row.get("countermeasure", "")).strip() or "-"
                lines.append(f"{index}. {risk} | Wahrsch.: {max(1, min(5, probability))} | Ausmaß: {max(1, min(5, impact))}")
                lines.append(f"   Gegenmaßnahme: {countermeasure}")
            if lines:
                text = "\n".join(lines)
                return text, "-"

    risk_text = str(project.get("risk", "") or "-")
    countermeasure_text = str(project.get("risk_countermeasure", "") or "-")
    return risk_text, countermeasure_text


def build_projects_tab(app) -> None:
    top = ttk.Frame(app.projects_tab)
    top.pack(fill="x")
    ttk.Label(top, text="Projekte", style="Header.TLabel").grid(row=0, column=0, sticky="w")
    button_row = ttk.Frame(top)
    button_row.grid(row=0, column=1, sticky="e")
    ttk.Button(button_row, text="Neu", style="Accent.TButton", command=app.add_project_dialog).pack(side="left")
    ttk.Button(button_row, text="Bearbeiten", command=app.edit_selected_project).pack(side="left", padx=8)
    ttk.Button(button_row, text="Löschen", command=app.delete_selected_project).pack(side="left")
    ttk.Button(button_row, text="Meilenstein", command=app.add_milestone_dialog).pack(side="left", padx=8)
    ttk.Button(button_row, text="Freigaben", command=app.show_selected_project_shares).pack(side="left", padx=(8, 0))
    ttk.Button(button_row, text="Teilen", command=app.share_selected_project).pack(side="left", padx=8)
    ttk.Button(button_row, text="Entteilen", command=app.unshare_selected_project).pack(side="left")
    ttk.Button(button_row, text="Im Aufgaben-Tab", command=app.open_project_in_tasks_tab).pack(side="left", padx=(8, 0))
    top.columnconfigure(0, weight=1)

    main = ttk.PanedWindow(app.projects_tab, orient=tk.HORIZONTAL)
    main.pack(fill="both", expand=True, pady=(10, 0))
    left = ttk.Frame(main)
    right = ttk.Frame(main)
    main.add(left, weight=2)
    main.add(right, weight=3)

    app.project_tree = ttk.Treeview(
        left,
        columns=("status", "goal", "milestone", "review", "tasks", "open"),
        show="headings",
        height=18,
    )
    for column, heading, width in [
        ("status", "Status", 90),
        ("goal", "Ziel", 220),
        ("milestone", "Meilenstein", 180),
        ("review", "Review", 95),
        ("tasks", "Aufgaben", 75),
        ("open", "Offen", 65),
    ]:
        app.project_tree.heading(column, text=heading)
        app.project_tree.column(column, width=width, anchor="w")
    app.project_tree.pack(fill="both", expand=True)
    app.project_tree.bind("<<TreeviewSelect>>", lambda _: app.update_project_milestones())
    app.project_tree.bind("<Double-1>", lambda _: app.edit_selected_project())

    ttk.Label(right, text="Projektfokus", style="Header.TLabel").pack(anchor="w")
    app.project_focus_name_var = tk.StringVar(value="Kein Projekt ausgewählt")
    app.project_focus_meta_var = tk.StringVar(value="Links ein Projekt auswählen, um alle zugehörigen Inhalte zu sehen.")
    app.project_focus_counts_var = tk.StringVar(value="")

    ttk.Label(right, textvariable=app.project_focus_name_var, style="Subheader.TLabel").pack(anchor="w", pady=(2, 0))
    ttk.Label(right, textvariable=app.project_focus_meta_var).pack(anchor="w", pady=(2, 0))
    ttk.Label(right, textvariable=app.project_focus_counts_var).pack(anchor="w", pady=(2, 8))

    app.project_focus_text = tk.Text(right, height=6, wrap="word")
    app.project_focus_text.pack(fill="x", expand=False, pady=(0, 10))
    app.project_focus_text.configure(state="disabled")
    if not hasattr(app, "text_widgets"):
        app.text_widgets = []
    app.text_widgets.append(app.project_focus_text)

    scope_actions = ttk.Frame(right)
    scope_actions.pack(fill="x", pady=(0, 8))
    ttk.Button(scope_actions, text="Projekt in Aufgaben öffnen", command=app.open_project_in_tasks_tab).pack(side="left")
    ttk.Button(scope_actions, text="Aufgabe öffnen", command=app.open_selected_project_task).pack(side="left", padx=8)
    ttk.Button(scope_actions, text="Vorlage öffnen", command=app.open_selected_project_template).pack(side="left")

    details_notebook = ttk.Notebook(right)
    details_notebook.pack(fill="both", expand=True)

    project_tasks_tab = ttk.Frame(details_notebook, padding=6)
    project_milestones_tab = ttk.Frame(details_notebook, padding=6)
    project_templates_tab = ttk.Frame(details_notebook, padding=6)

    details_notebook.add(project_tasks_tab, text="Aufgaben")
    details_notebook.add(project_milestones_tab, text="Meilensteine")
    details_notebook.add(project_templates_tab, text="Vorlagen")

    app.project_task_tree = ttk.Treeview(
        project_tasks_tab,
        columns=("title", "status", "priority", "due", "tags"),
        show="headings",
        height=12,
    )
    for column, heading, width in [
        ("title", "Titel", 280),
        ("status", "Status", 90),
        ("priority", "Prio", 60),
        ("due", "Fällig", 90),
        ("tags", "Tags", 160),
    ]:
        app.project_task_tree.heading(column, text=heading)
        app.project_task_tree.column(column, width=width, anchor="w")
    app.project_task_tree.pack(fill="both", expand=True)
    app.project_task_tree.bind("<Double-1>", lambda _: app.open_selected_project_task())

    milestone_actions = ttk.Frame(project_milestones_tab)
    milestone_actions.pack(fill="x")
    ttk.Button(milestone_actions, text="Neu", style="Accent.TButton", command=app.add_milestone_dialog).pack(side="left")
    ttk.Button(milestone_actions, text="Bearbeiten", command=app.edit_selected_milestone).pack(side="left", padx=8)
    ttk.Button(milestone_actions, text="Löschen", command=app.delete_selected_milestone).pack(side="left")

    app.milestone_tree = ttk.Treeview(
        project_milestones_tab,
        columns=("title", "due", "status"),
        show="headings",
        height=12,
    )
    for column, heading, width in [
        ("title", "Titel", 260),
        ("due", "Fällig", 100),
        ("status", "Status", 90),
    ]:
        app.milestone_tree.heading(column, text=heading)
        app.milestone_tree.column(column, width=width, anchor="w")
    app.milestone_tree.pack(fill="both", expand=True, pady=(8, 0))
    app.milestone_tree.bind("<<TreeviewSelect>>", lambda _: app.update_active_milestone())
    app.milestone_tree.bind("<Double-1>", lambda _: app.edit_selected_milestone())

    app.project_template_tree = ttk.Treeview(
        project_templates_tab,
        columns=("name", "title", "status", "priority", "recur"),
        show="headings",
        height=12,
    )
    for column, heading, width in [
        ("name", "Name", 150),
        ("title", "Titel", 260),
        ("status", "Status", 90),
        ("priority", "Prio", 60),
        ("recur", "Wiederholung", 100),
    ]:
        app.project_template_tree.heading(column, text=heading)
        app.project_template_tree.column(column, width=width, anchor="w")
    app.project_template_tree.pack(fill="both", expand=True)
    app.project_template_tree.bind("<Double-1>", lambda _: app.open_selected_project_template())


def refresh_projects(app) -> None:
    current_id = selected_project_tree_id(app)
    for row in app.project_tree.get_children():
        app.project_tree.delete(row)
    for project in list_projects():
        app.project_tree.insert(
            "",
            "end",
            iid=str(project["id"]),
            values=(
                project_label(project["status"]),
                project["goal"] or "-",
                project["milestone"] or "-",
                project["next_review_date"] or "-",
                project["task_count"],
                project["open_tasks"] or 0,
            ),
        )

    if current_id is not None and app.project_tree.exists(str(current_id)):
        app.project_tree.selection_set(str(current_id))
    elif app.project_tree.get_children():
        app.project_tree.selection_set(app.project_tree.get_children()[0])

    update_project_milestones(app)


def selected_project_tree_id(app) -> int | None:
    selection = app.project_tree.selection()
    return int(selection[0]) if selection else None


def selected_project_task_id(app) -> int | None:
    selection = app.project_task_tree.selection()
    return int(selection[0]) if selection else None


def selected_project_template_id(app) -> int | None:
    selection = app.project_template_tree.selection()
    return int(selection[0]) if selection else None


def selected_milestone_id(app) -> int | None:
    selection = app.milestone_tree.selection()
    return int(selection[0]) if selection else None


def _reset_project_focus(app) -> None:
    for tree in [app.project_task_tree, app.milestone_tree, app.project_template_tree]:
        for row in tree.get_children():
            tree.delete(row)


def _set_focus_text(app, text: str) -> None:
    app.project_focus_text.configure(state="normal")
    app.project_focus_text.delete("1.0", tk.END)
    app.project_focus_text.insert("1.0", text)
    app.project_focus_text.configure(state="disabled")


def update_project_milestones(app) -> None:
    previous_milestone_id = getattr(app, "active_milestone_id", None)
    _reset_project_focus(app)
    project_id = selected_project_tree_id(app)
    app.active_project_id = project_id

    if project_id is None:
        app.project_focus_name_var.set("Kein Projekt ausgewählt")
        app.project_focus_meta_var.set("Links ein Projekt auswählen, um alle zugehörigen Inhalte zu sehen.")
        app.project_focus_counts_var.set("")
        app.active_milestone_id = None
        _set_focus_text(app, "")
        return

    project = next((item for item in list_projects() if item["id"] == project_id), None)
    if project is None:
        app.project_focus_name_var.set("Projekt nicht gefunden")
        app.project_focus_meta_var.set("")
        app.project_focus_counts_var.set("")
        app.active_milestone_id = None
        _set_focus_text(app, "")
        return

    app.project_focus_name_var.set(project["name"])
    app.project_focus_meta_var.set(
        f"Status: {project_label(project['status'])} | Review: {format_date(project['next_review_date'])}"
    )
    risk_text, countermeasure_text = _risk_rows_text(dict(project))

    _set_focus_text(
        app,
        f"Ziel:\n{project['goal'] or '-'}\n\n"
        f"Aktueller Meilenstein:\n{project['milestone'] or '-'}\n\n"
        f"Risiken:\n{risk_text}\n"
        f"Wahrscheinlichkeit: {project['risk_probability']}\n"
        f"Ausmaß: {project['risk_impact']}\n\n"
        f"Gegenmaßnahmen:\n{countermeasure_text}\n\n"
        f"Beschreibung:\n{project['description'] or '-'}",
    )

    tasks = list_tasks(project_id=project_id, include_done=True)
    milestones = list_milestones(project_id)
    templates = [item for item in list_templates() if item["project_id"] == project_id]

    for task in tasks:
        app.project_task_tree.insert(
            "",
            "end",
            iid=str(task["id"]),
            values=(
                task["title"],
                task_label(task["status"]),
                task["priority"],
                format_date(task["due_date"]),
                task["tags"] or "-",
            ),
        )

    for milestone in milestones:
        app.milestone_tree.insert(
            "",
            "end",
            iid=str(milestone["id"]),
            values=(
                milestone["title"],
                format_date(milestone["due_date"]),
                task_label(milestone["status"]),
            ),
        )

    if previous_milestone_id is not None and app.milestone_tree.exists(str(previous_milestone_id)):
        app.milestone_tree.selection_set(str(previous_milestone_id))
    elif app.milestone_tree.get_children():
        app.milestone_tree.selection_set(app.milestone_tree.get_children()[0])

    update_active_milestone(app)

    for template in templates:
        app.project_template_tree.insert(
            "",
            "end",
            iid=str(template["id"]),
            values=(
                template["name"],
                template["title"],
                task_label(template["status"]),
                template["priority"],
                template["recurrence_days"] or "-",
            ),
        )

    open_count = sum(1 for task in tasks if task["status"] != "done")
    blocked_count = sum(1 for task in tasks if task["status"] == "blocked")
    today = date.today().isoformat()
    week_end = (date.today() + timedelta(days=7)).isoformat()
    week_due_count = sum(
        1
        for task in tasks
        if task["status"] != "done" and task["due_date"] and today <= task["due_date"] <= week_end
    )
    app.project_focus_counts_var.set(
        f"Aufgaben: {len(tasks)} | Offen: {open_count} | Blockiert: {blocked_count} | Diese Woche fällig: {week_due_count} | Vorlagen: {len(templates)} | Meilensteine: {len(milestones)}"
    )


def _apply_project_filter_in_tasks_tab(app, project_id: int) -> None:
    target_prefix = f"{project_id}: "
    for label in app.project_filter_combo["values"]:
        label_text = str(label)
        if label_text.startswith(target_prefix):
            app.project_filter_var.set(label_text)
            break
    app.status_filter_var.set("Alle Aufgaben")
    app.due_filter_var.set("Alle Fälligkeiten")
    app.energy_filter_var.set("Alle Energien")
    app.tag_filter_var.set("")
    app.context_filter_var.set("")
    app.search_var.set("")


def open_project_in_tasks_tab(app) -> None:
    project_id = selected_project_tree_id(app) or app.active_project_id
    if project_id is None:
        messagebox.showinfo("Hinweis", "Bitte ein Projekt auswählen.", parent=app)
        return
    _apply_project_filter_in_tasks_tab(app, project_id)
    app.notebook.select(app.tasks_tab)
    app.refresh_tasks()


def open_selected_project_task(app) -> None:
    task_id = selected_project_task_id(app)
    project_id = selected_project_tree_id(app) or app.active_project_id
    if task_id is None or project_id is None:
        return
    _apply_project_filter_in_tasks_tab(app, project_id)
    app.notebook.select(app.tasks_tab)
    app.refresh_tasks()
    if app.task_tree.exists(str(task_id)):
        app.task_tree.selection_set(str(task_id))
        app.task_tree.focus(str(task_id))
        app.task_tree.see(str(task_id))
    app.update_task_details()


def open_selected_project_template(app) -> None:
    template_id = selected_project_template_id(app)
    if template_id is None:
        return
    app.notebook.select(app.templates_tab)
    app.refresh_templates()
    if app.template_tree.exists(str(template_id)):
        app.template_tree.selection_set(str(template_id))
        app.template_tree.focus(str(template_id))
        app.template_tree.see(str(template_id))
    app.update_active_template()


def update_active_milestone(app) -> None:
    selected = app.milestone_tree.selection()
    app.active_milestone_id = int(selected[0]) if selected else None
