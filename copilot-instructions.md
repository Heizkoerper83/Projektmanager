# Copilot Context: Projektmanager

Last updated: 2026-06-17

## Kurzueberblick
- Projektmanagement-Tool mit zentralem **Server-Only-Modus** (keine lokale Datenbank).
- Desktop-GUI (tkinter) kommuniziert ausschliesslich über REST-API mit einem Remote-Kollaborationsserver.
- Einstiegspunkte: `pr.py` (Wrapper), `python -m pmtool` (direkt).

## Wichtige Module
- `pmtool/gui.py`: Haupt-GUI (LoginDialog, ProjectManagerApp, AccountAdminDialog, ~2860 Zeilen).
- `pmtool/remote_core.py`: REST-API-Client – alle CRUD-Operationen gegen Server.
- `pmtool/collab_server.py`: Server-seitige Kollaboration (Login, Accounts, API-Endpoints).
- `pmtool/collab_accounts.py`: Account-Verwaltung (JSON-Datei).
- `pmtool/core/`: Datenbank-Modelle, Reports, Legacy-Hilfsfunktionen.
  - `models.py`: Data-Klassen (TaskInput, ProjectInput, RiskData, TaskFilter, Principal).
  - `legacy.py`: Normalisierungen, Datenbank-Utilities, Risk-Rows-Handling, Tags.
  - `reports.py`: Berichtsgenerierung.
- `pmtool/cli.py`: CLI-Kommandos (add/list/update/delete projekte, aufgaben, vorlagen, milestones).
- `pmtool/ui/`: gemeinsame UI-Bausteine, Dialoge, Tabs.
  - `dialogs.py`: DatePicker, PlaceholderEntry, TogglePasswordEntry, ProjectDialog, TaskDialog, TemplateDialog.
  - `tabs/`: board, tasks, projects, timeline, templates, reports, dashboard, backup.
- `pmtool/sync.py`: Sync-Logik und Auto-Sync (wird vom Server bereitgestellt, Client fragt REST-API ab).
- `pmtool/paths.py`: Pfadauflösung für lokale Daten (Accounts JSON, DB nur auf Server).

## Typische Befehle
- Start GUI: `python pr.py` oder `python -m pmtool`
- Explizit GUI: `python pr.py gui`
- Tests: `python -m unittest discover -s tests -v` oder `python -m pytest -q`

## Architektur
- Server-seitige DB: `app.db` (SQLite) auf dem Server.
- Clients haben keine lokale DB; alle CRUD-Operationen gehen direkt an die REST-API.
- Authentifizierung per Session-Cookie (`PMTOOL_SESSION`), Login/Register über `/login` und `/register`.
- Session-Timeout: 30 Minuten (1800 Sekunden Idle-Timeout in der GUI).
- Basis-URL: standardmässig `https://100.80.250.84`, konfigurierbar via `PM_BASE_URL`-Env-Variable.

## Features
- Dashboard mit Kennzahlen (Aufgaben/Projekte nach Status)
- Kanban-Board (4 Spalten: offen, in Arbeit, blockiert, erledigt)
- Aufgaben mit Titel, Details, Status, Priorität (1-5), Fälligkeitsdatum, Tags, Kontext, Energie-Level (low/medium/high), Aufwand (Minuten), Wiederholungen
- Risikobewertung pro Aufgabe und Projekt (multipel: mehrere Risk-Rows mit probability/impact/countermeasure)
- Projekte mit Name, Team, Beschreibung, Status, Ziel, Meilenstein, Review-Datum
- Vorlagen für wiederkehrende Aufgaben (mit Due-Offset)
- Wochenbericht als Markdown-Generierung
- Global Search (projekt-, aufgaben- und funktionsübergreifend)
- Schnellerfassung neuer Aufgaben in der Topbar
- Tastenkürzel (Ctrl+N, Ctrl+E, F5, Ctrl+1-7 für Tabs, Ctrl+K für globale Suche)
- Theme-Umschaltung Hell/Dunkel
- Exe-Download-Button zum Herunterladen der aktuellen Build-EXE

## Rollen
- `reader`: nur GET-Endpunkte (read-only)
- `editor`: GET + POST + PATCH (schreibender Zugriff)
- `admin`: zusätzlich Account-Verwaltung (GUI-Button "Konten" in Topbar)

## Build
- Windows-EXE wird per GitHub Actions gebaut (Push auf `main` oder Tag-Release).
- Build-Script: `scripts/build_exe.py`.
- PyInstaller-Spec: `pr.spec`.

## PyInstaller-Build: WICHTIG – Modul-Swap-Mechanismus in pmtool/core/__init__.py

`pmtool/core/__init__.py` (Zeile 102) verwendet einen `sys.modules`-Swap-Trick:
```python
sys.modules[__name__] = _legacy
```

Dies ersetzt das gesamte `pmtool.core`-Modul zur Laufzeit durch `pmtool.core.legacy`. **PyInstaller kann diesen Swap nicht korrekt auflösen.** Der gefrorene Importer versucht, die Namen im originalen (geswappten) `__init__`-Modul zu finden und scheitert.

**Konsequenz:** Jeglicher `from pmtool.core import ...` in Code, der per PyInstaller gebaut wird, schlägt fehl – selbst wenn die Namen explizit aufgeführt sind.

