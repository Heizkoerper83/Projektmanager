# Projektmanager

Ein **Server-basiertes Projektmanagement-Tool** mit Desktop-GUI und CLI.

Die App arbeitet im **Server-Only-Modus**: alle CRUD-Operationen laufen direkt gegen die REST-API eines zentralen Kollaborationsservers. Es gibt keine lokale Datenbank auf dem Client.

## Architektur

- **Desktop-Client**: tkinter-GUI (`pmtool/gui.py`), kommuniziert ausschliesslich über HTTP/REST
- **Server**: Python-Server (`pmtool/collab_server.py`) mit SQLite-DB, Web-Login und API
- **Kein lokaler Offline-Mode** – alle Daten liegen zentral auf dem Server

### Datenbank-Standorte (wichtig für Kollaboration)

| Modus | Datenbank-Standort | Beschreibung |
|---|---|---|
| **Lokal** (`pr.exe solo`) | `~/.pmtool/app.db` pro PC | Jeder PC hat seine eigene isolierte Datenbank |
| **Server** (`collab_server.py` läuft auf Server) | Nur auf dem Server (dort wo `collab_server.py` läuft) | Alle Clients greifen auf **dieselbe** zentrale SQLite-DB zu |

- `app.db` und `collab_accounts.json` liegen **nur auf dem Server**, wenn der Server-Modus aktiv ist.
- Die Dateien `Project/app.db` und `Project/collab_accounts.json` im Repository sind Entwicklungs-Relikte und werden **nicht** mit dem Release-Zip ausgeliefert.
- Jeder PC, der `pr.exe` startet, bekommt automatisch eine frische leere Datenbank in `~/.pmtool/`.

Das Projekt ist in ein Paket mit Unterordnern aufgeteilt:

- [pr.py](pr.py) als schlanker Einstiegspunkt
- [pmtool/remote_core.py](pmtool/remote_core.py) für die REST-API-Kommunikation
- [pmtool/core](pmtool/core) für Datenbank-Modelle, Reports und Hilfsfunktionen
- [pmtool/gui.py](pmtool/gui.py) für die grafische Oberfläche
- [pmtool/cli.py](pmtool/cli.py) für die Befehlszeile
- [pmtool/ui/dialogs.py](pmtool/ui/dialogs.py) für Dialoge und UI-Bausteine
- [pmtool/ui/tabs](pmtool/ui/tabs) für Tab-spezifische GUI-Module
- [pmtool/collab_server.py](pmtool/collab_server.py) für den Kollaborations-Server
- [pmtool/collab_accounts.py](pmtool/collab_accounts.py) für Account-Verwaltung
- [pmtool/__main__.py](pmtool/__main__.py) für Start per Modul

Zusätzliche Ordner:

- [pmtool/reports](pmtool/reports) für Auswertungen
- [pmtool/sync.py](pmtool/sync.py) für Sync-Logik
- [scripts](scripts) für Build-Helfer
- [tests](tests) für Regression-Tests

## Features

- **Dashboard** mit Kennzahlen (Aufgaben/Projekte nach Status)
- **Kanban-Board** – 4 Spalten: offen, in Arbeit, blockiert, erledigt
- **Aufgaben** mit Titel, Details, Status, Priorität (1-5), Fälligkeitsdatum, Tags, Kontext, Energie-Level (low/medium/high), Aufwand (Minuten), Wiederholungen
- **Risikobewertung** pro Aufgabe und Projekt (multipel: mehrere Risk-Rows mit Wahrscheinlichkeit/Ausmaß/Gegenmassnahme)
- **Projekte** mit Name, Team, Beschreibung, Status, Ziel, Meilenstein, Review-Datum
- **Vorlagen** für wiederkehrende Aufgaben (mit Due-Offset)
- **Wochenbericht** – Markdown-Generierung
- **Global Search** – projekt-, aufgaben- und funktionsübergreifend
- **Schnellerfassung** neuer Aufgaben in der Topbar
- **Theme-Umschaltung** Hell/Dunkel
- **Account-Verwaltung** – Login/Registrierung, Rollen (reader/editor/admin)
- **Notizen und Verlauf** pro Aufgabe
- **Projekt-Sharing** zwischen Benutzern
- **Auto-Sync** im Hintergrund (konfigurierbares Intervall)
- **Tastenkürzel** (siehe unten)

