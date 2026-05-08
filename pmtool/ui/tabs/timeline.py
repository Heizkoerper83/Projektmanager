"""Timeline tab for visualizing project milestones and tasks."""

from __future__ import annotations

from datetime import date
import tkinter as tk
from tkinter import ttk

from pmtool.core import list_milestones, list_projects, list_tasks


def build_timeline_tab(app) -> None:
    """Build the timeline tab UI."""
    top = ttk.Frame(app.timeline_tab)
    top.pack(fill="x", padx=14, pady=14)

    ttk.Label(top, text="Projekt-Zeitstrahl", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        top,
        text="Visualisiere Meilensteine, Aufgaben und deren Status auf einer chronologischen Linie.",
        style="Subheader.TLabel",
    ).pack(anchor="w", pady=(2, 10))

    # Steuerleiste
    controls = ttk.Frame(top)
    controls.pack(fill="x", pady=(8, 0))
    
    ttk.Label(controls, text="Projekt:").pack(side="left")
    app.timeline_project_combo = ttk.Combobox(
        controls,
        textvariable=app.timeline_project_var,
        state="readonly",
        values=["Projekt wählen"],
        width=40,
    )
    app.timeline_project_combo.pack(side="left", padx=(8, 8))
    app.timeline_project_combo.bind("<<ComboboxSelected>>", lambda _: refresh_timeline(app))

    ttk.Button(controls, text="↻", command=lambda: refresh_timeline(app), width=3).pack(side="left")
    ttk.Button(
        controls,
        text="An Fenster anpassen",
        command=lambda: _fit_timeline_to_window(app),
    ).pack(side="left", padx=(8, 0))
    
    status_frame = ttk.Frame(controls)
    status_frame.pack(side="right", fill="x", expand=True)
    ttk.Label(status_frame, textvariable=app.timeline_status_var, font=("Segoe UI", 9, "bold")).pack(anchor="e")

    # Legende
    legend_frame = ttk.LabelFrame(top, text="Legende", padding=10)
    legend_frame.pack(fill="x", pady=(8, 0))
    
    legend_items = [
        ("●", "#16a34a", "Erledigt"),
        ("●", "#ea580c", "In Arbeit"),
        ("●", "#2563eb", "Offen"),
        ("●", "#dc2626", "Blockiert"),
        ("◆", "#f59e0b", "Meilenstein"),
    ]
    
    for i, (symbol, color, label) in enumerate(legend_items):
        frame = ttk.Frame(legend_frame)
        frame.pack(side="left", padx=(0, 22))
        tk.Label(frame, text=symbol, fg=color, font=("Segoe UI", 15, "bold")).pack(side="left", padx=(0, 6))
        ttk.Label(frame, text=label, font=("Segoe UI", 10)).pack(side="left")

    # Canvas mit Scrollbars
    canvas_frame = ttk.Frame(app.timeline_tab)
    canvas_frame.pack(fill="both", expand=True, padx=14, pady=(12, 0))

    app.timeline_canvas = tk.Canvas(canvas_frame, highlightthickness=0, bg="white", cursor="hand2")
    v_scroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=app.timeline_canvas.yview)
    h_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=app.timeline_canvas.xview)
    
    app.timeline_canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
    
    app.timeline_canvas.grid(row=0, column=0, sticky="nsew")
    v_scroll.grid(row=0, column=1, sticky="ns")
    h_scroll.grid(row=1, column=0, sticky="ew")
    
    canvas_frame.rowconfigure(0, weight=1)
    canvas_frame.columnconfigure(0, weight=1)

    # Eventbindings
    app.timeline_canvas.bind("<Configure>", lambda _: refresh_timeline(app, keep_scroll=True))
    app.timeline_canvas.bind("<Motion>", lambda e: _on_canvas_motion(app, e))
    app.timeline_canvas.bind("<Leave>", lambda _: _hide_tooltip(app))
    app.timeline_canvas.bind("<MouseWheel>", lambda e: _on_canvas_scroll(app, e))
    app.timeline_canvas.bind("<Button-4>", lambda e: _on_canvas_scroll(app, e))
    app.timeline_canvas.bind("<Button-5>", lambda e: _on_canvas_scroll(app, e))

    app.timeline_item_meta = {}
    app.timeline_tooltip = None


