from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pmtool.remote_core import format_date, list_next_tasks, list_projects, project_label, task_dashboard_counts, task_label


def build_dashboard_tab(app) -> None:
    cards = ttk.Frame(app.dashboard_tab)
    cards.pack(fill="x")
    app._make_card(cards, "Projekte", "card_projects")
    app._make_card(cards, "Offen", "card_open")
    app._make_card(cards, "Heute", "card_today")
    app._make_card(cards, "Diese Woche", "card_week")
    app._make_card(cards, "Überfällig", "card_overdue")
    app._make_card(cards, "Blockiert", "card_blocked")

    lower = ttk.PanedWindow(app.dashboard_tab, orient=tk.HORIZONTAL)
    lower.pack(fill="both", expand=True, pady=(14, 0))

    next_frame = ttk.Frame(lower, padding=10)
    review_frame = ttk.Frame(lower, padding=10)
    lower.add(next_frame, weight=2)
    lower.add(review_frame, weight=1)

    ttk.Label(next_frame, text="Nächste Aufgaben", style="Header.TLabel").pack(anchor="w")
    app.dashboard_next = ttk.Treeview(
        next_frame,
        columns=("project", "title", "due", "status"),
        show="headings",
        height=14,
    )
    for column, heading, width in [
        ("project", "Projekt", 180),
        ("title", "Titel", 330),
        ("due", "Fällig", 90),
        ("status", "Status", 90),
    ]:
        app.dashboard_next.heading(column, text=heading)
        app.dashboard_next.column(column, width=width, anchor="w")
    app.dashboard_next.pack(fill="both", expand=True, pady=(8, 0))
    app.dashboard_next.bind("<Double-1>", lambda _: app.open_task_from_tree(app.dashboard_next))

    ttk.Label(review_frame, text="Projekt-Review", style="Header.TLabel").pack(anchor="w")
    app.dashboard_projects = ttk.Treeview(
        review_frame,
        columns=("status", "goal", "review"),
        show="headings",
        height=14,
    )
    for column, heading, width in [
        ("status", "Status", 90),
        ("goal", "Ziel", 220),
        ("review", "Review", 100),
    ]:
        app.dashboard_projects.heading(column, text=heading)
        app.dashboard_projects.column(column, width=width, anchor="w")
    app.dashboard_projects.pack(fill="both", expand=True, pady=(8, 0))


def refresh_dashboard(app) -> None:
    counts = task_dashboard_counts()
    projects = getattr(app, "_cached_projects", None) or list_projects()
    app.card_projects.configure(text=str(len(projects)))
    app.card_open.configure(text=str(counts["open"] + counts["in_progress"]))
    app.card_today.configure(text=str(counts["today"]))
    app.card_week.configure(text=str(counts["week"]))
    app.card_overdue.configure(text=str(counts["overdue"]))
    app.card_blocked.configure(text=str(counts["blocked"]))

    for row in app.dashboard_next.get_children():
        app.dashboard_next.delete(row)
    for task in list_next_tasks(limit=8):
        app.dashboard_next.insert(
            "",
            "end",
            iid=str(task["id"]),
            values=(
                task["project_name"] or "-",
                task["title"],
                format_date(task["due_date"]),
                task_label(task["status"]),
            ),
        )

    for row in app.dashboard_projects.get_children():
        app.dashboard_projects.delete(row)
    for project in projects:
        app.dashboard_projects.insert(
            "",
            "end",
            iid=str(project["id"]),
            values=(
                project_label(project["status"]),
                project["goal"] or "-",
                project["next_review_date"] or "-",
            ),
        )
