from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pmtool.ui.dialogs import DateInput


def build_reports_tab(app) -> None:
    container = ttk.PanedWindow(app.reports_tab, orient=tk.HORIZONTAL)
    container.pack(fill="both", expand=True)

    left_host = ttk.Frame(container)
    left_canvas = tk.Canvas(left_host, highlightthickness=0)
    left_scrollbar = ttk.Scrollbar(left_host, orient="vertical", command=left_canvas.yview)
    left_canvas.configure(yscrollcommand=left_scrollbar.set)
    left_scrollbar.pack(side="right", fill="y")
    left_canvas.pack(side="left", fill="both", expand=True)

    left = ttk.Frame(left_canvas, padding=10)
    left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")

    def _sync_left_scrollregion(_event=None) -> None:
        left_canvas.configure(scrollregion=left_canvas.bbox("all"))

    def _sync_left_width(event) -> None:
        left_canvas.itemconfigure(left_window, width=event.width)

    def _scroll_left_with_mousewheel(event) -> str:
        left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    left.bind("<Configure>", _sync_left_scrollregion)
    left_canvas.bind("<Configure>", _sync_left_width)
    left_canvas.bind("<Enter>", lambda _e: left_canvas.bind_all("<MouseWheel>", _scroll_left_with_mousewheel))
    left_canvas.bind("<Leave>", lambda _e: left_canvas.unbind_all("<MouseWheel>"))

    right = ttk.Frame(container, padding=10)
    container.add(left_host, weight=2)
    container.add(right, weight=3)

    ttk.Label(left, text="Wochenbericht", style="Header.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
    ttk.Label(
        left,
        text="Generiert das feste Berichtstemplate und speichert es als .md Datei.",
        style="Subheader.TLabel",
    ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 10))

    row = 2
    ttk.Label(left, text="Projekt").grid(row=row, column=0, sticky="w")
    app.report_project_combo = ttk.Combobox(
        left,
        textvariable=app.report_project_var,
        state="readonly",
        values=["Projekt wählen"],
    )
    app.report_project_combo.grid(row=row, column=1, columnspan=2, sticky="we", padx=(8, 16))
    app.report_project_combo.bind("<<ComboboxSelected>>", lambda _: app.load_report_project_tasks())
    ttk.Button(left, text="Aufgaben laden", command=app.load_report_project_tasks).grid(row=row, column=3, sticky="e")
    row += 1

    ttk.Label(left, text="Projektaufgaben (Mehrfachauswahl)").grid(row=row, column=0, sticky="w", pady=(8, 0))
    app.report_tasks_listbox = tk.Listbox(left, selectmode="extended", height=7)
    app.report_tasks_listbox.grid(row=row, column=1, columnspan=3, sticky="we", padx=(8, 0), pady=(8, 0))
    if not hasattr(app, "listboxes"):
        app.listboxes = []
    app.listboxes.append(app.report_tasks_listbox)
    row += 1

    task_actions = ttk.Frame(left)
    task_actions.grid(row=row, column=1, columnspan=3, sticky="w", padx=(8, 0), pady=(6, 0))
    ttk.Button(task_actions, text="Ausgewählte hinzufügen", command=app.autofill_report_from_project_tasks).pack(side="left")
    ttk.Button(task_actions, text="Auswahl löschen", command=lambda: app.report_tasks_listbox.selection_clear(0, tk.END)).pack(side="left", padx=8)
    ttk.Button(task_actions, text="Alle", command=app.select_all_report_tasks).pack(side="left")
    ttk.Button(task_actions, text="Invertieren", command=app.invert_report_task_selection).pack(side="left", padx=8)
    ttk.Button(task_actions, text="Nur Erledigt", command=app.select_done_report_tasks).pack(side="left")
    ttk.Button(task_actions, text="Nur Offen", command=app.select_open_report_tasks).pack(side="left", padx=8)
    row += 1

    ttk.Label(left, text="Datum").grid(row=row, column=0, sticky="w")
    DateInput(left, app.report_date_var, picker_title="Berichtsdatum wählen").grid(row=row, column=1, sticky="we", padx=(8, 16))
    ttk.Button(left, text="Heute", command=app.fill_weekly_report_today).grid(row=row, column=2, sticky="w")
    row += 1

    ttk.Label(left, text="Status").grid(row=row, column=0, sticky="w", pady=(8, 0))
    app.report_status_combo = ttk.Combobox(
        left,
        textvariable=app.report_status_var,
        state="readonly",
        values=["", "Im Plan", "Im Verzug", "Schneller als geplant"],
        width=28,
    )
    app.report_status_combo.grid(row=row, column=1, columnspan=2, sticky="we", padx=(8, 16), pady=(8, 0))
    row += 1

    ttk.Label(left, text="Geplant").grid(row=row, column=0, sticky="nw", pady=(8, 0))
    app.report_planned_items_frame = ttk.Frame(left)
    app.report_planned_items_frame.grid(row=row, column=1, columnspan=3, sticky="we", padx=(8, 0), pady=(8, 0))
    row += 1

    ttk.Label(left, text="Erreicht").grid(row=row, column=0, sticky="nw", pady=(8, 0))
    app.report_achieved_items_frame = ttk.Frame(left)
    app.report_achieved_items_frame.grid(row=row, column=1, columnspan=3, sticky="we", padx=(8, 0), pady=(8, 0))
    row += 1

    ttk.Label(left, text="Nicht Erreicht").grid(row=row, column=0, sticky="nw", pady=(8, 0))
    app.report_not_achieved_items_frame = ttk.Frame(left)
    app.report_not_achieved_items_frame.grid(row=row, column=1, columnspan=3, sticky="we", padx=(8, 0), pady=(8, 0))
    row += 1

    ttk.Label(left, text="Gegenmaßnahmen bei Verzug").grid(row=row, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(left, textvariable=app.report_delay1_var).grid(row=row, column=1, columnspan=3, sticky="we", padx=(8, 0), pady=(8, 0))
    row += 1
    ttk.Entry(left, textvariable=app.report_delay2_var).grid(row=row, column=1, columnspan=3, sticky="we", padx=(8, 0), pady=(4, 0))
    row += 1

    ttk.Label(
        left,
        text="Risiken werden automatisch aus dem gewählten Projekt und den ausgewählten Aufgaben übernommen.",
        style="Subheader.TLabel",
    ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 0))
    row += 1

    ttk.Label(left, text="Nächster Meilenstein").grid(row=row, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(left, textvariable=app.report_milestone_var).grid(row=row, column=1, sticky="we", padx=(8, 8), pady=(8, 0))
    ttk.Label(left, text="Datum").grid(row=row, column=2, sticky="w", pady=(8, 0))
    DateInput(left, app.report_milestone_date_var, picker_title="Meilensteindatum wählen").grid(row=row, column=3, sticky="we", pady=(8, 0))
    row += 1

    ttk.Label(
        left,
        text="Meilenstein wird automatisch aus Datum und Projekt-Meilensteinen ermittelt.",
        style="Subheader.TLabel",
    ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(2, 0))
    row += 1

    actions = ttk.Frame(left)
    actions.grid(row=row, column=0, columnspan=4, sticky="we", pady=(14, 0))
    ttk.Button(actions, text="Vorschau aktualisieren", style="Accent.TButton", command=app.preview_weekly_report).pack(side="left")
    ttk.Button(actions, text="Als .md speichern", command=app.save_weekly_report).pack(side="left", padx=8)
    ttk.Button(actions, text="Zurücksetzen", command=app.clear_weekly_report_form).pack(side="left")

    ttk.Label(left, textvariable=app.report_status_message_var).grid(row=row + 1, column=0, columnspan=4, sticky="w", pady=(8, 0))

    for idx in range(4):
        left.columnconfigure(idx, weight=1 if idx in (1, 3) else 0)

    ttk.Label(right, text="Markdown Vorschau", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        right,
        text="Die Vorschau entspricht exakt dem gespeicherten Inhalt.",
        style="Subheader.TLabel",
    ).pack(anchor="w", pady=(2, 8))

    preview_container = ttk.Frame(right)
    preview_container.pack(fill="both", expand=True)

    preview_scrollbar = ttk.Scrollbar(preview_container, orient="vertical")
    app.report_preview_text = tk.Text(preview_container, wrap="word", yscrollcommand=preview_scrollbar.set)
    preview_scrollbar.configure(command=app.report_preview_text.yview)

    app.report_preview_text.pack(side="left", fill="both", expand=True)
    preview_scrollbar.pack(side="right", fill="y")
    app.report_preview_text.configure(state="disabled")

    if not hasattr(app, "text_widgets"):
        app.text_widgets = []
    app.text_widgets.append(app.report_preview_text)

    app.render_all_dynamic_report_sections()