## Starten

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
python pr.py
```

Alternativ direkt als Paket:

```bash
python -m pmtool
```

Ohne Argumente startet direkt die grafische Oberfläche. Falls du lieber explizit starten willst:

```bash
python pr.py gui
```

### EXE automatisch bauen

Die Windows-EXE wird automatisch per GitHub Actions gebaut. Der Workflow liegt in [.github/workflows/build-windows-exe.yml](.github/workflows/build-windows-exe.yml) und nutzt [scripts/build_exe.py](scripts/build_exe.py), um `dist/pr.exe` nach `pr.exe` zu kopieren.

Bei Push auf `main` wird die EXE als Artefakt erzeugt. Bei Tag-Releases wird zusätzlich ein Release-Asset veröffentlicht.

## Oberfläche

Die App besteht aus mehreren Tabs:

- **Dashboard** für schnelle Kennzahlen
- **Kanban** für Status-Überblick
- **Aufgaben** für Suche, Filter und Details
- **Projekte** für Ziele und Meilensteine
- **Zeitstrahl** für Projekt-Timeline mit Aufgaben, Meilensteinen und aktueller Position
- **Vorlagen** für Standardaufgaben
- **Wochenbericht** für Markdown-Vorschau

Zusätzlich gibt es in der Topbar:

- Anzeige der aktiven **Server-URL** und des angemeldeten Benutzers mit Rollen-Badge
- **Konten**-Button (nur für Admin-Rolle)
- **Mein Konto**-Menü (Abmelden, Account wechseln)
- **EXE-/App herunterladen**-Button
- **Global Search**-Leiste

### Login-Dialog

Beim Start erscheint ein Login-Dialog mit zwei Tabs:
- **Anmelden** – bestehende Benutzer mit E-Mail und Passwort
- **Registrieren** – neue Benutzer mit E-Mail, Passwort (min. 8 Zeichen) und Passwort-Stärke-Anzeige

### Projektfokus

In der Projektansicht gibt es rechts den Projektfokus: Sobald du links ein Projekt auswählst, siehst du direkt die zugehörigen Aufgaben, Meilensteine, Vorlagen und die wichtigsten Kennzahlen dieses Projekts.

### Zeitstrahl

Im Zeitstrahl-Tab kannst du ein Projekt auswählen und den Verlauf auf einer gemeinsamen Zeitleiste sehen.

**Visuelle Elemente:**
- Horizontale Zeitlinie mit monatlichen Markierungen für schnelle Orientierung
- **Meilensteine** als Rauten (◆) direkt auf dem Strahl, mit Namen beschriftet
  - Grün (✓): Erledigt
  - Gold: Offen
- **Aufgaben** als Punkte (●) abwechselnd oben/unten, verbunden mit dem Strahl
  - Grün: Erledigt
  - Orange: In Arbeit
  - Blau: Offen
  - Rot: Blockiert
- Rote gestrichelte Linie mit "HEUTE" Label für aktuelle Position

**Statistiken:**
- Live-Fortschrittsanzeige (z.B. "Aufgaben: 15 (✓5 ⟳3 ✗1 ○6)")
- Meilenstein-Übersicht (n/m erledigt)
- Prozentuale Completion-Rate

**Interaktionen:**
- Hover über beliebigen Punkt/Raute zeigt Details (Titel, Status, Dates, Aufwand)
- Mousewheel zum horizontalscrollen
- Automatische Lane-Verwaltung zum Vermeiden von Überlappungen

### Wochenbericht

Der Wochenbericht-Tab unterstützt:
- scrollbare Eingabebereiche und scrollbare Markdown-Vorschau
- Mehrfach-Risiken für Projekte und Aufgaben
- pro Risiko eigene Werte für Wahrscheinlichkeit und Ausmaß

### Tastenkürzel

- `Ctrl+N` neue Aufgabe
- `Ctrl+Shift+N` neues Projekt
- `Ctrl+E` ausgewählte Aufgabe bearbeiten
- `Ctrl+D` ausgewählte Aufgabe duplizieren
- `Entf` ausgewählte Aufgabe löschen
- `F5` alles aktualisieren
- `Ctrl+F` Suche fokussieren
- `Ctrl+K` globale Suche fokussieren
- `Ctrl+1` Dashboard
- `Ctrl+2` Kanban
- `Ctrl+3` Aufgaben
- `Ctrl+4` Projekte
- `Ctrl+5` Zeitstrahl
- `Ctrl+6` Vorlagen
- `Ctrl+7` Wochenbericht

## Wichtige Filter

- `Heute` zeigt nur Aufgaben mit Fälligkeitsdatum heute.
- `Diese Woche` zeigt Aufgaben bis 7 Tage voraus.
- `Überfällig` zeigt offene Aufgaben mit abgelaufenem Datum.
- `Blockiert` zeigt Aufgaben mit Status blockiert.
- Zusätzlich kannst du nach Tags, Kontext und Energielevel filtern.

## Befehlszeile (CLI)

Die GUI ist der Hauptweg, aber die Befehlszeile bleibt für schnelle Aktionen nutzbar.

```bash
python pr.py add-project "Name"
python pr.py add-task "Titel"
python pr.py list-projects
python pr.py list-tasks
python pr.py overview
python pr.py add-note 1 "Notiztext"
python pr.py add-template "Vorlage" "Titel"
python pr.py list-milestones
python pr.py add-milestone 1 "Meilenstein"
python pr.py update-milestone 1 --title "Neu"
python pr.py delete-milestone 1
```

## Zusammenarbeit und Browser-Zugriff

Die Desktop-App ist ein reines Client-Programm. Der zentrale Server stellt die Web-Login-Seite ohne Port per HTTPS bereit, die API läuft per HTTP auf Port `8765`. Alle Benutzer arbeiten direkt gegen diesen Server.

### Browser-Zugriff

Benutzer können sich direkt beim zentralen Server anmelden (ohne Port, HTTPS):

```bash
https://100.80.250.84/login
```

Nach erfolgreicher Authentifizierung steht die Web-Oberfläche zur Verfügung:

```bash
https://100.80.250.84/app
```

### Account-Verwaltung

`collab-add-user` gibt einen Aktivierungs-API-Key genau einmal aus. Der neue Account bleibt pending, bis ein Admin ihn final aktiviert.

Alle Account-Verwaltung erfolgt über die CLI:

```bash
python pr.py collab-list-users
python pr.py collab-set-role bob@example.com editor
python pr.py collab-disable-user bob@example.com
python pr.py collab-enable-user bob@example.com
python pr.py collab-activate-user bob@example.com --api-key act_xxxxx
python pr.py collab-rotate-key alice@example.com
python pr.py collab-delete-user bob@example.com
```

Verfügbare Rollen:

- `reader`: nur `GET` Endpunkte (read-only)
- `editor`: darf auch `POST` und `PATCH` ausführen
- `admin`: zusätzlich Account-Verwaltung in der GUI

### Features der Web-Oberfläche

- Aufgaben-Detailansicht beim Klick auf eine Aufgabe
- Suche und Statusfilter in der Aufgabenliste
- Inline-Statusänderung direkt in der Tabelle (Editor-Rolle)

Die Browser-Session läuft über Cookie und bleibt gültig, solange die Session nicht abläuft.

## Tests

Eine kleine Regression-Test-Suite für Core-Flows liegt in [tests/test_core.py](tests/test_core.py).

```bash
python -m unittest discover -s tests -v
```

Alternativ mit `pytest`:

```bash
python -m pytest -q
```

## Copilot-Kontext

Eine aktuelle, kurze Projektzusammenfassung für Copilot liegt in
[copilot-instructions.md](copilot-instructions.md). Bitte diese Datei bei grösseren Änderungen
am Projekt mit aktualisieren.

## API-Endpoints (Server)

Der Server bietet folgende REST-Endpoints:

**GET Endpoints:**
- `GET /api/projects` – Projekte abrufen
- `GET /api/tasks?project_id=X&status=...` – Aufgaben abrufen (mit Filtern)
- `GET /api/tasks/{id}` – Einzelaufgabe abrufen
- `GET /api/tasks/{id}/notes` – Notizen einer Aufgabe
- `GET /api/tasks/{id}/history` – Verlauf einer Aufgabe
- `GET /api/milestones?project_id=X` – Meilensteine abrufen
- `GET /api/templates` – Vorlagen abrufen
- `GET /api/dashboard` – Dashboard-Kennzahlen
- `GET /api/sync/accounts` – Accounts abrufen (für Admin)
- `GET /api/sync/projects?since=...` – Sync: Projekte
- `GET /api/sync/tasks?since=...` – Sync: Aufgaben
- `GET /api/sync/milestones?since=...` – Sync: Meilensteine
- `GET /api/sync/templates?since=...` – Sync: Vorlagen
- `GET /api/sync/project-shares?since=...` – Sync: Projekt-Freigaben
- `GET /api/projects/{id}/shares` – Freigaben eines Projekts

**POST Endpoints:**
- `POST /api/projects` – Projekt anlegen
- `POST /api/tasks` – Aufgabe anlegen
- `POST /api/tasks/{id}/notes` – Notiz hinzufügen
- `POST /api/milestones` – Meilenstein anlegen
- `POST /api/templates` – Vorlage anlegen
- `POST /api/tasks/from-template` – Aufgabe aus Vorlage erstellen
- `POST /api/sync/upload` – Änderungen hochladen

**PATCH Endpoints:**
- `PATCH /api/projects/{id}` – Projekt aktualisieren
- `PATCH /api/tasks/{id}` – Aufgabe aktualisieren
- `PATCH /api/milestones/{id}` – Meilenstein aktualisieren
- `PATCH /api/templates/{id}` – Vorlage aktualisieren

**DELETE Endpoints:**
- `DELETE /api/projects/{id}` – Projekt löschen
- `DELETE /api/tasks/{id}` – Aufgabe löschen
- `DELETE /api/milestones/{id}` – Meilenstein löschen
- `DELETE /api/templates/{id}` – Vorlage löschen

### Python-API (für Entwickler)

```python
from pmtool.remote_core import configure_session, list_projects, list_tasks

