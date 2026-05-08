from __future__ import annotations

from tkinter import ttk


def build_backup_tab(app) -> None:
    ttk.Label(app.backup_tab, text="Backup & Import", style="Header.TLabel").pack(anchor="w")
    box = ttk.Frame(app.backup_tab, padding=16)
    box.pack(fill="x", pady=(10, 0))
    ttk.Button(box, text="JSON exportieren", style="Accent.TButton", command=app.export_json_dialog).grid(
        row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8)
    )
    ttk.Button(box, text="JSON importieren", command=app.import_json_dialog).grid(
        row=0, column=1, sticky="w", padx=(0, 8), pady=(0, 8)
    )
    ttk.Button(box, text="CSV exportieren", command=app.export_csv_dialog).grid(
        row=1, column=0, sticky="w", padx=(0, 8)
    )
    ttk.Button(box, text="CSV importieren", command=app.import_csv_dialog).grid(
        row=1, column=1, sticky="w", padx=(0, 8)
    )
    ttk.Label(
        box,
        text="Daten liegen lokal in app.db. Backups sichern Projekte, Aufgaben, Notizen, Verlauf, Vorlagen und Meilensteine.",
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(16, 0))
