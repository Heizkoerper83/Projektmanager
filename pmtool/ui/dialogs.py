"""Graphical user interface for the local project management tool."""

from __future__ import annotations

import json
import calendar
import sqlite3
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from pmtool.core import (
    add_milestone,
    add_project,
    add_task,
    add_task_note,
    add_template,
    complete_task,
    create_task_from_template,
    delete_project,
    delete_task,
    delete_template,
    export_csv,
    export_json,
    format_date,
    get_connection,
    get_task,
    import_csv,
    import_json,
    init_db,
    list_milestones,
    list_next_tasks,
    list_projects,
    list_task_history,
    list_task_notes,
    delete_milestone,
    update_milestone,
    update_project,
    update_task,
    update_template,
    list_tasks,
    list_templates,
    normalize_energy_level,
    normalize_tags,
    parse_due_date,
    project_dashboard_counts,
    project_label,
    task_dashboard_counts,
    task_label,
)


TASK_STATUS_CHOICES = [
    ("Offen", "open"),
    ("In Arbeit", "in_progress"),
    ("Blockiert", "blocked"),
    ("Erledigt", "done"),
]
PROJECT_STATUS_CHOICES = [
    ("Aktiv", "active"),
    ("Pausiert", "paused"),
    ("Abgeschlossen", "done"),
]
ENERGY_CHOICES = [
    ("Niedrig", "low"),
    ("Mittel", "medium"),
    ("Hoch", "high"),
]
TASK_STATUS_VALUES = {label: value for label, value in TASK_STATUS_CHOICES}
PROJECT_STATUS_VALUES = {label: value for label, value in PROJECT_STATUS_CHOICES}
ENERGY_VALUES = {label: value for label, value in ENERGY_CHOICES}


def _split_multiline_items(value: str) -> list[str]:
    return [part.strip() for part in value.splitlines() if part.strip()]


def _normalize_risk_level(value: object, default: int = 3) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(5, level))


def _parse_int_or_default(value: object, default: int | None, *, placeholder: str | None = None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return default
    if placeholder is not None and text == placeholder:
        return default
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def _load_risk_rows(record: sqlite3.Row | None) -> list[dict[str, object]]:
    if not record:
        return []

    raw_json = str(record["risk_rows_json"] or "") if "risk_rows_json" in record.keys() else ""
    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            rows: list[dict[str, object]] = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                risk_text = str(item.get("risk", "")).strip()
                if not risk_text:
                    continue
                rows.append(
                    {
                        "risk": risk_text,
                        "countermeasure": str(item.get("countermeasure", "")).strip(),
                        "probability": _normalize_risk_level(item.get("probability", 3)),
                        "impact": _normalize_risk_level(item.get("impact", 3)),
                    }
                )
            if rows:
                return rows

    fallback_probability = _normalize_risk_level(record["risk_probability"] if "risk_probability" in record.keys() else 3)
    fallback_impact = _normalize_risk_level(record["risk_impact"] if "risk_impact" in record.keys() else 3)
    risks = _split_multiline_items(str(record["risk"] if "risk" in record.keys() else ""))
    countermeasures = _split_multiline_items(str(record["risk_countermeasure"] if "risk_countermeasure" in record.keys() else ""))
    count = max(len(risks), len(countermeasures))
    rows: list[dict[str, object]] = []
    for idx in range(count):
        risk_text = risks[idx] if idx < len(risks) else ""
        countermeasure = countermeasures[idx] if idx < len(countermeasures) else ""
        if not risk_text:
            continue
        rows.append(
            {
                "risk": risk_text,
                "countermeasure": countermeasure,
                "probability": fallback_probability,
                "impact": fallback_impact,
            }
        )
    return rows


class DatePickerDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, title: str = "Datum auswählen", initial_date: date | None = None) -> None:
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.grab_set()
        self.resizable(False, False)
        self.result = None
        self._calendar = calendar.Calendar(firstweekday=0)
        self._current_date = initial_date or date.today()
        self._year_var = tk.IntVar(value=self._current_date.year)
        self._month_var = tk.IntVar(value=self._current_date.month)

        frame = ttk.Frame(self, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)

        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Button(header, text="<", width=3, command=self._previous_month).grid(row=0, column=0, sticky="w")
        self._month_label = ttk.Label(header, text="")
        self._month_label.grid(row=0, column=1, sticky="ew")
        ttk.Button(header, text=">", width=3, command=self._next_month).grid(row=0, column=2, sticky="e")

        controls = ttk.Frame(frame)
        controls.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        ttk.Label(controls, text="Jahr").pack(side="left")
        year_spin = ttk.Spinbox(controls, from_=1900, to=2100, width=7, textvariable=self._year_var, command=self._render_calendar)
        year_spin.pack(side="left", padx=(6, 12))
        ttk.Label(controls, text="Monat").pack(side="left")
        month_spin = ttk.Spinbox(controls, from_=1, to=12, width=5, textvariable=self._month_var, command=self._render_calendar)
        month_spin.pack(side="left", padx=(6, 0))
        self._year_var.trace_add("write", lambda *_: self._render_calendar())
        self._month_var.trace_add("write", lambda *_: self._render_calendar())

        self._days_frame = ttk.Frame(frame)
        self._days_frame.grid(row=2, column=0, sticky="nsew")

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="Heute", command=self._select_today).pack(side="left")
        ttk.Button(buttons, text="Leer", command=lambda: self.finish("")).pack(side="left", padx=8)
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="right")

        self.bind("<Escape>", lambda _event: self.destroy())
        self._render_calendar()

    def finish(self, result: str) -> None:
        self.result = result
        self.destroy()

    def _previous_month(self) -> None:
        year = int(self._year_var.get())
        month = int(self._month_var.get()) - 1
        if month < 1:
            month = 12
            year -= 1
        self._year_var.set(year)
        self._month_var.set(month)

    def _next_month(self) -> None:
        year = int(self._year_var.get())
        month = int(self._month_var.get()) + 1
        if month > 12:
            month = 1
            year += 1
        self._year_var.set(year)
        self._month_var.set(month)

    def _select_today(self) -> None:
        self.finish(date.today().isoformat())

    def _select_day(self, selected_date: date) -> None:
        self.finish(selected_date.isoformat())

    def _render_calendar(self) -> None:
        year = int(self._year_var.get())
        month = int(self._month_var.get())
        if month < 1:
            month = 1
            self._month_var.set(month)
        elif month > 12:
            month = 12
            self._month_var.set(month)
        self._month_label.config(text=f"{calendar.month_name[month]} {year}")

        for child in self._days_frame.winfo_children():
            child.destroy()

        week_names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        for column, label in enumerate(week_names):
            ttk.Label(self._days_frame, text=label).grid(row=0, column=column, padx=2, pady=(0, 4))

        month_days = self._calendar.monthdayscalendar(year, month)
        for row_index, week in enumerate(month_days, start=1):
            for column_index, day_number in enumerate(week):
                if day_number == 0:
                    ttk.Label(self._days_frame, text=" ", width=3).grid(row=row_index, column=column_index, padx=2, pady=2)
                    continue
                chosen_date = date(year, month, day_number)
                is_today = chosen_date == date.today()
                text = str(day_number)
                button = ttk.Button(self._days_frame, text=text, width=3, command=lambda current=chosen_date: self._select_day(current))
                if is_today:
                    button.state(["!disabled"])
                button.grid(row=row_index, column=column_index, padx=2, pady=2)