# Session konfigurieren
configure_session("https://100.80.250.84:8765", "session_id", account={"email": "user@example.com", "role": "editor"})

# Daten abrufen
projects = list_projects()
tasks = list_tasks(project_id=1)
```

### Auto-Synchronisierung

Automatische Synchronisierung im Hintergrund:

```python
from pmtool.sync import SyncManager, AutoSyncManager

sync = SyncManager("https://100.80.250.84:8765", auth_cookie="...")

# Auto-Sync alle 5 Minuten (300 Sekunden)
auto_sync = AutoSyncManager(
    sync,
    interval_seconds=300,
    enabled=True,
    on_sync_callback=lambda result: print(f"Synced: {result['status']}")
)

# Intervall ändern
auto_sync.set_interval(600)  # Jetzt alle 10 Minuten

# Deaktivieren
auto_sync.set_enabled(False)
```

## PyInstaller-Build: Bekannte Einschränkung

Das Modul `pmtool/core/__init__.py` verwendet einen `sys.modules`-Swap-Trick (`sys.modules[__name__] = _legacy`), um `pmtool.core` durch `pmtool.core.legacy` zu ersetzen. **PyInstaller kann diesen Swap nicht korrekt auflösen.** Daher müssen alle Namen, die aus `pmtool.core` importiert werden sollen, **explizit** im `from pmtool.core import (...)`-Statement in `pmtool/remote_core.py` aufgeführt werden.

**Debugging unter Windows:**
Wenn die `.exe` sofort wieder schliesst, starte sie per Kommandozeile:
```cmd
C:\Users\...> pr.exe
```
Die Fehlermeldung zeigt dann, welcher Import fehlschlägt.

---

**In der GUI:**
1. Button **"⚙ Auto-Sync"** klicken
2. Checkbox **"Auto-Sync aktivieren"** aktivieren
3. Intervall wählen (60s, 300s, 600s, 900s, 1800s)
4. **"Übernehmen"** klicken
5. Status wird in der Topbar angezeigt: **"Auto-Sync: alle 300s"**

**Auto-Sync speichert die Konfiguration** in `~/.pmtool_autosync_config.json` und stellt sie beim nächsten Start wieder her.

**Features:**
- ✅ Background-Thread für regelmäßige Syncs
- ✅ Konfigurierbare Intervalle (60s bis 3600s)
- ✅ Enable/Disable Toggle
- ✅ Fehlertoleranz (ignoriert Offline-Fehler)
- ✅ Callback-System für Status-Updates
- ✅ Auto-Refresh UI nach erfolgreichem Sync