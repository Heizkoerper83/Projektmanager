# Copilot Context: Projektmanager

Last updated: 2026-06-01

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

## PyInstaller-Warnung: Modul-Swap-Mechanismus in pmtool/core/__init__.py
`pmtool/core/__init__.py` verwendet einen `sys.modules`-Swap-Trick (`sys.modules[__name__] = _legacy`), um `pmtool.core` durch `pmtool.core.legacy` zu ersetzen. **PyInstaller kann diesen Swap nicht korrekt auflösen.**

Wenn `export_csv`, `export_json`, `import_csv`, `import_json` (oder andere Namen aus `pmtool.core.legacy`) direkt aus `pmtool.remote_core` importiert werden sollen, müssen sie **explizit** im `from pmtool.core import ...`-Statement in `remote_core.py` aufgeführt werden. Ein einfaches `from pmtool.core import *` reicht ebenfalls nicht, da PyInstaller die dynamische Namensauflösung nicht erfasst.

**Vorgehen bei zukünftigen Imports aus `pmtool.core`:**
1. Die gewünschte Funktion in `pmtool/core/legacy.py` definieren
2. In `pmtool/core/__init__.py` in die `__all__`-Liste aufnehmen (für `from pmtool.core import ...`)
3. In `pmtool/remote_core.py` ins `from pmtool.core import (...)`-Statement aufnehmen (für PyInstaller)
4. In `pmtool/remote_core.py` in die `__all__`-Liste aufnehmen (für Konsistenz)

## Debugging unter Windows
Wenn die `.exe` sofort wieder schliesst, per Kommandozeile starten um die Fehlermeldung zu sehen:
```cmd
C:\Users\...> pr.exe
```
Häufige Ursache: Ein von PyInstaller nicht aufgelöster Import wegen des Modul-Swap-Mechanismus.

## Hinweise fuer Aenderungen
- Neue Features sollen GUI, CLI und Core konsistent halten.
- Bei Schema-Aenderungen Tests in `tests/` anpassen (`test_core.py`, `test_collab_auth.py`).
- README und diese Datei mit aktualisieren, wenn Features oder Struktur sich aendern.
- REST-API-Payloads in `remote_core.py` (`_task_payload`, `_project_payload`) erweitern, wenn neue Felder dazukommen.
- GUI-Tabs in `pmtool/ui/tabs/` sind module, keine Klassen – Funktionen erhalten die App-Instanz als Parameter.
- **Task-Dokumentation:** Alle von Cline durchgeführten Tasks werden in `TASK_HISTORY.md` festgehalten. Vor grösseren Änderungen zuerst einen Plan erstellen, dann nach Freigabe ausführen, danach in `TASK_HISTORY.md` dokumentieren.