class PlaceholderEntry(tk.Entry):
    def __init__(
        self,
        master: tk.Misc,
        *,
        placeholder: str,
        textvariable: tk.StringVar | None = None,
        width: int = 20,
        show: str | None = None,
        validator: callable | None = None,
    ) -> None:
        self._placeholder = placeholder
        self._show_char = show or ""
        self._placeholder_active = False
        self._placeholder_fg = "#7a8699"
        super().__init__(master, textvariable=textvariable, width=width)
        if show:
            self.configure(show=show)
        self._validator = validator
        self.bind("<FocusIn>", self._clear_placeholder)
        self.bind("<FocusOut>", self._apply_placeholder)
        if textvariable is not None:
            textvariable.trace_add("write", lambda *_: self._sync_from_variable())
        self._apply_placeholder()

    def _sync_from_variable(self) -> None:
        if self._placeholder_active:
            return
        if not self.get().strip():
            self._apply_placeholder()

    def _apply_placeholder(self, *_args) -> None:
        if self.focus_get() == self:
            return
        current = self.get().strip()
        if current and current != self._placeholder:
            # run validator if provided
            if self._validator is not None:
                try:
                    valid, msg = self._validator(current)
                except Exception:
                    valid, msg = False, "Ungültige Eingabe"
                if not valid:
                    try:
                        messagebox.showwarning("Ungültige Eingabe", msg, parent=self.winfo_toplevel())
                    except Exception:
                        pass
                    # return focus to this widget shortly after focusout
                    self.after(1, lambda: self.focus_set())
                    return
            self._placeholder_active = False
            self.configure(fg="black")
            if self._show_char:
                self.configure(show=self._show_char)
            return
        self._placeholder_active = True
        self.configure(fg=self._placeholder_fg)
        if self._show_char:
            self.configure(show="")
        self.delete(0, tk.END)
        self.insert(0, self._placeholder)

    def _clear_placeholder(self, *_args) -> None:
        if not self._placeholder_active:
            return
        self._placeholder_active = False
        self.delete(0, tk.END)
        self.configure(fg="black")
        if self._show_char:
            self.configure(show=self._show_char)

    def get_value(self) -> str:
        value = self.get().strip()
        if self._placeholder_active and value == self._placeholder:
            return ""
        return value


class NumericPlaceholderEntry(PlaceholderEntry):
    def __init__(
        self,
        master: tk.Misc,
        *,
        placeholder: str,
        textvariable: tk.StringVar | None = None,
        width: int = 20,
    ) -> None:
        # derive optional min/max from placeholder like "1-5"
        self._min = None
        self._max = None
        if isinstance(placeholder, str) and "-" in placeholder:
            try:
                parts = placeholder.split("-", 1)
                self._min = int(parts[0])
                self._max = int(parts[1])
            except Exception:
                self._min = None
                self._max = None
        def _validator(value: str) -> tuple[bool, str]:
            text = value.strip()
            if not text:
                return True, ""
            try:
                num = int(text)
            except Exception:
                return False, "Nur Zahlen erlaubt"
            if self._min is not None and num < self._min:
                return False, f"Wert muss mindestens {self._min} sein"
            if self._max is not None and num > self._max:
                return False, f"Wert darf höchstens {self._max} sein"
            return True, ""
        super().__init__(master, placeholder=placeholder, textvariable=textvariable, width=width, validator=_validator)
        self.bind("<KeyPress>", self._filter_numeric_input, add=True)

    def _filter_numeric_input(self, event: tk.Event) -> str | None:
        if self._placeholder_active:
            self._clear_placeholder()

        if event.state & 0x4 and event.keysym.lower() in {"a", "c", "v", "x"}:
            return None

        allowed_keys = {
            "BackSpace",
            "Delete",
            "Left",
            "Right",
            "Home",
            "End",
            "Tab",
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
            "Escape",
            "Return",
        }
        if event.keysym in allowed_keys:
            return None

        if event.char.isdigit() or event.char == "":
            return None

        self.bell()
        return "break"


