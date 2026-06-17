from __future__ import annotations

from datetime import date
import json
import tkinter as tk
from tkinter import ttk

from pmtool.remote_core import (
    format_date,
    list_task_details,
    list_tasks,
    task_label,
)

_STATUS_FILTER_MAP = {
    "Offen": "open",
    "In Arbeit": "in_progress",
    "Blockiert": "blocked",
    "Erledigt": "done",
}

_ENERGY_FILTER_MAP = {
    "Niedrig": "low",
    "Mittel": "medium",
    "Hoch": "high",
}

_DUE_FILTER_MAP = {
    "Heute": "today",
    "Diese Woche": "week",
    "Überfällig": "overdue",
    "Blockiert": "blocked",
}


def _risk_rows_text(task: dict[str, object]) -> tuple[str, str]:
    raw_json = str(task.get("risk_rows_json", "") or "")
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
                    probability = int(row.get("probability", task.get("risk_probability", 3)))
                except (TypeError, ValueError):
                    probability = 3
                try:
                    impact = int(row.get("impact", task.get("risk_impact", 3)))
                except (TypeError, ValueError):
                    impact = 3
                countermeasure = str(row.get("countermeasure", "")).strip() or "-"
                lines.append(f"{index}. {risk} | Wahrsch.: {max(1, min(5, probability))} | Ausmaß: {max(1, min(5, impact))}")
                lines.append(f"   Gegenmaßnahme: {countermeasure}")
            if lines:
                return "\n".join(lines), "-"

    risk_text = str(task.get("risk", "") or "-")
    countermeasure_text = str(task.get("risk_countermeasure", "") or "-")
    return risk_text, countermeasure_text


