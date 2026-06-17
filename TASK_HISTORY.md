# Task History – Projektmanager

Diese Datei dokumentiert alle von Cline durchgeführten Tasks im Projekt.
Zweck: Nachvollziehbarkeit, Kontext für zukünftige Sessions, Vermeidung von Doppelarbeit.

## Format

Jeder Eintrag besteht aus:

```
## YYYY-MM-DD: Kurzer Titel

**Status:** Abgeschlossen / In Arbeit / Geplant

**Betroffene Dateien:**
- `pfad/datei.py`

**Was wurde gemacht:**
Kurze Beschreibung der Änderungen.

**Entscheidungen / Begründungen:**
Warum etwas so gemacht wurde.
```

---

## 2026-06-01: Update copilot-instructions.md und README.md auf Server-Only-Architektur

**Status:** Abgeschlossen

**Betroffene Dateien:**
- `Project/copilot-instructions.md`
- `Project/README.md`

**Was wurde gemacht:**
Beide Markdown-Dateien wurden vollständig überarbeitet, um den aktuellen Architekturstand (Server-Only-Modus, keine lokale DB) abzubilden.

**copilot-instructions.md:**
- Architektur auf Server-Only umgestellt (kein lokaler SQLite-Client mehr)
- Detaillierte Modulbeschreibungen hinzugefügt (remote_core.py, collab_server.py, paths.py)
- Features, Rollen (reader/editor/admin) und Build-Infos aktualisiert
- Hinweise für Änderungen ergänzt (REST-API-Payloads, GUI-Tabs als Module)

**README.md:**
- Von "lokales Projektmanagement-Tool mit SQLite" auf "Server-basiertes Projektmanagement-Tool" umgestellt
- Vollständige Liste aller REST-API-Endpoints (GET/POST/PATCH/DELETE)
- Login-Dialog-Beschreibung mit Registrierung
- Account-Verwaltung mit Admin-Rolle (CLI-Befehle)
- Python-API-Beispiel für Entwickler
- Auto-Sync-Dokumentation (Konfiguration, Intervalle, Features)

**Entscheidungen / Begründungen:**
- Das Projekt hat sich vom lokalen Tool zu einem Server-Client-Modell entwickelt
- Die README muss den aktuellen Stand widerspiegeln, da sie die erste Anlaufstelle für neue Entwickler ist
- copilot-instructions.md ist der zentrale Kontext für Cline, daher muss sie immer aktuell sein

---

## 2026-06-02: Fix PyInstaller-Crash – Modul-Swap-Mechanismus in pmtool.core

**Status:** Abgeschlossen

**Betroffene Dateien:**
- `Project/pmtool/remote_core.py`

**Was wurde gemacht:**
Der Fehler trat auf, wenn die mit GitHub Actions gebaute `.exe` gestartet wurde – die Meldung zeigte einen `ImportError` für `export_csv`, aber der wirkliche Fehler war tiefer:

```
ImportError: cannot import name 'export_csv' from 'pmtool.remote_core'
```

**Ursache (wurde in zwei Schritten erkannt):**
1. **Erste (unvollständige) Diagnose:** Es fehlten `export_csv`, `export_json`, `import_csv`, `import_json` im Import-Statement von `remote_core.py`. Wurde ergänzt – **reichte nicht**.
2. **Echte Ursache:** `pmtool/core/__init__.py` (Zeile 102) macht einen `sys.modules`-Swap:
   ```python
   sys.modules[__name__] = _legacy
   ```
   Das ersetzt das gesamte `pmtool.core`-Modul durch `pmtool.core.legacy`. **PyInstaller kann diesen Swap nicht auflösen** – selbst wenn die Namen im `from pmtool.core import ...` explizit aufgeführt sind. Der gefrorene Importer sucht im originalen (geswappten) Modul und findet nichts.

**Fix:**
- Alle Imports in `remote_core.py`, die `pmtool.core` betreffen, wurden auf **direkte Importe aus den Quellmodulen** umgestellt:
  ```python
  # Statt: from pmtool.core import export_csv, format_date
  # Jetzt: from pmtool.core.legacy import export_csv, format_date
  # Und:   from pmtool.core.reports import build_weekly_project_report_markdown
  ```

