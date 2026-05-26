from __future__ import annotations

from tkinter import ttk

from pmtool.remote_core import list_projects, list_templates, task_label


def build_templates_tab(app) -> None:
    top = ttk.Frame(app.templates_tab)
    top.pack(fill="x")
    ttk.Label(top, text="Vorlagen", style="Header.TLabel").grid(row=0, column=0, sticky="w")
    button_row = ttk.Frame(top)
    button_row.grid(row=0, column=1, sticky="e")
    ttk.Button(button_row, text="Neu", style="Accent.TButton", command=app.add_template_dialog).pack(side="left")
    ttk.Button(button_row, text="Bearbeiten", command=app.edit_selected_template).pack(side="left", padx=8)
    ttk.Button(button_row, text="Verwenden", command=app.use_selected_template).pack(side="left")
    ttk.Button(button_row, text="Löschen", command=app.delete_selected_template).pack(side="left", padx=8)
    top.columnconfigure(0, weight=1)

    app.template_tree = ttk.Treeview(
        app.templates_tab,
        columns=("project", "title", "status", "priority", "tags", "recur"),
        show="headings",
        height=18,
    )
    for column, heading, width in [
        ("project", "Projekt", 140),
        ("title", "Titel", 220),
        ("status", "Status", 90),
        ("priority", "Prio", 60),
        ("tags", "Tags", 160),
        ("recur", "Wiederholung", 100),
    ]:
        app.template_tree.heading(column, text=heading)
        app.template_tree.column(column, width=width, anchor="w")
    app.template_tree.pack(fill="both", expand=True, pady=(10, 0))
    app.template_tree.bind("<<TreeviewSelect>>", lambda _: app.update_active_template())
    app.template_tree.bind("<Double-1>", lambda _: app.use_selected_template())


def refresh_templates(app) -> None:
    for row in app.template_tree.get_children():
        app.template_tree.delete(row)
    projects = {project["id"]: project["name"] for project in list_projects()}
    for template in list_templates():
        app.template_tree.insert(
            "",
            "end",
            iid=str(template["id"]),
            values=(
                projects.get(template["project_id"], "-") if template["project_id"] else "-",
                template["title"],
                task_label(template["status"]),
                template["priority"],
                template["tags"] or "-",
                template["recurrence_days"] or "-",
            ),
        )


def selected_template_id(app) -> int | None:
    selection = app.template_tree.selection()
    return int(selection[0]) if selection else None


def update_active_template(app) -> None:
    selected = app.template_tree.selection()
    app.active_template_id = int(selected[0]) if selected else None