class TogglePasswordEntry(ttk.Frame):
    """Password entry with toggle visibility button (eye icon)."""
    def __init__(self, master: tk.Misc, variable: tk.StringVar | None = None, width: int = 40) -> None:
        super().__init__(master)
        self.variable = variable or tk.StringVar()
        self._password_visible = False
        
        self.entry = PlaceholderEntry(self, placeholder="mind. 8 Zeichen", textvariable=self.variable, width=width, show="•")
        self.entry.pack(side="left", fill="x", expand=True)
        
        self.toggle_button = ttk.Button(self, text="👁", width=2, command=self._toggle_visibility)
        self.toggle_button.pack(side="left", padx=(4, 0))
    
    def _toggle_visibility(self) -> None:
        """Toggle password visibility."""
        self._password_visible = not self._password_visible
        if self._password_visible:
            self.entry.configure(show="")
            self.toggle_button.config(text="🔒")
        else:
            self.entry.configure(show="•")
            self.toggle_button.config(text="👁")
    
    def get_value(self) -> str:
        """Get password value."""
        return self.entry.get_value()
    
    def get(self) -> str:
        """Get password value (alias)."""
        return self.entry.get()
    
    def delete(self, start: int, end: int | str) -> None:
        """Delete password characters."""
        return self.entry.delete(start, end)
    
    def focus(self) -> None:
        """Focus the password entry."""
        return self.entry.focus()


class DateInput(ttk.Frame):
    def __init__(self, master: tk.Misc, variable: tk.StringVar, picker_title: str = "Datum auswählen", allow_clear: bool = True, width: int = 12) -> None:
        super().__init__(master)
        self.variable = variable
        self.picker_title = picker_title
        self.allow_clear = allow_clear

        def _date_validator(value: str) -> tuple[bool, str]:
            txt = value.strip()
            if not txt:
                return True, ""
            try:
                parse_due_date(txt)
                return True, ""
            except Exception as exc:
                return False, "Ungültiges Datum. Erwartet: YYYY-MM-DD"

        self.entry = PlaceholderEntry(self, placeholder="YYYY-MM-DD", textvariable=variable, width=width, validator=_date_validator)
        self.entry.pack(side="left", fill="x", expand=True)
        ttk.Button(self, text="Kalender", command=self._open_picker).pack(side="left", padx=(6, 0))
        if allow_clear:
            ttk.Button(self, text="Leer", command=lambda: self.variable.set("")).pack(side="left", padx=(6, 0))

    def _open_picker(self) -> None:
        current_value = self.variable.get().strip()
        try:
            initial_date = date.fromisoformat(current_value) if current_value else date.today()
        except ValueError:
            initial_date = date.today()
        dialog = DatePickerDialog(self.winfo_toplevel(), self.picker_title, initial_date=initial_date)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self.variable.set(dialog.result)
        self.entry.icursor(tk.END)


class BaseDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, title: str) -> None:
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.grab_set()
        self.resizable(False, False)
        self.result: dict[str, object] | None = None
        self.columnconfigure(0, weight=1)

    def finish(self, result: dict[str, object]) -> None:
        self.result = result
        self.destroy()


