# Projektmanager

Serverbasierter Projektmanager mit Windows-Desktop-App, CLI und Browseroberfläche. Alle Projektdaten liegen zentral in der SQLite-Datenbank des Servers; der Client besitzt keinen Offline- oder Solo-Modus.

## Für Benutzer: Windows-App starten

1. Am Projektmanager-Server anmelden und im Bereich **Download** die Datei `pr.exe` aus dem Rolling-Latest-Release laden.
2. `pr.exe` starten.
3. Beim ersten Start die HTTPS-Adresse des Projektmanager-Servers eingeben.
4. Die Anmeldung im geöffneten Browser abschließen.

Die Serveradresse wird als nicht-sensible Benutzereinstellung gespeichert. `PM_BASE_URL` überschreibt sie für Tests und Administration.

## Server installieren

Voraussetzungen: Python 3.11 oder neuer, Caddy für produktives HTTPS.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
export PMTOOL_DATA_DIR=/srv/pmtool/data
export PMTOOL_PUBLIC_BASE_URL=https://pm.example.com
export PMTOOL_TRUST_PROXY_HEADERS=1
python3 -m pmtool.collab_server
```

Caddy leitet HTTPS intern an `127.0.0.1:8765` weiter. Der Python-Server sollte nicht direkt öffentlich erreichbar sein.

Wichtige Servervariablen:

- `PMTOOL_DATA_DIR`: Verzeichnis für `app.db` und `collab_accounts.json`
- `PMTOOL_PUBLIC_BASE_URL`: öffentliche HTTPS-Adresse
- `PMTOOL_TRUST_PROXY_HEADERS=1`: nur setzen, wenn ausschließlich der vertrauenswürdige Proxy den Server erreicht
- `PMTOOL_GITHUB_REPOSITORY`: Quelle des Rolling-Latest-Release
- `PMTOOL_FALLBACK_EXE`: lokale `pr.exe`; sie wird nur bei passender `.sha256`-Datei angeboten
- `PMTOOL_ORPHAN_PROJECT_OWNER`: optionaler Account für eine bewusst gestartete Alt-Datenmigration

## Accounts

```bash
python3 pr.py collab-add-user admin@example.com --role admin
python3 pr.py collab-activate-user admin@example.com --api-key act_xxxxx
python3 pr.py collab-set-role user@example.com editor
```

Passwörter werden interaktiv abgefragt. Rollen sind `reader`, `editor` und `admin`.

## Entwicklung

```bash
python3 -m pip install -r requirements-dev.txt
PM_BASE_URL=http://127.0.0.1:8765 python3 pr.py
python3 pr.py --server http://127.0.0.1:8765 --email user@example.com list-projects
python3 -m unittest discover -s tests -v
```

`python3 pr.py` entspricht dem Start der EXE. `python3 -m pmtool` und das installierte Kommando `pmtool` stellen die CLI bereit; `pmtool-server` startet den Server.

## Builds und Veröffentlichung

Bei jedem Push auf `main` baut GitHub Actions `pr.exe`, `pr.exe.sha256` und `build-metadata.json`. Der Build wird als Actions-Artefakt gespeichert und aktualisiert zusätzlich das Release `rolling-latest`. Die Weboberfläche bietet dieses Release primär an und verwendet bei GitHub-Ausfall ausschließlich einen lokal checksum-validierten Fallback.

## Backup und Betrieb

Die zentrale Sicherung muss mindestens `app.db` und `collab_accounts.json` umfassen. Vor Migrationen ist eine konsistente Kopie beider Dateien anzulegen.

Private Schlüssel und Zertifikate gehören nicht ins Repository. Die zuvor versionierten Schlüssel müssen auf dem produktiven System rotiert werden. Eine Entfernung aus der Git-Historie ist ein separater koordinierter Betriebsschritt.
