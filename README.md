# Projektmanager

Ein lokales Projektmanagement-Tool mit SQLite und grafischer Oberfläche.

Die Logik ist jetzt in ein Paket mit Unterordner aufgeteilt:

- [pr.py](pr.py) als schlanker Einstiegspunkt
- [pmtool/core](pmtool/core) für Datenbank, Modelle und CRUD
- [pmtool/cli.py](pmtool/cli.py) für die Befehlszeile
- [pmtool/gui.py](pmtool/gui.py) für die grafische Oberfläche
- [pmtool/ui/dialogs.py](pmtool/ui/dialogs.py) für Dialoge und UI-Bausteine
- [pmtool/ui/tabs](pmtool/ui/tabs) für Tab-spezifische GUI-Module
- [pmtool/__main__.py](pmtool/__main__.py) für Start per Modul

Kompatibilität:

- [project_manager_core.py](project_manager_core.py)
- [project_manager_cli.py](project_manager_cli.py)
- [project_manager_gui.py](project_manager_gui.py)

Diese drei Dateien sind jetzt nur noch kompatible Weiterleitungen auf das neue Paket.

Die App kann inzwischen deutlich mehr als eine einfache Aufgabenliste:

- Dashboard mit Kennzahlen und Fälligkeitsübersicht
- Kanban-Ansicht für offene, laufende, blockierte und erledigte Aufgaben
- Aufgaben mit Tags, Kontext, Energielevel, Aufwand und Wiederholungen
- Projekte mit Ziel, Meilenstein und Review-Datum
- Vorlagen für wiederkehrende Arbeit
- Notizen und Verlauf pro Aufgabe
- JSON- und CSV-Export oder -Import
- Schnellerfassung, Kontextmenü und globale Tastenkürzel in der GUI

## Starten

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

Die Windows-EXE wird jetzt automatisch per GitHub Actions gebaut. Der Workflow liegt in [.github/workflows/build-windows-exe.yml](.github/workflows/build-windows-exe.yml) und nutzt [scripts/build_exe.py](scripts/build_exe.py), um `dist/pr.exe` nach `pr.exe` zu kopieren.

Bei Push auf `main` wird die EXE als Artefakt erzeugt. Bei Tag-Releases wird zusätzlich ein Release-Asset veröffentlicht.

## Oberfläche

Die App besteht aus mehreren Tabs:

- Dashboard für schnelle Kennzahlen
- Kanban für Status-Überblick
- Aufgaben für Suche, Filter und Details
- Projekte für Ziele und Meilensteine
- Zeitstrahl für Projekt-Timeline mit Aufgaben, Meilensteinen und aktueller Position
- Vorlagen für Standardaufgaben
- Wochenbericht für Markdown-Vorschau und Export
- Backup für Export und Import

Zusätzlich gibt es in der Topbar:

- **🔄 Sync** für normale Synchronisierung
- **⟳ Full Sync** um den Sync-Cache zu ignorieren und alles neu zu laden
- **Diagnose** mit Server-, Account- und Cache-Status für Troubleshooting
- Anzeige der aktiven **Server-URL**

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
- Mousewheel zum horizontalscrollenItalic
- Automatische Lane-Verwaltung zum Vermeiden von Überlappungen

### Wochenbericht

Der Wochenbericht-Tab unterstützt jetzt:

- scrollbare Eingabebereiche und scrollbare Markdown-Vorschau
- Mehrfach-Risiken für Projekte und Aufgaben
- pro Risiko eigene Werte für Wahrscheinlichkeit und Ausmaß

Oben gibt es eine Schnellerfassung und ein Theme-Menü.

Zusätzlich gibt es oben eine globale Suchleiste. Damit kannst du Funktionen, Projekte und Aufgaben suchen und direkt öffnen.

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
- `Ctrl+8` Backup

## Wichtige Filter

- `Heute` zeigt nur Aufgaben mit Fälligkeitsdatum heute.
- `Diese Woche` zeigt Aufgaben bis 7 Tage voraus.
- `Überfällig` zeigt offene Aufgaben mit abgelaufenem Datum.
- `Blockiert` zeigt Aufgaben mit Status blockiert.
- Zusätzlich kannst du nach Tags, Kontext und Energielevel filtern.

## Befehlszeile

Die GUI ist der Hauptweg, aber die Befehlszeile bleibt für schnelle Aktionen nutzbar.

