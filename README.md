# Projektmanager

Serverbasierter Projektmanager mit Weboberflaeche, Windows-Desktop-App und CLI. Alle Projektdaten liegen zentral auf dem Server in SQLite; Windows-Clients arbeiten nicht offline und fuehren keine lokale Projektdatenbank mehr.

Interne Arbeitsnotizen fuer Codex und Projektentscheidungen stehen in `PROJECT_INFO_FOR_CODEX.md`.

## Was ist aktuell enthalten?

- Zentrale Projekt-, Aufgaben-, Meilenstein- und Vorlagenverwaltung
- Browseroberflaeche mit Login, Projektansicht, Arbeitsbereich, Reports und Downloadbereich
- Windows-Desktop-App (`pr.exe`) mit Browser-Login gegen den bestehenden Server
- CLI fuer Projekte, Aufgaben, Vorlagen, Meilensteine, Notizen und Verlauf
- Rollenmodell mit `reader`, `editor` und `admin`
- Accountverwaltung per CLI auf dem Server
- Rolling-Latest-Build fuer `pr.exe` ueber GitHub Actions

## Benutzerstart auf Windows

1. Im Browser am Projektmanager-Server anmelden.
2. Im Bereich **Download** die aktuelle `pr.exe` laden.
3. `pr.exe` starten.
4. Beim ersten Start die Serveradresse eingeben, zum Beispiel `https://pm.example.com`.
5. Die Anmeldung im automatisch geoeffneten Browser abschliessen.

Die Serveradresse wird als nicht-sensible Benutzereinstellung gespeichert. `PM_BASE_URL` ueberschreibt diese Einstellung fuer Tests oder Administration.

Fuer lokale Tests gegen den aktuellen Testserver kann `start-windows-test.bat` verwendet werden, wenn der Projektordner auf dem Windows-PC liegt. Die Datei setzt `PM_BASE_URL` und startet `pr.py`.

## Server installieren

Voraussetzungen:

- Python 3.11 oder neuer
- `bcrypt` aus `requirements.txt`
- Fuer produktiven Betrieb: HTTPS-Reverse-Proxy, zum Beispiel Caddy

```bash
cd /srv/Projektmanager/Project
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

export PMTOOL_DATA_DIR=/srv/pmtool/data
export PMTOOL_PUBLIC_BASE_URL=https://pm.example.com
export PMTOOL_TRUST_PROXY_HEADERS=1

python3 -m pmtool.collab_server
```

Alternativ startet ein installiertes Paket den Server mit:

```bash
pmtool-server
```

Der Python-Server lauscht standardmaessig auf Port `8765`. Produktiv sollte er nur intern erreichbar sein; HTTPS und oeffentliche Erreichbarkeit gehoeren an den Reverse-Proxy.

## Server dauerhaft aktiv halten

Der Server soll im Betrieb standardmaessig immer laufen. Dafuer liegt eine systemd-Vorlage unter `deploy/systemd/pmtool.service`. Sie startet den Projektmanager beim Boot automatisch und setzt `Restart=always`, damit der Prozess nach einem Fehler wieder hochkommt.

Einmalige Einrichtung auf dem Server:

```bash
cd /home/florian/Projektmanager/Project
sudo cp deploy/systemd/pmtool.service /etc/systemd/system/pmtool.service
sudo systemctl daemon-reload
sudo systemctl enable --now pmtool.service
sudo systemctl status pmtool.service
```

Nach Codeaenderungen wird der Server nicht manuell beendet, sondern nur neu gestartet:

```bash
./scripts/restart_server.sh
```

Das Script fuehrt `sudo systemctl restart pmtool.service` aus und zeigt danach direkt den Status. Falls der Service auf einem System anders heisst, kann der Name ueberschrieben werden:

```bash
PMTOOL_SERVICE_NAME=anderer-name.service ./scripts/restart_server.sh
```

Nicht im Normalbetrieb verwenden:

```bash
sudo systemctl stop pmtool.service
```

`stop` ist nur fuer Wartungsfaelle gedacht. Der Standardbetrieb ist: Service aktiviert lassen, bei Aenderungen restart ausfuehren.

## Daten und Konfiguration

Der Server speichert seine Daten in `PMTOOL_DATA_DIR`. Ohne diese Variable nutzt das Tool ein Benutzerverzeichnis.

Wichtige Dateien:

- `app.db`: zentrale SQLite-Datenbank fuer Projekte, Aufgaben, Vorlagen und Historie
- `collab_accounts.json`: Accounts, Rollen, Passwort-Hashes, API-Key-Hashes und Audit-Log
- `client.json`: gespeicherte Desktop-Serveradresse auf Client-Systemen

Wichtige Umgebungsvariablen:

- `PMTOOL_DATA_DIR`: Datenverzeichnis fuer `app.db` und `collab_accounts.json`
- `PMTOOL_PUBLIC_BASE_URL`: oeffentliche Serveradresse, besonders hinter HTTPS-Proxy
- `PMTOOL_TRUST_PROXY_HEADERS=1`: nur setzen, wenn ausschliesslich der vertrauenswuerdige Proxy den Python-Server erreicht
- `PMTOOL_GITHUB_REPOSITORY`: Repository fuer Rolling-Latest-Downloads, Standard `Heizkoerper83/Projektmanager`
- `PMTOOL_FALLBACK_EXE`: lokaler Fallback-Pfad fuer `pr.exe`; wird nur mit passender `.sha256` angeboten
- `PMTOOL_ORPHAN_PROJECT_OWNER`: optionaler Account fuer bewusst gestartete Alt-Datenmigrationen
- `PM_BASE_URL`: Client- und CLI-Serveradresse; hat Vorrang vor gespeicherter Client-Konfiguration
- `PM_EMAIL` und `PM_PASSWORD`: optionale CLI-Login-Daten fuer Automatisierung
- `PMTOOL_CLIENT_CONFIG`: optionaler Pfad fuer die Desktop-Client-Konfiguration

## Accounts verwalten

Accountbefehle laufen lokal auf dem Server und bearbeiten die Accounts-Datei. Passwoerter muessen mindestens 12 Zeichen lang sein.

```bash
python3 pr.py collab-add-user admin@example.com --role admin
python3 pr.py collab-activate-user admin@example.com --api-key act_xxxxx
python3 pr.py collab-list-users
python3 pr.py collab-set-role user@example.com editor
python3 pr.py collab-set-password user@example.com
python3 pr.py collab-disable-user user@example.com
python3 pr.py collab-enable-user user@example.com
python3 pr.py collab-rotate-key user@example.com
python3 pr.py collab-delete-user user@example.com
```

Rollen:

- `reader`: kann lesen
- `editor`: kann Projekte, Aufgaben, Vorlagen und Meilensteine bearbeiten
- `admin`: kann administrative Web- und Accountfunktionen nutzen

Neue Accounts werden zunaechst als pending angelegt und muessen mit dem ausgegebenen Aktivierungs-API-Key aktiviert werden.

## Desktop und CLI nutzen

Desktop-Client starten:

```bash
PM_BASE_URL=http://127.0.0.1:8765 python3 pr.py
```

CLI gegen einen Server verwenden:

```bash
python3 pr.py --server http://127.0.0.1:8765 --email user@example.com overview
python3 pr.py --server http://127.0.0.1:8765 --email user@example.com list-projects
python3 pr.py --server http://127.0.0.1:8765 --email user@example.com list-tasks --due-filter today
```

Wenn `--password` nicht gesetzt ist, fragt die CLI interaktiv nach dem Passwort. Fuer Automatisierung koennen `PM_BASE_URL`, `PM_EMAIL` und `PM_PASSWORD` genutzt werden.

Wichtige CLI-Befehle:

- Projekte: `add-project`, `update-project`, `delete-project`, `list-projects`
- Aufgaben: `add-task`, `update-task`, `delete-task`, `complete-task`, `list-tasks`, `next`, `overview`
- Notizen und Verlauf: `add-note`, `list-notes`, `history`
- Vorlagen: `add-template`, `update-template`, `use-template`, `delete-template`, `list-templates`
- Meilensteine: `add-milestone`, `update-milestone`, `delete-milestone`, `list-milestones`
- Lokal/Admin: `gui`, `init`, `collab-*`

## Entwicklung

```bash
cd /home/florian/Projektmanager/Project
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
```

Server lokal starten:

```bash
PMTOOL_PUBLIC_BASE_URL=http://127.0.0.1:8765 python3 -m pmtool.collab_server
```

Client gegen den lokalen Server starten:

```bash
PM_BASE_URL=http://127.0.0.1:8765 python3 pr.py
```

CLI-Paket-Einstiegspunkte:

```bash
python3 -m pmtool --help
pmtool --help
pmtool-server
```

Tests:

```bash
python3 -m unittest discover -s tests -v
```

## Builds und Veroeffentlichung

Bei Pushes auf `main` baut GitHub Actions:

- `pr.exe`
- `pr.exe.sha256`
- `build-metadata.json`

Die Artefakte werden als Actions-Artefakt gespeichert und das Release `rolling-latest` wird aktualisiert. Die Weboberflaeche bietet primaer dieses Release an. Wenn GitHub nicht erreichbar ist, wird nur ein lokaler Fallback angeboten, dessen `.sha256` zur `pr.exe` passt.

Lokaler Build-Helfer:

```bash
python3 scripts/build_exe.py
```

## Backup und Betrieb

Eine konsistente Sicherung muss mindestens diese Dateien enthalten:

- `app.db`
- `collab_accounts.json`

Vor Migrationen oder Deployments zuerst beide Dateien sichern. Private Schluessel, Zertifikate, Datenbanken, virtuelle Umgebungen, Builds und EXE-Artefakte gehoeren nicht ins Repository.

Bekannte Betriebsnotizen:

- Nach Server-Codeaenderungen muss der laufende Serverprozess neu gestartet werden.
- `PM_BASE_URL` hat Vorrang vor der gespeicherten Desktop-Konfiguration.
- Eine falsch gespeicherte Windows-Client-URL liegt typischerweise unter `C:\Users\<Name>\.pmtool\client.json`.
- Fuer produktiven Betrieb HTTPS verwenden und den Python-Server nicht direkt oeffentlich exponieren.