def refresh_timeline(app, keep_scroll: bool = False) -> None:
    """Refresh the timeline visualization."""
    if not hasattr(app, "timeline_canvas"):
        return

    canvas = app.timeline_canvas
    palette = app._palette()
    
    # Speichere alte Scroll-Position
    scroll_x = canvas.xview() if keep_scroll else (0, 0)
    scroll_y = canvas.yview() if keep_scroll else (0, 0)

    canvas.delete("all")
    app.timeline_item_meta = {}
    _hide_tooltip(app)

    # Projekt auswählen
    proj_id = _get_selected_project_id(app)
    if proj_id is None:
        canvas.create_text(
            50, 50,
            text="Bitte wähle ein Projekt.",
            anchor="nw",
            fill=palette.get("muted", "#999"),
            font=("Segoe UI", 13, "italic")
        )
        canvas.configure(scrollregion=(0, 0, 400, 150))
        app.timeline_status_var.set("Bereit")
        return

    # Lade Aufgaben und Meilensteine
    tasks = [dict(row) for row in list_tasks(project_id=proj_id, include_done=True)]
    milestones = [dict(row) for row in list_milestones(proj_id)]

    # Filtere nach Datum
    dated_tasks = [t for t in tasks if t.get("due_date")]
    dated_milestones = [m for m in milestones if m.get("due_date")]

    if not dated_tasks and not dated_milestones:
        canvas.create_text(
            50, 50,
            text="Keine Aufgaben oder Meilensteine mit Datum vorhanden.",
            anchor="nw",
            fill=palette.get("muted", "#999"),
            font=("Segoe UI", 13, "italic")
        )
        canvas.configure(scrollregion=(0, 0, 400, 150))
        app.timeline_status_var.set(f"Keine datierten Elemente")
        return

    # Berechne Datum-Range und konvertiere
    all_dates = []
    task_dates_dict = {}
    milestone_dates_dict = {}
    
    for t in dated_tasks:
        try:
            dt = date.fromisoformat(str(t["due_date"]))
            all_dates.append(dt)
            task_dates_dict[t["id"]] = dt
        except (ValueError, TypeError):
            pass
    
    for m in dated_milestones:
        try:
            dt = date.fromisoformat(str(m["due_date"]))
            all_dates.append(dt)
            milestone_dates_dict[m["id"]] = dt
        except (ValueError, TypeError):
            pass
    
    if not all_dates:
        canvas.create_text(
            50, 50,
            text="Keine gültigen Daten vorhanden.",
            anchor="nw",
            fill=palette.get("muted", "#999"),
            font=("Segoe UI", 13, "italic")
        )
        canvas.configure(scrollregion=(0, 0, 400, 150))
        app.timeline_status_var.set("Keine gültigen Daten")
        return

    today = date.today()
    min_date = min(min(all_dates), today)
    max_date = max(max(all_dates), today)
    total_days = max(1, (max_date - min_date).days)

    # Fit-to-view: always render within the currently visible canvas.
    viewport_width = max(canvas.winfo_width(), 900)
    viewport_height = max(canvas.winfo_height(), 620)

    canvas_width = viewport_width
    canvas_height = viewport_height

    left_margin = max(90, int(canvas_width * 0.11))
    right_margin = left_margin
    timeline_width = max(260, canvas_width - left_margin - right_margin)

    beam_y = canvas_height // 2
    upper_band = max(170, int(canvas_height * 0.36))
    lower_band = upper_band
    top_y = max(22, beam_y - upper_band)
    bottom_y = min(canvas_height - 22, beam_y + lower_band)
    
    def date_to_x(d: date) -> float:
        """Konvertiere Datum zu X-Position."""
        ratio = (d - min_date).days / total_days if total_days > 0 else 0
        return left_margin + ratio * timeline_width

    # Farben
    line_color = palette.get("text", "#000")
    text_color = palette.get("text", "#000")
    muted_color = palette.get("muted", "#999")
    bg_color = palette.get("bg", "#fff")
    
    # Zeichne Hintergrund-Grid für Monate
    _draw_month_grid(
        canvas,
        left_margin,
        right_margin,
        canvas_width,
        top_y,
        bottom_y,
        min_date,
        max_date,
        date_to_x,
        muted_color,
    )

    # Zeichne Zeitstrahl-Balken (stärker hervorgehoben)
    canvas.create_line(
        left_margin, beam_y,
        canvas_width - right_margin, beam_y,
        fill=line_color,
        width=5
    )
    
    # Betone den Balken visuell
    canvas.create_line(
        left_margin, beam_y + 1,
        canvas_width - right_margin, beam_y + 1,
        fill=line_color,
        width=1.5
    )

    # Datum-Labels mit besserer Formatierung
    min_date_str = _format_date_pretty(min_date)
    max_date_str = _format_date_pretty(max_date)
    
    canvas.create_text(
        left_margin - 5, beam_y + 30,
        text=min_date_str,
        anchor="ne",
        fill=text_color,
        font=("Segoe UI", 10, "bold")
    )
    canvas.create_text(
        canvas_width - right_margin + 5, beam_y + 30,
        text=max_date_str,
        anchor="nw",
        fill=text_color,
        font=("Segoe UI", 10, "bold")
    )

    # "Heute" Marker mit besserer Visualisierung
    today_x = date_to_x(today)
    canvas.create_line(
        today_x, top_y,
        today_x, bottom_y,
        fill="#dc2626",
        width=4,
        dash=(7, 4)
    )
    today_label_top = max(6, top_y - 16)
    today_label_bottom = min(canvas_height - 6, today_label_top + 34)
    canvas.create_rectangle(
        today_x - 36, today_label_top,
        today_x + 36, today_label_bottom,
        fill="#dc2626",
        outline="#991b1b"
    )
    canvas.create_text(
        today_x, (today_label_top + today_label_bottom) / 2,
        text="HEUTE",
        anchor="c",
        fill="#ffffff",
        font=("Segoe UI", 10, "bold")
    )

    # Zeichne Meilensteine zuerst (damit sie hinter Tasks sind)
    milestone_lanes = {}
    for milestone in dated_milestones:
        if milestone["id"] not in milestone_dates_dict:
            continue
        
        ms_date = milestone_dates_dict[milestone["id"]]
        x = date_to_x(ms_date)
        status = milestone.get("status", "open")
        title = milestone.get("title") or milestone.get("name") or "Meilenstein"
        
        # Farbe basierend auf Status
        if status == "done":
            color = "#16a34a"  # Grün
            border = "#14532d"
        else:
            color = "#f59e0b"  # Gold
            border = "#92400e"
        
        # Bestimme Y-Position
        lane = _get_milestone_lane(milestone_lanes, x)
        offset = max(90, int(canvas_height * 0.15))
        milestone_lane_step = max(46, int(canvas_height * 0.08))
        
        if lane % 2 == 0:
            y = beam_y - offset - (lane // 2 * milestone_lane_step)
        else:
            y = beam_y + offset + ((lane - 1) // 2 * milestone_lane_step)
        y = max(top_y + 24, min(bottom_y - 24, y))
        
        # Zeichne Raute (Meilenstein)
        size = 16
        marker_id = canvas.create_polygon(
            x, y - size,
            x + size, y,
            x, y + size,
            x - size, y,
            fill=color,
            outline=border,
            width=2.5,
            tags=("timeline_item",)
        )
        canvas.create_polygon(
            x, y - (size + 10),
            x + (size + 10), y,
            x, y + (size + 10),
            x - (size + 10), y,
            fill="",
            outline="",
            width=0,
            tags=("timeline_item", "timeline_hit")
        )
        
        # Zeichne Verbindungslinie
        canvas.create_line(x, beam_y, x, y - size - 2, fill=border, width=1.5, dash=(3, 3))
        
        # Zeichne Label unter der Raute
        canvas.create_text(
            x, y + size + 24,
            text=title,
            anchor="n",
            fill=text_color,
            font=("Segoe UI", 10, "bold"),
            width=180
        )
        
        app.timeline_item_meta[marker_id] = {
            "kind": "milestone",
            "title": title,
            "status": status,
            "date": ms_date.isoformat(),
            "raw": milestone
        }

    # Zeichne Aufgaben (Punkte)
    task_lanes = {}
    for task in dated_tasks:
        if task["id"] not in task_dates_dict:
            continue

        task_date = task_dates_dict[task["id"]]
        x = date_to_x(task_date)
        status = task.get("status", "open")
        title = task.get("title") or task.get("name") or "Aufgabe"
        
        # Farbe basierend auf Status
        if status == "done":
            color = "#16a34a"  # Grün
        elif status == "blocked":
            color = "#dc2626"  # Rot
        elif status == "in_progress":
            color = "#ea580c"  # Orange
        else:
            color = "#2563eb"  # Blau
        
        # Bestimme Y-Position (abwechselnd oben/unten)
        lane = _get_task_lane(task_lanes, x, min_gap=90)
        task_offset = max(74, int(canvas_height * 0.12))
        task_lane_step = max(32, int(canvas_height * 0.055))
        if lane % 2 == 0:
            y = beam_y - task_offset - (lane // 2 * task_lane_step)
        else:
            y = beam_y + task_offset + ((lane - 1) // 2 * task_lane_step)
        y = max(top_y + 20, min(bottom_y - 20, y))
        
        # Zeichne Verbindungslinie vom Balken zum Punkt
        canvas.create_line(x, beam_y, x, y, fill=color, width=1.5, dash=(3, 3))
        
        # Zeichne Punkt mit besserem Effekt
        marker_id = canvas.create_oval(
            x - 10, y - 10,
            x + 10, y + 10,
            fill=color,
            outline="#ffffff",
            width=3,
            tags=("timeline_item",)
        )
        canvas.create_oval(
            x - 22, y - 22,
            x + 22, y + 22,
            fill="",
            outline="",
            width=0,
            tags=("timeline_item", "timeline_hit")
        )
        
        # Optionaler innerer Ring für bessere visuelle Tiefe
        canvas.create_oval(
            x - 5, y - 5,
            x + 5, y + 5,
            fill="",
            outline=color,
            width=1
        )
        
        app.timeline_item_meta[marker_id] = {
            "kind": "task",
            "title": title,
            "status": status,
            "date": task_date.isoformat(),
            "raw": task
        }

    # Berechne Statistiken
    done_count = sum(1 for t in dated_tasks if t.get("status") == "done")
    in_progress_count = sum(1 for t in dated_tasks if t.get("status") == "in_progress")
    blocked_count = sum(1 for t in dated_tasks if t.get("status") == "blocked")
    open_count = len(dated_tasks) - done_count - in_progress_count - blocked_count
    
    done_milestones = sum(1 for m in dated_milestones if m.get("status") == "done")
    total_milestones = len(dated_milestones)
    
    percentage_done = (done_count * 100 // len(dated_tasks)) if dated_tasks else 0

    # Update Status mit Statistiken
    stats_text = (
        f"Aufgaben: {len(dated_tasks)} (✓{done_count} ⟳{in_progress_count} ✗{blocked_count} ○{open_count}) | "
        f"Meilensteine: {done_milestones}/{total_milestones} | "
        f"Fortschritt: {percentage_done}%"
    )
    app.timeline_status_var.set(stats_text)
    
    # Setze Scrollregion
    canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
    
    if keep_scroll:
        canvas.xview_moveto(scroll_x[0])
        canvas.yview_moveto(scroll_y[0])


def _get_task_lane(lane_map: dict, x: float, min_gap: float = 80) -> int:
    """Bestimme die beste Y-Spur für eine Aufgabe."""
    for lane in range(12):
        if lane not in lane_map or x - lane_map[lane] >= min_gap:
            lane_map[lane] = x
            return lane
    lane_map[11] = x
    return 11


def _get_milestone_lane(lane_map: dict, x: float, min_gap: float = 120) -> int:
    """Bestimme die beste Y-Spur für einen Meilenstein."""
    for lane in range(8):
        if lane not in lane_map or x - lane_map[lane] >= min_gap:
            lane_map[lane] = x
            return lane
    lane_map[7] = x
    return 7


def _format_date_pretty(d: date) -> str:
    """Formatiere Datum schöner (z.B. 'Jan 15, 2026')."""
    months = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    return f"{months[d.month - 1]} {d.day}, {d.year}"


def _draw_month_grid(canvas: tk.Canvas, left: float, right: float, width: float, 
                     top_y: float, bottom_y: float, min_date: date, max_date: date,
                     date_to_x_fn, color: str) -> None:
    """Zeichne monatliche Gitterlinien."""
    current = date(min_date.year, min_date.month, 1)
    
    while current <= max_date:
        x = date_to_x_fn(current)
        if left <= x <= width - right:
            canvas.create_line(
                x, top_y,
                x, bottom_y,
                fill=color,
                width=0.5,
                dash=(2, 4)
            )
            
            # Monatslabel oben
            month_str = current.strftime("%b '%y")
            canvas.create_text(
                x, max(2, top_y - 16),
                text=month_str,
                anchor="n",
                fill=color,
                font=("Segoe UI", 9)
            )
        
        # Zum nächsten Monat
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def _get_selected_project_id(app) -> int | None:
    """Extrahiere Projekt-ID aus Combobox-Wert."""
    value = app.timeline_project_var.get().strip()
    if ":" not in value:
        return None
    try:
        return int(value.split(":", 1)[0])
    except ValueError:
        return None


def _on_canvas_scroll(app, event: tk.Event) -> None:
    """Behandle Mausrad-Scrollen für Zoom-Effekt."""
    canvas = app.timeline_canvas
    
    # Scroll-Verhalten
    if event.num == 5 or event.delta < 0:
        # Scroll runter = rechts
        canvas.xview_scroll(4, "units")
    elif event.num == 4 or event.delta > 0:
        # Scroll oben = links
        canvas.xview_scroll(-4, "units")


def _fit_timeline_to_window(app) -> None:
    """Render timeline for current viewport and center the visible window."""
    refresh_timeline(app, keep_scroll=False)
    canvas = getattr(app, "timeline_canvas", None)
    if canvas is None:
        return

    # Center current viewport in the available scrollregion.
    x_first, x_last = canvas.xview()
    y_first, y_last = canvas.yview()
    x_span = max(0.0, x_last - x_first)
    y_span = max(0.0, y_last - y_first)
    x_target = max(0.0, min(1.0, 0.5 - x_span / 2))
    y_target = max(0.0, min(1.0, 0.5 - y_span / 2))
    canvas.xview_moveto(x_target)
    canvas.yview_moveto(y_target)


def _on_canvas_motion(app, event: tk.Event) -> None:
    """Hover-Event auf Canvas."""
    canvas = app.timeline_canvas
    # Convert viewport coordinates to canvas coordinates so hit-testing
    # stays correct after horizontal or vertical scrolling.
    x_canvas = int(canvas.canvasx(event.x))
    y_canvas = int(canvas.canvasy(event.y))
    meta = _timeline_meta_at_point(canvas, x_canvas, y_canvas, app.timeline_item_meta)
    if meta is None:
        _hide_tooltip(app)
        return
    _show_tooltip(app, meta, event.x_root, event.y_root)


def _timeline_meta_at_point(
    canvas: tk.Canvas,
    x: int,
    y: int,
    meta_map: dict[int, dict[str, object]],
) -> dict[str, object] | None:
    """Find the closest timeline metadata for a pointer position."""
    current = canvas.find_withtag("current")
    if current:
        item_id = int(current[0])
        if item_id in meta_map:
            return meta_map[item_id]

    hit_items = canvas.find_overlapping(x - 22, y - 22, x + 22, y + 22)
    for item_id in reversed(hit_items):
        if item_id in meta_map:
            return meta_map[item_id]

    hit_items = canvas.find_overlapping(x - 36, y - 36, x + 36, y + 36)
    for item_id in reversed(hit_items):
        if item_id in meta_map:
            return meta_map[item_id]

    return None


def _show_tooltip(app, meta: dict, x_root: int, y_root: int) -> None:
    """Zeige Tooltip mit erweiterten Details."""
    _hide_tooltip(app)
    
    tooltip = tk.Toplevel(app)
    tooltip.overrideredirect(True)
    tooltip.attributes("-topmost", True)
    
    palette = app._palette()
    
    frame = ttk.Frame(tooltip, padding=12)
    frame.pack(fill="both", expand=True)
    
    title = meta.get("title", "Eintrag")
    kind = meta.get("kind", "")
    status = meta.get("status", "open")
    date_value = meta.get("date", "-")
    
    kind_text = "📌 Aufgabe" if kind == "task" else "🎯 Meilenstein"
    status_icons = {
        "done": "✓",
        "in_progress": "⟳",
        "blocked": "✗",
    }
    status_names = {
        "done": "Erledigt",
        "in_progress": "In Arbeit",
        "blocked": "Blockiert",
    }
    
    status_icon = status_icons.get(status, "○")
    status_text = f"{status_icon} {status_names.get(status, 'Offen')}"
    
    # Header
    ttk.Label(
        frame,
        text=f"{kind_text}: {title}",
        font=("Segoe UI", 11, "bold"),
        wraplength=350
    ).pack(anchor="w", pady=(0, 8))
    
    # Divider
    ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(0, 8))
    
    # Status und Datum
    ttk.Label(
        frame,
        text=f"Status:  {status_text}",
        font=("Segoe UI", 10)
    ).pack(anchor="w", pady=(0, 4))
    
    ttk.Label(
        frame,
        text=f"Datum:  {_format_date_pretty(date.fromisoformat(date_value)) if date_value != '-' else '-'}",
        font=("Segoe UI", 10)
    ).pack(anchor="w", pady=(0, 8))
    
    # Extra-Infos bei Aufgaben
    raw = meta.get("raw", {})
    if isinstance(raw, dict):
        extra_info = []
        
        if "energy_level" in raw and raw["energy_level"]:
            extra_info.append(f"Energie: {raw['energy_level']}")
        
        if "estimate_minutes" in raw and raw["estimate_minutes"]:
            mins = int(raw["estimate_minutes"])
            hours = mins // 60
            remainder = mins % 60
            time_str = f"{hours}h {remainder}m" if hours > 0 else f"{mins}m"
            extra_info.append(f"Aufwand: {time_str}")
        
        if extra_info:
            ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(0, 8))
            for info in extra_info:
                ttk.Label(frame, text=info, font=("Segoe UI", 8), foreground=palette.get("muted", "#999")).pack(anchor="w")
    
    ttk.Label(
        frame,
        text="(Mausverlauf versteckt das Fenster)",
        font=("Segoe UI", 8),
        foreground=palette.get("muted", "#999")
    ).pack(anchor="w", pady=(8, 0))
    
    tooltip.update_idletasks()
    width = min(460, max(320, frame.winfo_reqwidth() + 32))
    height = min(340, max(160, frame.winfo_reqheight() + 32))
    
    # Positioniere Tooltip neben Maus
    tooltip.geometry(f"{width}x{height}+{x_root+20}+{y_root+15}")
    tooltip.configure(bg=palette.get("bg", "white"))
    
    app.timeline_tooltip = tooltip


def _hide_tooltip(app) -> None:
    """Verstecke Tooltip."""
    if app.timeline_tooltip is not None:
        try:
            app.timeline_tooltip.destroy()
        except tk.TclError:
            pass
    app.timeline_tooltip = None
