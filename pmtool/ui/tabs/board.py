from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pmtool.core import list_tasks


def build_board_tab(app) -> None:
    ttk.Label(app.board_tab, text="Kanban", style="Header.TLabel").pack(anchor="w")
    board = ttk.Frame(app.board_tab)
    board.pack(fill="both", expand=True, pady=(10, 0))
    board.columnconfigure(0, weight=1)
    board.columnconfigure(1, weight=1)
    board.columnconfigure(2, weight=1)
    board.columnconfigure(3, weight=1)

    app.board_lists = {}
    for index, (title, status) in enumerate(
        [("Offen", "open"), ("In Arbeit", "in_progress"), ("Blockiert", "blocked"), ("Erledigt", "done")]
    ):
        column = ttk.Frame(board, padding=8)
        column.grid(row=0, column=index, sticky="nsew", padx=6)
        ttk.Label(column, text=title, style="Subheader.TLabel").pack(anchor="w")
        listbox = tk.Listbox(column, height=22, activestyle="none", exportselection=False)
        listbox.pack(fill="both", expand=True, pady=(8, 0))
        listbox.bind("<Double-1>", lambda event, s=status: app.edit_task_from_board(s))
        app.board_lists[status] = listbox
        if not hasattr(app, "listboxes"):
            app.listboxes = []
        app.listboxes.append(listbox)


def refresh_board(app) -> None:
    for status, listbox in app.board_lists.items():
        listbox.delete(0, tk.END)
        for task in list_tasks(status=status, include_done=True):
            listbox.insert(tk.END, f'{task["id"]}: {task["title"]}')