**Regel für alle Build-relevanten Dateien** (insb. `pmtool/remote_core.py`, `pmtool/collab_server.py`):
Imports aus `pmtool.core` müssen **direkt aus den Quellmodulen** erfolgen, nicht über das geswap-te `pmtool.core`:

```python
# ❌ NICHT – PyInstaller zerbricht daran:
from pmtool.core import export_csv, format_date

# ✅ STATT DESSEN – Direkt aus den Quellmodulen:
from pmtool.core.legacy import export_csv, format_date, normalize_tags
from pmtool.core.reports import build_weekly_project_report_markdown
```

**Folgende Quellmodule sind sicher für direkte Importe:**
- `pmtool.core.legacy` – CRUD-Helfer, Normalisierungen, Labels, Export/Import (CSV, JSON)
- `pmtool.core.reports` – `build_weekly_project_report_markdown`, `generate_weekly_project_report`
- `pmtool.core.models` – Data-Klassen (`ProjectInput`, `TaskInput`, etc.)

## Debugging unter Windows
Wenn die `.exe` sofort wieder schliesst, per Kommandozeile starten um die Fehlermeldung zu sehen:
```cmd
C:\Users\...> pr.exe
```
Häufige Ursache: Ein von PyInstaller nicht aufgelöster Import wegen des Modul-Swap-Mechanismus. In dem Fall die Import-Kette in `remote_core.py` prüfen und auf direkte Importe aus `pmtool.core.legacy` umstellen.

## Rate-Limiter

Der Server (`collab_server.py`) hat einen integrierten Rate-Limiter:
- **Limit:** 600 Requests pro Minute pro IP (`RATE_LIMIT_REQUESTS_PER_MINUTE = 600`)
- **Thread-Safety:** `threading.Lock` schützt den Request-Log vor Race-Conditions
- **Geltungsbereich:** Alle HTTP-Endpunkte (API und Web-UI) sind betroffen
- **Antwort bei Überschreitung:** HTTP 429 mit `{"error": "Zu viele Anfragen. Bitte kurz warten."}`

## API-Endpoints (Server)

Der Server bietet folgende REST-Endpoints:

**GET Endpoints:**
...
- `GET /api/tasks/{id}/details` – **Batch-Endpoint**: Task + Notes + History in einem Response (ersetzt 3 separate Calls)

## Performance-Optimierungen

**Batch-Endpoint (`GET /api/tasks/{id}/details`):**
- Liefert Task, Notes und History in einem einzigen API-Call
- Nutzung in der Web-UI (`loadTaskNotesHistory`) reduziert 2 Requests → 1
- Nutzung im Desktop-GUI (`update_task_details`) reduziert 3 Requests → 1

**Web-UI (`collab_server.py` embedded JS):**
- Nach Mutationen werden nur noch die betroffenen Endpoints neu geladen:
  - Projekt-Operationen: `loadProjects()` + `loadDashboard()` (2 statt 6 Requests)
  - Aufgaben-Operationen: `loadTasks()` + `loadDashboard()` (2 statt 6 Requests)
  - Meilenstein-/Vorlagen-Operationen: nur der jeweilige Tab (1 Request)
- Initialer Page-Load lädt weiterhin alle 6 Endpoints via `reloadAll()`

**Desktop-GUI (`gui.py`):**
- `refresh_project_combo_boxes()` ruft `list_projects()` nur 1× statt 4× auf
- **Project-Cache**: `refresh_all()` speichert `list_projects()` in `app._cached_projects` – alle Sub-Funktionen nutzen den Cache (reduziert von 5× auf 1× `list_projects()` pro Refresh)
- **Such-Debounce**: 300ms Debounce beim Tippen in der Suchleiste (verhindert API-Flood bei jedem Tastendruck)

**Board (`ui/tabs/board.py`):**
- `refresh_board()` macht 1 Query (alle Tasks) statt 4 Queries (einer pro Status)

**Dashboard-Queries (`core/legacy.py`):**
- `task_dashboard_counts()` und `project_dashboard_counts()` nutzen SQL `GROUP BY`-Aggregat-Queries statt Full-Table-Scans + Python-Counting

**Task Notes/History (`core/legacy.py`):**
- `list_task_notes/history` rufen nicht mehr unnötig `get_task()` auf

## Hinweise fuer Aenderungen
- Neue Features sollen GUI, CLI und Core konsistent halten.
- Bei Schema-Aenderungen Tests in `tests/` anpassen (`test_core.py`, `test_collab_auth.py`).
- README und diese Datei mit aktualisieren, wenn Features oder Struktur sich aendern.
- REST-API-Payloads in `remote_core.py` (`_task_payload`, `_project_payload`) erweitern, wenn neue Felder dazukommen.
- GUI-Tabs in `pmtool/ui/tabs/` sind module, keine Klassen – Funktionen erhalten die App-Instanz als Parameter.
- **Task-Dokumentation:** Alle von Cline durchgeführten Tasks werden in `TASK_HISTORY.md` festgehalten. Vor grösseren Änderungen zuerst einen Plan erstellen, dann nach Freigabe ausführen, danach in `TASK_HISTORY.md` dokumentieren.