- `python pr.py add-project "Name"`
- `python pr.py add-task "Titel"`
- `python pr.py list-projects`
- `python pr.py list-tasks`
- `python pr.py overview`
- `python pr.py add-note 1 "Notiztext"`
- `python pr.py add-template "Vorlage" "Titel"`
- `python pr.py list-milestones`
- `python pr.py add-milestone 1 "Meilenstein"`
- `python pr.py update-milestone 1 --title "Neu"`
- `python pr.py delete-milestone 1`
- `python pr.py export-json backup.json`
- `python pr.py export-csv backup-folder`

## Daten

Die Daten werden lokal in `app.db` gespeichert. Es wird nichts in die Cloud synchronisiert.

## Zusammenarbeit und Browser-Zugriff

Die Desktop-App ist ein reines Client-Programm. Der zentrale Server stellt die Web-Login-Seite ohne Port bereit, die Sync-API laeuft jedoch auf Port `8765`. Alle Benutzer synchronisieren ihre lokalen Daten mit diesem Server.

### Browser-Zugriff

Benutzer können sich direkt beim zentralen Server anmelden (ohne Port):

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

## Synchronisierung zwischen mehreren Usern

Die App unterstützt jetzt **Synchronisierung zwischen lokalen EXEs und einem zentralen Server**! 🔄

### Szenario

Jeder User arbeitet mit seiner eigenen lokalen EXE:
- Florian hat `pr.exe` auf seinem PC
- Alice hat `pr.exe` auf ihrem PC
- Ein zentraler Server (`100.80.250.84:8765`) speichert die gemeinsamen Daten

### Wie es funktioniert

1. **Florian arbeitet lokal:**
   ```bash
   pr.exe  # Lokale Arbeit in Offline-Mode
   ```

2. **Browser-Login:**
   - Die EXE oeffnet den Login im Browser ohne Port (z.B. `https://100.80.250.84/login?...`).
   - Die Desktop-Anmeldung wird ueber diese Host-URL bestaetigt.
   - Fuer Sync wird weiterhin die API auf `:8765` verwendet.

3. **Synchronisierung initiieren:**
   - Button **"🔄 Sync"** in der GUI klicken
   - App sendet alle lokalen Änderungen zum Server
   - Server speichert die Daten mit Timestamps

   Optional:
   - **"⟳ Full Sync"** lädt alle Daten neu (ignoriert den letzten Sync-Zeitpunkt)
   - **"Diagnose"** zeigt aktiven Server, Account, Session und Sync-Cache an

3. **Alice synchronisiert:**
   - Sie klickt auch **"🔄 Sync"**
   - App lädt Florinas Daten herunter
   - Beide haben nun identische Daten lokal

### API-Endpoints

Der Server bietet folgende Sync-Endpoints:

**GET Endpoints** (Daten herunterladen):
- `GET /api/sync/projects?since=2026-05-07T...` - Projekte abrufen
- `GET /api/sync/tasks?since=2026-05-07T...` - Aufgaben abrufen
- `GET /api/sync/milestones?since=2026-05-07T...` - Meilensteine abrufen
- `GET /api/sync/templates?since=2026-05-07T...` - Vorlagen abrufen

**POST Endpoint** (Daten hochladen):
- `POST /api/sync/upload` - JSON mit lokalen Änderungen

### Python-API

```python
from pmtool.sync import SyncManager

# Sync initialisieren
sync = SyncManager("https://100.80.250.84:8765", auth_cookie="...")

# Daten vom Server herunterladen
download_result = sync.sync_from_server()
print(download_result['projects'])
print(download_result['tasks'])

# Lokale Änderungen hochladen
projects = [...]  # Modified projects
result = sync.sync_to_server(projects=projects)
if result.get('conflicts'):
    print("Konflikte gefunden:", result['conflicts'])
```

### Konflikt-Handling

Falls Konflikte auftreten (z.B. beide User ändern dieselbe Aufgabe):
- Server gibt Liste der Konflikte zurück
- GUI zeigt Konflikt-Dialog mit Details
- User kann Änderungen manuell abgleichen

### Auto-Synchronisierung

Automatische Synchronisierung im Hintergrund:

```python
from pmtool.sync import SyncManager, AutoSyncManager

sync = SyncManager("https://100.80.250.84:8765", auth_cookie="...")

# Auto-Sync alle 5 Minuten (300 Sekunden)
auto_sync = AutoSyncManager(
    sync,
    interval_seconds=300,  # 5 minutes
    enabled=True,
    on_sync_callback=lambda result: print(f"Synced: {result['status']}")
)

# Intervall ändern
auto_sync.set_interval(600)  # Jetzt alle 10 Minuten

# Deaktivieren
auto_sync.set_enabled(False)

# Status abfragen
status = auto_sync.get_status()
```

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