**Entscheidungen / Begründungen:**
- Der Modul-Swap-Mechanismus (`sys.modules[__name__] = _legacy`) ist für normalen Python-Betrieb notwendig (er ermöglicht, dass `from pmtool.core import add_task` funktioniert, obwohl die Funktionen in `legacy.py` liegen). Er kann nicht einfach entfernt werden.
- Der Workaround ist, in Build-relevanten Dateien direkt aus den Quellmodulen zu importieren.
- `collab_server.py` ist nicht betroffen, weil es auf dem Server läuft (kein PyInstaller).

**Dokumentation:**
- `copilot-instructions.md`: Abschnitt "PyInstaller-Build: WICHTIG – Modul-Swap-Mechanismus" komplett überarbeitet mit dem korrekten Workaround (direkte Imports).

---

## 2026-06-02: Erstellung von TASK_HISTORY.md für Aufgaben-Dokumentation

**Status:** Abgeschlossen

**Betroffene Dateien:**
- `Project/TASK_HISTORY.md` (neu erstellt)
- `Project/copilot-instructions.md` (ergänzt)

**Was wurde gemacht:**
- `TASK_HISTORY.md` als zentrale Dokumentationsdatei für alle Cline-Tasks erstellt
- Erstes Konzept mit Format-Vorlage und zwei Einträgen (Nachdokumentation + dieser Eintrag)
- `copilot-instructions.md` um einen Abschnitt ergänzt, der auf TASK_HISTORY.md verweist

**Entscheidungen / Begründungen:**
- Einheitliche Dokumentation aller Tasks sorgt für Kontext bei Unterbrechungen
- Verlinkung in copilot-instructions.md stellt sicher, dass Cline immer weiss, wo die History zu finden ist
- Einfaches Markdown-Format – kein zusätzliches Tool nötig

---

## 2026-06-17: Rate-Limit- und Performance-Optimierung

**Status:** Abgeschlossen

**Betroffene Dateien:**
- `pmtool/collab_server.py`
- `pmtool/gui.py`
- `pmtool/ui/tabs/board.py`
- `pmtool/core/legacy.py`
- `copilot-instructions.md`

**Was wurde gemacht:**

**Rate-Limiter (`collab_server.py`):**
- `RATE_LIMIT_REQUESTS_PER_MINUTE` von 60 auf 300 erhöht
- Thread-Safety durch `threading.Lock` für `request_log` hinzugefügt (analog zu `sessions_lock`)
- Lock-Initialisierung in `run_collab_server()` ergänzt

**Redundante DB-Queries reduziert:**
- `refresh_project_combo_boxes()` (`gui.py`): `list_projects()` wird nur noch 1× statt 4× aufgerufen
- `refresh_board()` (`ui/tabs/board.py`): 1 Query statt 4 – alle Tasks einmal laden, in Python nach Status filtern
- `list_task_notes/history` (`core/legacy.py`): unnötigen `get_task()`-Aufruf entfernt (eine DB-Query pro Aufruf gespart)

**Dashboard-Optimierung (`core/legacy.py`):**
- `task_dashboard_counts()`: SQL-Aggregat-Queries (`GROUP BY`) statt Full-Table-Scan + Python-Counting
- `project_dashboard_counts()`: SQL-Aggregat-Query (`GROUP BY`) statt Full-Table-Scan

**Web-UI (`collab_server.py` embedded JS):**
- `reloadAll()` nach Mutationen durch gezielte Reloads ersetzt:
  - Projekt-Mutationen: nur `loadProjects()` + `loadDashboard()`
  - Aufgaben-Mutationen: nur `loadTasks()` + `loadDashboard()`
  - Reduziert von 6 parallelen GETs auf 2 pro Mutation
- Initialer Page-Load bleibt bei `reloadAll()` (alle 6 Endpoints)

**Entscheidungen / Begründungen:**
- Der Rate-Limiter wurde erhöht, weil 60 req/min bei 6 parallelen Requests pro Mutation schnell erreicht waren
- Thread-Safety war notwendig, da `ThreadingHTTPServer` Requests parallel verarbeitet
- Bei der Entfernung von `get_task()` in `list_task_notes/history` wurde auf den redundanten Access-Check verzichtet – der Server authentifiziert bereits auf HTTP-Ebene
- Die Web-UI-Optimierung reduziert die Serverlast am stärksten: von 6 Requests auf 2 pro Mutation