class ProjectDialog(BaseDialog):
    def __init__(self, master: tk.Misc, title: str, project: sqlite3.Row | None = None) -> None:
        super().__init__(master, title)
        initial_status = project_label(project["status"]) if project else "Aktiv"
        self.name_var = tk.StringVar(value=project["name"] if project else "")
        self.team_var = tk.StringVar(value=project["team"] if project else "")
        self.status_var = tk.StringVar(value=initial_status)
        self.review_var = tk.StringVar(value=project["next_review_date"] if project and project["next_review_date"] else "")
        self.project_risk_rows: list[tuple[tk.StringVar, tk.StringVar, tk.StringVar, tk.StringVar]] = []

        frame = ttk.Frame(self, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        self._add_label(frame, "Name", 0, required=True)
        PlaceholderEntry(frame, placeholder="Projektname", textvariable=self.name_var, width=42).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        self._add_label(frame, "Status", 1)
        ttk.Combobox(frame, textvariable=self.status_var, values=[label for label, _ in PROJECT_STATUS_CHOICES], state="readonly", width=39).grid(row=1, column=1, sticky="ew", pady=(0, 8))

        self._add_label(frame, "Projektteam", 2)
        PlaceholderEntry(frame, placeholder="z.B. Team A", textvariable=self.team_var, width=42).grid(row=2, column=1, sticky="ew", pady=(0, 8))

        self._add_label(frame, "Review", 3)
        DateInput(frame, self.review_var, picker_title="Review-Datum wählen").grid(row=3, column=1, sticky="ew", pady=(0, 8))

        self._add_label(frame, "Beschreibung", 4)
        self.description_text = tk.Text(frame, width=48, height=4, wrap="word")
        self.description_text.grid(row=4, column=1, sticky="ew", pady=(0, 8))
        if project:
            self.description_text.insert("1.0", project["description"])

        self._add_label(frame, "Ziel", 5)
        self.goal_text = tk.Text(frame, width=48, height=4, wrap="word")
        self.goal_text.grid(row=5, column=1, sticky="ew", pady=(0, 8))
        if project:
            self.goal_text.insert("1.0", project["goal"])

        self._add_label(frame, "Meilenstein", 6)
        self.milestone_text = tk.Text(frame, width=48, height=3, wrap="word")
        self.milestone_text.grid(row=6, column=1, sticky="ew")
        if project:
            self.milestone_text.insert("1.0", project["milestone"])

        self._add_label(frame, "Risiken", 7)
        self.project_risks_frame = ttk.Frame(frame)
        self.project_risks_frame.grid(row=7, column=1, sticky="ew", pady=(8, 8))
        self.project_risks_frame.columnconfigure(0, weight=3)
        self.project_risks_frame.columnconfigure(3, weight=3)

        for row in _load_risk_rows(project):
            self._add_project_risk_row(
                risk=str(row["risk"]),
                countermeasure=str(row["countermeasure"]),
                probability=int(row["probability"]),
                impact=int(row["impact"]),
            )
        self._ensure_trailing_project_risk_row()

        self._add_label(frame, "Gegenmaßnahmen", 8)
        ttk.Label(frame, text="Pro Risiko kann eine eigene Gegenmaßnahme gepflegt werden.", style="Subheader.TLabel").grid(
            row=8,
            column=1,
            sticky="w",
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=9, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Speichern", command=self._submit).grid(row=0, column=1)
        self.bind("<Escape>", lambda _: self.destroy())

    def _add_label(self, frame: ttk.Frame, text: str, row: int, required: bool = False) -> None:
        label_text = f"{text} *" if required else text
        ttk.Label(frame, text=label_text).grid(row=row, column=0, sticky="w", pady=(0, 8))

    def _add_project_risk_row(self, risk: str = "", countermeasure: str = "", probability: int | str = "", impact: int | str = "") -> None:
        risk_var = tk.StringVar(value=risk)
        countermeasure_var = tk.StringVar(value=countermeasure)
        probability_var = tk.StringVar(value=str(probability) if str(probability).strip() else "")
        impact_var = tk.StringVar(value=str(impact) if str(impact).strip() else "")
        self.project_risk_rows.append((risk_var, probability_var, impact_var, countermeasure_var))
        self._render_project_risk_rows()

    def _remove_project_risk_row(self, index: int) -> None:
        if index < 0 or index >= len(self.project_risk_rows):
            return
        self.project_risk_rows.pop(index)
        self._render_project_risk_rows()
        self._ensure_trailing_project_risk_row()

    def _on_project_risk_changed(self, *_args) -> None:
        self._ensure_trailing_project_risk_row()

    def _ensure_trailing_project_risk_row(self) -> None:
        if not self.project_risk_rows:
            self._add_project_risk_row()
            return

        while len(self.project_risk_rows) > 1:
            last_risk, _last_probability, _last_impact, last_countermeasure = self.project_risk_rows[-1]
            prev_risk, _prev_probability, _prev_impact, prev_countermeasure = self.project_risk_rows[-2]
            if (last_risk.get().strip() or last_countermeasure.get().strip()) or not (prev_risk.get().strip() or prev_countermeasure.get().strip()):
                break
            self.project_risk_rows.pop()
            self._render_project_risk_rows()

        last_risk, _last_probability, _last_impact, last_countermeasure = self.project_risk_rows[-1]
        if last_risk.get().strip() or last_countermeasure.get().strip():
            self._add_project_risk_row()

    def _render_project_risk_rows(self) -> None:
        for child in self.project_risks_frame.winfo_children():
            child.destroy()

        ttk.Label(self.project_risks_frame, text="Risiko").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(self.project_risks_frame, text="Wahrsch.").grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(self.project_risks_frame, text="Ausmaß").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Label(self.project_risks_frame, text="Gegenmaßnahme").grid(row=0, column=3, sticky="w", padx=(0, 8))
        ttk.Button(self.project_risks_frame, text="+", width=3, command=lambda: self._add_project_risk_row()).grid(row=0, column=4, sticky="e")

        for idx, (risk_var, probability_var, impact_var, countermeasure_var) in enumerate(self.project_risk_rows, start=1):
            risk_entry = ttk.Entry(self.project_risks_frame, textvariable=risk_var, width=28)
            risk_entry.grid(row=idx, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))
            risk_entry.bind("<FocusOut>", self._on_project_risk_changed)
            risk_entry.bind("<Return>", self._on_project_risk_changed)

            NumericPlaceholderEntry(self.project_risks_frame, placeholder="1-5", textvariable=probability_var, width=6).grid(row=idx, column=1, sticky="w", padx=(0, 8), pady=(4, 0))

            NumericPlaceholderEntry(self.project_risks_frame, placeholder="1-5", textvariable=impact_var, width=6).grid(row=idx, column=2, sticky="w", padx=(0, 8), pady=(4, 0))

            countermeasure_entry = ttk.Entry(self.project_risks_frame, textvariable=countermeasure_var, width=28)
            countermeasure_entry.grid(row=idx, column=3, sticky="ew", padx=(0, 8), pady=(4, 0))
            countermeasure_entry.bind("<FocusOut>", self._on_project_risk_changed)
            countermeasure_entry.bind("<Return>", self._on_project_risk_changed)

            ttk.Button(
                self.project_risks_frame,
                text="-",
                width=3,
                command=lambda row_index=idx - 1: self._remove_project_risk_row(row_index),
            ).grid(row=idx, column=4, sticky="e", pady=(4, 0))

    def _submit(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Fehler", "Der Projektname darf nicht leer sein.", parent=self)
            return
        review_text = self.review_var.get().strip()
        if review_text:
            parse_due_date(review_text)
        risk_rows: list[dict[str, object]] = []
        for risk_var, probability_var, impact_var, countermeasure_var in self.project_risk_rows:
            risk_text = risk_var.get().strip()
            if not risk_text:
                continue
            probability = _parse_int_or_default(probability_var.get(), 3, placeholder="1-5")
            impact = _parse_int_or_default(impact_var.get(), 3, placeholder="1-5")
            if probability is None or impact is None:
                messagebox.showerror("Fehler", "Jedes Risiko braucht Wahrscheinlichkeit und Ausmaß als Zahl 1 bis 5.", parent=self)
                return
            if probability < 1 or probability > 5 or impact < 1 or impact > 5:
                messagebox.showerror("Fehler", "Wahrscheinlichkeit und Ausmaß müssen zwischen 1 und 5 liegen.", parent=self)
                return
            risk_rows.append(
                {
                    "risk": risk_text,
                    "probability": probability,
                    "impact": impact,
                    "countermeasure": countermeasure_var.get().strip(),
                }
            )

        legacy_probability = max((int(row["probability"]) for row in risk_rows), default=3)
        legacy_impact = max((int(row["impact"]) for row in risk_rows), default=3)
        self.finish(
            {
                "name": name,
                "team": self.team_var.get().strip(),
                "description": self.description_text.get("1.0", "end").strip(),
                "goal": self.goal_text.get("1.0", "end").strip(),
                "milestone": self.milestone_text.get("1.0", "end").strip(),
                "risk": "\n".join(str(row["risk"]) for row in risk_rows),
                "risk_rows": risk_rows,
                "risk_probability": legacy_probability,
                "risk_impact": legacy_impact,
                "risk_weight": max(legacy_probability, legacy_impact),
                "risk_countermeasure": "\n".join(str(row["countermeasure"]) for row in risk_rows),
                "next_review_date": review_text or None,
                "status": PROJECT_STATUS_VALUES.get(self.status_var.get(), "active"),
            }
        )


class TaskDialog(BaseDialog):
    def __init__(self, master: tk.Misc, title: str, projects: list[sqlite3.Row], task: sqlite3.Row | None = None) -> None:
        super().__init__(master, title)
        self.projects = projects
        self.project_values = ["Keine Zuordnung"] + [f'{project["id"]}: {project["name"]}' for project in projects]
        self.status_var = tk.StringVar(value=self._task_status_label(task))
        self.project_var = tk.StringVar(value=self._task_project_label(task))
        self.priority_var = tk.StringVar(value=str(task["priority"] if task else ""))
        self.due_var = tk.StringVar(value=task["due_date"] if task and task["due_date"] else "")
        self.context_var = tk.StringVar(value=task["context"] if task else "")
        self.energy_var = tk.StringVar(value=self._energy_label(task))
        self.estimate_var = tk.StringVar(value=str(task["estimate_minutes"] if task and task["estimate_minutes"] else ""))
        self.tags_var = tk.StringVar(value=task["tags"] if task else "")
        self.recurrence_var = tk.StringVar(value=str(task["recurrence_days"] if task and task["recurrence_days"] else ""))
        self.task_risk_rows: list[tuple[tk.StringVar, tk.StringVar, tk.StringVar, tk.StringVar]] = []

        frame = ttk.Frame(self, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        self._add_entry(frame, "Titel", 0, "title", required=True)
        self.title_var = tk.StringVar(value=task["title"] if task else "")
        self._bind_entry(frame, self.title_var, 0)

        self._add_combo(frame, "Projekt", 1, self.project_values, self.project_var)
        self._add_combo(frame, "Status", 2, [label for label, _ in TASK_STATUS_CHOICES], self.status_var)
        PlaceholderEntry(frame, placeholder="1-5", textvariable=self.priority_var, width=44).grid(row=3, column=1, sticky="ew", pady=(0, 8))
        self._add_entry(frame, "Fällig", 4, "due")
        DateInput(frame, self.due_var, picker_title="Fälligkeitsdatum wählen").grid(row=4, column=1, sticky="ew", pady=(0, 8))
        self._add_entry(frame, "Kontext", 5, "context")
        self._bind_entry(frame, self.context_var, 5)
        self._add_combo(frame, "Energie", 6, [label for label, _ in ENERGY_CHOICES], self.energy_var)
        self._add_entry(frame, "Schätzung", 7, "estimate")
        PlaceholderEntry(frame, placeholder="0", textvariable=self.estimate_var, width=44).grid(row=7, column=1, sticky="ew", pady=(0, 8))
        self._add_entry(frame, "Tags", 8, "tags")
        self._bind_entry(frame, self.tags_var, 8)
        self._add_entry(frame, "Wiederholung", 9, "recurrence")
        PlaceholderEntry(frame, placeholder="Tage", textvariable=self.recurrence_var, width=44).grid(row=9, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Risiken").grid(row=10, column=0, sticky="nw", pady=(0, 8))
        self.task_risks_frame = ttk.Frame(frame)
        self.task_risks_frame.grid(row=10, column=1, sticky="ew", pady=(0, 8))
        self.task_risks_frame.columnconfigure(0, weight=3)
        self.task_risks_frame.columnconfigure(3, weight=3)

        for row in _load_risk_rows(task):
            self._add_task_risk_row(
                risk=str(row["risk"]),
                countermeasure=str(row["countermeasure"]),
                probability=int(row["probability"]),
                impact=int(row["impact"]),
            )
        self._ensure_trailing_task_risk_row()

        ttk.Label(frame, text="Gegenmaßnahmen").grid(row=11, column=0, sticky="nw", pady=(0, 8))
        ttk.Label(frame, text="Pro Risiko kann eine eigene Gegenmaßnahme gepflegt werden.", style="Subheader.TLabel").grid(
            row=11,
            column=1,
            sticky="w",
            pady=(0, 8),
        )

        ttk.Label(frame, text="Blocker").grid(row=12, column=0, sticky="nw", pady=(0, 8))
        self.blocked_text = tk.Text(frame, width=52, height=3, wrap="word")
        self.blocked_text.grid(row=12, column=1, sticky="ew", pady=(0, 8))
        if task:
            self.blocked_text.insert("1.0", task["blocked_reason"])

        ttk.Label(frame, text="Details").grid(row=13, column=0, sticky="nw")
        self.details_text = tk.Text(frame, width=52, height=7, wrap="word")
        self.details_text.grid(row=13, column=1, sticky="ew")
        if task:
            self.details_text.insert("1.0", task["details"])

        buttons = ttk.Frame(frame)
        buttons.grid(row=14, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Speichern", command=self._submit).grid(row=0, column=1)
        self.bind("<Escape>", lambda _: self.destroy())

    def _task_status_label(self, task: sqlite3.Row | None) -> str:
        status = task["status"] if task else "open"
        return next((label for label, value in TASK_STATUS_CHOICES if value == status), "Offen")

    def _task_project_label(self, task: sqlite3.Row | None) -> str:
        if not task or task["project_id"] is None:
            return "Keine Zuordnung"
        return next((f'{project["id"]}: {project["name"]}' for project in self.projects if project["id"] == task["project_id"]), "Keine Zuordnung")

    def _energy_label(self, task: sqlite3.Row | None) -> str:
        energy = task["energy_level"] if task else "medium"
        return next((label for label, value in ENERGY_CHOICES if value == energy), "Mittel")

    def _add_entry(self, frame: ttk.Frame, text: str, row: int, _field: str, required: bool = False) -> None:
        label_text = f"{text} *" if required else text
        ttk.Label(frame, text=label_text).grid(row=row, column=0, sticky="w", pady=(0, 8))

    def _bind_entry(self, frame: ttk.Frame, variable: tk.StringVar, row: int) -> None:
        entry = ttk.Entry(frame, textvariable=variable, width=44)
        entry.grid(row=row, column=1, sticky="ew", pady=(0, 8))

    def _add_combo(self, frame: ttk.Frame, text: str, row: int, values: list[str], variable: tk.StringVar) -> None:
        ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", pady=(0, 8))
        ttk.Combobox(frame, textvariable=variable, values=values, state="readonly", width=41).grid(row=row, column=1, sticky="ew", pady=(0, 8))

    def _add_spin(self, frame: ttk.Frame, text: str, row: int, variable: tk.StringVar, minimum: int, maximum: int) -> None:
        ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", pady=(0, 8))
        PlaceholderEntry(frame, placeholder=f"{minimum}-{maximum}", textvariable=variable, width=8).grid(row=row, column=1, sticky="w", pady=(0, 8))

    def _add_task_risk_row(self, risk: str = "", countermeasure: str = "", probability: int | str = "", impact: int | str = "") -> None:
        risk_var = tk.StringVar(value=risk)
        countermeasure_var = tk.StringVar(value=countermeasure)
        probability_var = tk.StringVar(value=str(probability) if str(probability).strip() else "")
        impact_var = tk.StringVar(value=str(impact) if str(impact).strip() else "")
        self.task_risk_rows.append((risk_var, probability_var, impact_var, countermeasure_var))
        self._render_task_risk_rows()

    def _remove_task_risk_row(self, index: int) -> None:
        if index < 0 or index >= len(self.task_risk_rows):
            return
        self.task_risk_rows.pop(index)
        self._render_task_risk_rows()
        self._ensure_trailing_task_risk_row()

    def _on_task_risk_changed(self, *_args) -> None:
        self._ensure_trailing_task_risk_row()

    def _ensure_trailing_task_risk_row(self) -> None:
        if not self.task_risk_rows:
            self._add_task_risk_row()
            return

        while len(self.task_risk_rows) > 1:
            last_risk, _last_probability, _last_impact, last_countermeasure = self.task_risk_rows[-1]
            prev_risk, _prev_probability, _prev_impact, prev_countermeasure = self.task_risk_rows[-2]
            if (last_risk.get().strip() or last_countermeasure.get().strip()) or not (prev_risk.get().strip() or prev_countermeasure.get().strip()):
                break
            self.task_risk_rows.pop()
            self._render_task_risk_rows()

        last_risk, _last_probability, _last_impact, last_countermeasure = self.task_risk_rows[-1]
        if last_risk.get().strip() or last_countermeasure.get().strip():
            self._add_task_risk_row()

    def _render_task_risk_rows(self) -> None:
        for child in self.task_risks_frame.winfo_children():
            child.destroy()

        ttk.Label(self.task_risks_frame, text="Risiko").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(self.task_risks_frame, text="Wahrsch.").grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(self.task_risks_frame, text="Ausmaß").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Label(self.task_risks_frame, text="Gegenmaßnahme").grid(row=0, column=3, sticky="w", padx=(0, 8))
        ttk.Button(self.task_risks_frame, text="+", width=3, command=lambda: self._add_task_risk_row()).grid(row=0, column=4, sticky="e")

        for idx, (risk_var, probability_var, impact_var, countermeasure_var) in enumerate(self.task_risk_rows, start=1):
            risk_entry = ttk.Entry(self.task_risks_frame, textvariable=risk_var, width=30)
            risk_entry.grid(row=idx, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))
            risk_entry.bind("<FocusOut>", self._on_task_risk_changed)
            risk_entry.bind("<Return>", self._on_task_risk_changed)

            NumericPlaceholderEntry(self.task_risks_frame, placeholder="1-5", textvariable=probability_var, width=6).grid(row=idx, column=1, sticky="w", padx=(0, 8), pady=(4, 0))

            NumericPlaceholderEntry(self.task_risks_frame, placeholder="1-5", textvariable=impact_var, width=6).grid(row=idx, column=2, sticky="w", padx=(0, 8), pady=(4, 0))

            countermeasure_entry = ttk.Entry(self.task_risks_frame, textvariable=countermeasure_var, width=30)
            countermeasure_entry.grid(row=idx, column=3, sticky="ew", padx=(0, 8), pady=(4, 0))
            countermeasure_entry.bind("<FocusOut>", self._on_task_risk_changed)
            countermeasure_entry.bind("<Return>", self._on_task_risk_changed)

            ttk.Button(
                self.task_risks_frame,
                text="-",
                width=3,
                command=lambda row_index=idx - 1: self._remove_task_risk_row(row_index),
            ).grid(row=idx, column=4, sticky="e", pady=(4, 0))

    def _submit(self) -> None:
        title = self.title_var.get().strip()
        if not title:
            messagebox.showerror("Fehler", "Der Titel darf nicht leer sein.", parent=self)
            return
        due_text = self.due_var.get().strip()
        if due_text:
            parse_due_date(due_text)
        estimate_text = self.estimate_var.get().strip() or "0"
        recurrence_text = self.recurrence_var.get().strip()
        priority = _parse_int_or_default(self.priority_var.get(), 3, placeholder="1-5")
        estimate_minutes = _parse_int_or_default(estimate_text, 0, placeholder="0")
        recurrence_days = _parse_int_or_default(recurrence_text, None, placeholder="Tage")
        if priority is None or estimate_minutes is None or (recurrence_text and recurrence_days is None):
            messagebox.showerror("Fehler", "Schätzung, Priorität und Wiederholung müssen Zahlen sein.", parent=self)
            return
        if priority < 1 or priority > 5:
            messagebox.showerror("Fehler", "Die Priorität muss zwischen 1 und 5 liegen.", parent=self)
            return

        risk_rows: list[dict[str, object]] = []
        for risk_var, probability_var, impact_var, countermeasure_var in self.task_risk_rows:
            risk_text = risk_var.get().strip()
            if not risk_text:
                continue
            probability = _parse_int_or_default(probability_var.get(), 3, placeholder="1-5")
            impact = _parse_int_or_default(impact_var.get(), 3, placeholder="1-5")
            if probability is None or impact is None:
                messagebox.showerror("Fehler", "Jedes Risiko braucht Wahrscheinlichkeit und Ausmaß als Zahl 1 bis 5.", parent=self)
                return
            if probability < 1 or probability > 5 or impact < 1 or impact > 5:
                messagebox.showerror("Fehler", "Wahrscheinlichkeit und Ausmaß müssen zwischen 1 und 5 liegen.", parent=self)
                return
            risk_rows.append(
                {
                    "risk": risk_text,
                    "probability": probability,
                    "impact": impact,
                    "countermeasure": countermeasure_var.get().strip(),
                }
            )

        legacy_probability = max((int(row["probability"]) for row in risk_rows), default=3)
        legacy_impact = max((int(row["impact"]) for row in risk_rows), default=3)
        project_id = None
        if self.project_var.get() != "Keine Zuordnung":
            project_id = int(self.project_var.get().split(":", 1)[0])
        self.finish(
            {
                "title": title,
                "project_id": project_id,
                "status": TASK_STATUS_VALUES.get(self.status_var.get(), "open"),
                "priority": priority,
                "due_date": due_text or None,
                "blocked_reason": self.blocked_text.get("1.0", "end").strip(),
                "risk": "\n".join(str(row["risk"]) for row in risk_rows),
                "risk_rows": risk_rows,
                "risk_probability": legacy_probability,
                "risk_impact": legacy_impact,
                "risk_weight": max(legacy_probability, legacy_impact),
                "risk_countermeasure": "\n".join(str(row["countermeasure"]) for row in risk_rows),
                "context": self.context_var.get().strip(),
                "energy_level": ENERGY_VALUES.get(self.energy_var.get(), "medium"),
                "estimate_minutes": estimate_minutes,
                "tags": normalize_tags(self.tags_var.get()),
                "recurrence_days": recurrence_days,
                "details": self.details_text.get("1.0", "end").strip(),
            }
        )


class TemplateDialog(BaseDialog):
    def __init__(self, master: tk.Misc, title: str, projects: list[sqlite3.Row], template: sqlite3.Row | None = None) -> None:
        super().__init__(master, title)
        self.projects = projects
        self.project_values = ["Keine Zuordnung"] + [f'{project["id"]}: {project["name"]}' for project in projects]
        self.name_var = tk.StringVar(value=template["name"] if template else "")
        self.title_var = tk.StringVar(value=template["title"] if template else "")
        self.project_var = tk.StringVar(value=self._project_label(template))
        self.status_var = tk.StringVar(value=self._status_label(template))
        self.priority_var = tk.StringVar(value=str(template["priority"] if template else ""))
        self.offset_var = tk.StringVar(value=str(template["due_offset_days"] if template and template["due_offset_days"] is not None else ""))
        self.context_var = tk.StringVar(value=template["context"] if template else "")
        self.energy_var = tk.StringVar(value=self._energy_label(template))
        self.tags_var = tk.StringVar(value=template["tags"] if template else "")
        self.recurrence_var = tk.StringVar(value=str(template["recurrence_days"] if template and template["recurrence_days"] else ""))

        frame = ttk.Frame(self, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        self._add_entry(frame, "Name", 0, self.name_var, required=True)
        self._add_entry(frame, "Titel", 1, self.title_var, required=True)
        self._add_combo(frame, "Projekt", 2, self.project_values, self.project_var)
        self._add_combo(frame, "Status", 3, [label for label, _ in TASK_STATUS_CHOICES], self.status_var)
        PlaceholderEntry(frame, placeholder="1-5", textvariable=self.priority_var, width=44).grid(row=4, column=1, sticky="ew", pady=(0, 8))
        PlaceholderEntry(frame, placeholder="Tage", textvariable=self.offset_var, width=44).grid(row=5, column=1, sticky="ew", pady=(0, 8))
        self._add_entry(frame, "Kontext", 6, self.context_var)
        self._add_combo(frame, "Energie", 7, [label for label, _ in ENERGY_CHOICES], self.energy_var)
        PlaceholderEntry(frame, placeholder="a,b,c", textvariable=self.tags_var, width=44).grid(row=8, column=1, sticky="ew", pady=(0, 8))
        PlaceholderEntry(frame, placeholder="Tage", textvariable=self.recurrence_var, width=44).grid(row=9, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Details").grid(row=10, column=0, sticky="nw", pady=(0, 8))
        self.details_text = tk.Text(frame, width=52, height=8, wrap="word")
        self.details_text.grid(row=10, column=1, sticky="ew")
        if template:
            self.details_text.insert("1.0", template["details"])

        buttons = ttk.Frame(frame)
        buttons.grid(row=11, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Speichern", command=self._submit).grid(row=0, column=1)
        self.bind("<Escape>", lambda _: self.destroy())

    def _project_label(self, template: sqlite3.Row | None) -> str:
        if not template or template["project_id"] is None:
            return "Keine Zuordnung"
        return next((f'{project["id"]}: {project["name"]}' for project in self.projects if project["id"] == template["project_id"]), "Keine Zuordnung")

    def _status_label(self, template: sqlite3.Row | None) -> str:
        status = template["status"] if template else "open"
        return next((label for label, value in TASK_STATUS_CHOICES if value == status), "Offen")

    def _energy_label(self, template: sqlite3.Row | None) -> str:
        energy = template["energy_level"] if template else "medium"
        return next((label for label, value in ENERGY_CHOICES if value == energy), "Mittel")

    def _add_entry(self, frame: ttk.Frame, text: str, row: int, variable: tk.StringVar, required: bool = False) -> None:
        label_text = f"{text} *" if required else text
        ttk.Label(frame, text=label_text).grid(row=row, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=variable, width=44).grid(row=row, column=1, sticky="ew", pady=(0, 8))

    def _add_combo(self, frame: ttk.Frame, text: str, row: int, values: list[str], variable: tk.StringVar) -> None:
        ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", pady=(0, 8))
        ttk.Combobox(frame, textvariable=variable, values=values, state="readonly", width=41).grid(row=row, column=1, sticky="ew", pady=(0, 8))

    def _add_spin(self, frame: ttk.Frame, text: str, row: int, variable: tk.StringVar, minimum: int, maximum: int) -> None:
        ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", pady=(0, 8))
        PlaceholderEntry(frame, placeholder=f"{minimum}-{maximum}", textvariable=variable, width=8).grid(row=row, column=1, sticky="w", pady=(0, 8))

    def _submit(self) -> None:
        name = self.name_var.get().strip()
        title = self.title_var.get().strip()
        if not name or not title:
            messagebox.showerror("Fehler", "Name und Titel dürfen nicht leer sein.", parent=self)
            return
        project_id = None
        if self.project_var.get() != "Keine Zuordnung":
            project_id = int(self.project_var.get().split(":", 1)[0])
        offset_text = self.offset_var.get().strip()
        recurrence_text = self.recurrence_var.get().strip()
        priority = _parse_int_or_default(self.priority_var.get(), 3, placeholder="1-5")
        due_offset_days = _parse_int_or_default(offset_text, None, placeholder="Tage")
        recurrence_days = _parse_int_or_default(recurrence_text, None, placeholder="Tage")
        if priority is None or (offset_text and due_offset_days is None) or (recurrence_text and recurrence_days is None):
            messagebox.showerror("Fehler", "Priorität, Offset und Wiederholung müssen Zahlen sein.", parent=self)
            return
        self.finish(
            {
                "name": name,
                "title": title,
                "project_id": project_id,
                "status": TASK_STATUS_VALUES.get(self.status_var.get(), "open"),
                "priority": priority,
                "due_offset_days": due_offset_days,
                "context": self.context_var.get().strip(),
                "energy_level": ENERGY_VALUES.get(self.energy_var.get(), "medium"),
                "tags": normalize_tags(self.tags_var.get()),
                "recurrence_days": recurrence_days,
                "details": self.details_text.get("1.0", "end").strip(),
            }
        )