def build_tasks_tab(app) -> None:
    top = ttk.Frame(app.tasks_tab)
    top.pack(fill="x")
    ttk.Label(top, text="Aufgaben", style="Header.TLabel").grid(row=0, column=0, sticky="w")
    button_row = ttk.Frame(top)
    button_row.grid(row=0, column=1, sticky="e")
    ttk.Button(button_row, text="Neu", style="Accent.TButton", command=app.add_task_dialog).pack(side="left")
    ttk.Button(button_row, text="Bearbeiten", command=app.edit_selected_task).pack(side="left", padx=8)
    ttk.Button(button_row, text="Erledigt", command=app.complete_selected_task).pack(side="left", padx=0)
    ttk.Button(button_row, text="Offen", command=lambda: app.change_selected_task_status("open")).pack(side="left", padx=(8, 0))
    ttk.Button(button_row, text="In Arbeit", command=lambda: app.change_selected_task_status("in_progress")).pack(side="left", padx=8)
    ttk.Button(button_row, text="Blockiert", command=lambda: app.change_selected_task_status("blocked")).pack(side="left", padx=(0, 8))
    ttk.Button(button_row, text="Notiz", command=app.add_note_to_selected_task).pack(side="left", padx=8)
    ttk.Button(button_row, text="Duplizieren", command=app.duplicate_selected_task).pack(side="left", padx=0)
    ttk.Button(button_row, text="Löschen", command=app.delete_selected_task).pack(side="left", padx=(8, 0))
    top.columnconfigure(0, weight=1)

    filters = ttk.Frame(app.tasks_tab)
    filters.pack(fill="x", pady=(10, 8))
    app.search_entry = ttk.Entry(filters, textvariable=app.search_var)
    app.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    app.project_filter_combo = ttk.Combobox(filters, textvariable=app.project_filter_var, state="readonly")
    app.project_filter_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))
    app.status_filter_combo = ttk.Combobox(
        filters,
        textvariable=app.status_filter_var,
        values=["Alle Aufgaben", "Offen", "In Arbeit", "Blockiert", "Erledigt"],
        state="readonly",
    )
    app.status_filter_combo.grid(row=0, column=2, sticky="ew", padx=(0, 8))
    ttk.Entry(filters, textvariable=app.tag_filter_var, width=14).grid(row=0, column=3, sticky="ew", padx=(0, 8))
    ttk.Entry(filters, textvariable=app.context_filter_var, width=14).grid(row=0, column=4, sticky="ew", padx=(0, 8))
    app.energy_filter_combo = ttk.Combobox(
        filters,
        textvariable=app.energy_filter_var,
        values=["Alle Energien", "Niedrig", "Mittel", "Hoch"],
        state="readonly",
    )
    app.energy_filter_combo.grid(row=0, column=5, sticky="ew", padx=(0, 8))
    app.due_filter_combo = ttk.Combobox(
        filters,
        textvariable=app.due_filter_var,
        values=["Alle Fälligkeiten", "Heute", "Diese Woche", "Überfällig", "Blockiert"],
        state="readonly",
    )
    app.due_filter_combo.grid(row=0, column=6, sticky="ew", padx=(0, 8))
    ttk.Button(filters, text="Aktualisieren", command=app.refresh_all).grid(row=0, column=7, sticky="e")
    for index in range(7):
        filters.columnconfigure(index, weight=1)
    app.project_filter_combo.bind("<<ComboboxSelected>>", lambda _: app.refresh_tasks())
    app.status_filter_combo.bind("<<ComboboxSelected>>", lambda _: app.refresh_tasks())
    app.energy_filter_combo.bind("<<ComboboxSelected>>", lambda _: app.refresh_tasks())
    app.due_filter_combo.bind("<<ComboboxSelected>>", lambda _: app.refresh_tasks())

    main = ttk.PanedWindow(app.tasks_tab, orient=tk.VERTICAL)
    main.pack(fill="both", expand=True)

    tree_frame = ttk.Frame(main)
    details_frame = ttk.Frame(main)
    main.add(tree_frame, weight=3)
    main.add(details_frame, weight=2)

    app.task_tree = ttk.Treeview(
        tree_frame,
        columns=("project", "title", "status", "priority", "due", "energy", "tags"),
        show="headings",
        height=16,
    )
    for column, heading, width in [
        ("project", "Projekt", 150),
        ("title", "Titel", 280),
        ("status", "Status", 90),
        ("priority", "Prio", 60),
        ("due", "Fällig", 90),
        ("energy", "Energie", 80),
        ("tags", "Tags", 180),
    ]:
        app.task_tree.heading(column, text=heading)
        app.task_tree.column(column, width=width, anchor="w")
    app.task_tree.pack(fill="both", expand=True)
    app.task_tree.bind("<<TreeviewSelect>>", lambda _: app.update_task_details())
    app.task_tree.bind("<Double-1>", lambda _: app.edit_selected_task())
    app.task_tree.bind("<Button-3>", app.show_task_context_menu)
    app.task_tree.tag_configure("open", background="#ffffff")
    app.task_tree.tag_configure("in_progress", background="#e0f2fe")
    app.task_tree.tag_configure("blocked", background="#fee2e2")
    app.task_tree.tag_configure("done", background="#dcfce7")
    app.task_tree.tag_configure("overdue", background="#fef3c7")

    bottom = ttk.Notebook(details_frame)
    bottom.pack(fill="both", expand=True)
    app.detail_tab = ttk.Frame(bottom, padding=8)
    app.notes_tab = ttk.Frame(bottom, padding=8)
    app.history_tab = ttk.Frame(bottom, padding=8)
    bottom.add(app.detail_tab, text="Details")
    bottom.add(app.notes_tab, text="Notizen")
    bottom.add(app.history_tab, text="Verlauf")

    app.detail_text = tk.Text(app.detail_tab, height=10, wrap="word")
    app.detail_text.pack(fill="both", expand=True)
    app.notes_text = tk.Text(app.notes_tab, height=10, wrap="word")
    app.notes_text.pack(fill="both", expand=True)
    app.history_text = tk.Text(app.history_tab, height=10, wrap="word")
    app.history_text.pack(fill="both", expand=True)
    app.text_widgets = [app.detail_text, app.notes_text, app.history_text]


def selected_task_id(app) -> int | None:
    selection = app.task_tree.selection()
    return int(selection[0]) if selection else None


def status_filter_value(app) -> str | None:
    return _STATUS_FILTER_MAP.get(app.status_filter_var.get())


def energy_filter_value(app) -> str | None:
    return _ENERGY_FILTER_MAP.get(app.energy_filter_var.get())


def due_filter_value(app) -> str | None:
    return _DUE_FILTER_MAP.get(app.due_filter_var.get())


def refresh_tasks(app) -> None:
    for row in app.task_tree.get_children():
        app.task_tree.delete(row)
    tasks = list_tasks(
        project_id=app.selected_project_id(),
        status=status_filter_value(app),
        search=app.search_var.get().strip() or None,
        due_filter=due_filter_value(app),
        tag=app.tag_filter_var.get().strip() or None,
        context=app.context_filter_var.get().strip() or None,
        energy_level=energy_filter_value(app),
    )
    for task in tasks:
        task_tags = [task["status"]]
        if task["status"] != "done" and task["due_date"] and task["due_date"] < date.today().isoformat():
            task_tags.append("overdue")
        app.task_tree.insert(
            "",
            "end",
            iid=str(task["id"]),
            values=(
                task["project_name"] or "-",
                task["title"],
                task_label(task["status"]),
                task["priority"],
                format_date(task["due_date"]),
                task["energy_level"],
                task["tags"] or "-",
            ),
            tags=task_tags,
        )
    if not app.task_tree.selection() and tasks:
        app.task_tree.selection_set(str(tasks[0]["id"]))
    update_task_details(app)


def update_task_details(app) -> None:
    task_id = selected_task_id(app)
    if task_id is None:
        app.detail_text.delete("1.0", tk.END)
        app.notes_text.delete("1.0", tk.END)
        app.history_text.delete("1.0", tk.END)
        app.active_task_id = None
        return
    try:
        data = list_task_details(task_id)
    except Exception:
        app.active_task_id = None
        return
    task = data.get("task")
    if task is None:
        return
    app.active_task_id = task_id
    risk_text, countermeasure_text = _risk_rows_text(task)
    app.detail_text.delete("1.0", tk.END)
    app.detail_text.insert(
        "1.0",
        f"Projekt: {task['project_name'] or '-'}\n"
        f"Titel: {task['title']}\n"
        f"Status: {task_label(task['status'])}\n"
        f"Priorität: {task['priority']}\n"
        f"Fällig: {task['due_date'] or '-'}\n"
        f"Energie: {task['energy_level']}\n"
        f"Schätzung: {task['estimate_minutes']} Minuten\n"
        f"Kontext: {task['context'] or '-'}\n"
        f"Tags: {task['tags'] or '-'}\n"
        f"Wiederholung: {task['recurrence_days'] or '-'}\n\n"
        f"Risiken:\n{risk_text}\n"
        f"Wahrscheinlichkeit: {task['risk_probability']}\n"
        f"Ausmaß: {task['risk_impact']}\n"
        f"Gegenmaßnahmen:\n{countermeasure_text}\n\n"
        f"Blocker:\n{task['blocked_reason'] or '-'}\n\n"
        f"Details:\n{task['details'] or '-'}",
    )
    notes = data.get("notes", [])
    app.notes_text.delete("1.0", tk.END)
    for note in notes:
        app.notes_text.insert(tk.END, f"[{note['created_at']}] {note['note']}\n\n")
    history = data.get("history", [])
    app.history_text.delete("1.0", tk.END)
    for entry in history:
        app.history_text.insert(tk.END, f"[{entry['created_at']}] {entry['action']}: {entry['details']}\n")
