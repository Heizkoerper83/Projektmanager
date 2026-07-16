# PROJECT INFO FOR CODEX

Diese Datei ist die zentrale Arbeitsnotiz fuer dieses Projekt. Vor neuen Aenderungen zuerst hier hineinschauen.

## Projektstand

- Projektpfad: `/home/florian/Projektmanager/Project`
- Hauptdatei: `pr.py`
- Zentraler Server: `100.80.250.84`
- Dieser Workspace ist direkt der Server-Workspace auf `100.80.250.84`; Codeaenderungen hier liegen sofort auf dem Server-Dateisystem. Laufende Serverprozesse muessen nach Server-Codeaenderungen trotzdem neu gestartet werden.
- Aktuelle Server-URL fuer Tests: `http://100.80.250.84:8765`
- Zielarchitektur: zentraler Serverbetrieb, keine lokale Projektdatenbank auf Windows-Clients, kein Offline-/Sync-Modus.
- Windows ist die primaere Desktopplattform.

## Wichtige implementierte Aenderungen

- Zentrale Konfiguration ergaenzt:
  - `pmtool/config.py`
  - `pmtool/client_config.py`
- `pr.py` startet ohne Argumente als Endnutzer-Client:
  - Server-URL wird beim ersten Start abgefragt.
  - Gespeicherte URL liegt im Benutzerprofil.
  - `PM_BASE_URL` ueberschreibt die gespeicherte URL.
  - Browser-Login und GUI-Start bleiben der normale Nutzerfluss.
- Hardcodierte alte Serverwerte wurden aus dem Client entfernt.
- Rollenmodell vereinheitlicht:
  - `reader`
  - `editor`
  - `admin`
- Serverkonfiguration ergaenzt:
  - `PMTOOL_PUBLIC_BASE_URL`
  - `PMTOOL_TRUST_PROXY_HEADERS`
  - `PMTOOL_GITHUB_REPOSITORY`
  - `PMTOOL_FALLBACK_EXE`
  - `PMTOOL_ORPHAN_PROJECT_OWNER`
- Cookies werden je nach HTTPS-/Proxy-Konfiguration sicherer gesetzt.
- Alte Sync-/Offline-Pfade entfernt:
  - `pmtool/sync.py` geloescht
  - `/api/sync/*` entfernt
- Core-Modul bereinigt:
  - `pmtool/core/legacy.py` wurde zu `pmtool/core/service.py`
  - `pmtool/core/__init__.py` ersetzt sich nicht mehr per `sys.modules`
- GitHub Actions Workflow erweitert:
  - baut `pr.exe`
  - erzeugt `pr.exe.sha256`
  - erzeugt `build-metadata.json`
  - laedt Actions-Artefakt hoch
  - aktualisiert Rolling-Latest-Release `rolling-latest`
- Sensible und binaere Dateien sollen nicht mehr normal im Repository gepflegt werden:
  - Zertifikat/private Key geloescht
  - `pr.exe` und `pr.exe.sha256` geloescht
  - `.gitignore` erweitert
- Abhaengigkeiten getrennt:
  - `requirements.txt` fuer Laufzeit
  - `requirements-dev.txt` fuer Entwicklung/Build
  - `pyproject.toml` ergaenzt
- README wurde auf serverbasierten Betrieb umgeschrieben.
- Caddy-Beispiel wurde auf HTTPS/Proxy-Header angepasst.
- Testdatei `tests/test_configuration.py` ergaenzt.

## Verifikation bisher

- Unit Tests liefen erfolgreich:
  - `python3 -m unittest discover -s tests -v`
  - Ergebnis: 24 Tests bestanden
- Python Compile-Check lief erfolgreich.
- GitHub Workflow YAML wurde lokal syntaktisch geprueft.
- Suche nach alten Sync-/Legacy-/Hardcode-Resten ergab keine relevanten Treffer.

## Lokaler Windows-Test fuer den Benutzer

Der Benutzer moechte auf seinem Windows-PC testen, nicht auf dem Server.

Ein Windows-PC braucht dafuer lokal entweder:

- eine heruntergeladene `pr.exe`, oder
- eine lokale Kopie des Projektordners mit Python.

Einfachster EXE-Test auf Windows:

1. `pr.exe` einmal auf den Windows-PC laden.
2. Ordner anlegen, z.B. `C:\Projektmanager\`.
3. `pr.exe` dort ablegen.
4. Daneben `start-projektmanager.bat` anlegen mit:

```bat
@echo off
set "PM_BASE_URL=http://100.80.250.84:8765"
cd /d "%~dp0"

if not exist "pr.exe" (
  echo pr.exe wurde in diesem Ordner nicht gefunden.
  echo Lege pr.exe in denselben Ordner wie diese start-projektmanager.bat.
  pause
  exit /b 1
)

".\pr.exe"
pause
```

Damit muss keine Serveradresse eingetippt werden. Die Umgebungsvariable setzt den Server fuer diesen Start.

Wenn der Benutzer lokal eine Projektkopie mit Python hat, kann stattdessen verwendet werden:

```bat
@echo off
set "PM_BASE_URL=http://100.80.250.84:8765"
cd /d "%~dp0"
py -3 pr.py
if errorlevel 1 python pr.py
pause
```

Diese Datei existiert aktuell im Repo als:

- `start-windows-test.bat`

Sie hilft aber nur, wenn der Projektordner lokal auf dem Windows-PC vorhanden ist.

## Woher kommt die EXE?

Primaerer Weg:

- Server-Weboberflaeche oeffnen: `http://100.80.250.84:8765`
- Einloggen
- Downloadbereich verwenden

Falls dort noch keine EXE angeboten wird:

- GitHub Actions muss auf `main` laufen.
- Danach `pr.exe` aus dem Actions-Artefakt oder aus dem Release `rolling-latest` laden.

## Wichtige offene Aufgaben fuer echten Betrieb

- Produktiven privaten Schluessel rotieren.
- Sensible Daten bei Bedarf aus der Git-Historie entfernen; das ist ein separater koordinierter Schritt.
- `.venv`, `__pycache__` und andere generierte Dateien aus Git entfernen, falls sie noch getrackt sind:

```bash
git rm -r --cached --ignore-unmatch .venv __pycache__ Project/.venv Project/**/__pycache__
```

- Serverdaten vor Deployment sichern:
  - `app.db`
  - `collab_accounts.json`
- Systemd/Caddy produktiv passend konfigurieren.
- GitHub Actions einmal auf `main` ausfuehren und Release/Artefakte pruefen.
- Windows-EXE auf sauberem Windows-PC gegen `http://100.80.250.84:8765` testen.
- Die grosse Modularisierung von Server und GUI ist nur teilweise begonnen; nicht behaupten, dass der monolithische Server vollstaendig aufgeteilt ist.

## Nuetzliche Befehle

Tests:

```bash
cd /home/florian/Projektmanager/Project
python3 -m unittest discover -s tests -v
```

Server lokal starten:

```bash
cd /home/florian/Projektmanager/Project
PMTOOL_PUBLIC_BASE_URL=http://100.80.250.84:8765 python3 -m pmtool.collab_server
```

Client gegen Server starten:

```bash
cd /home/florian/Projektmanager/Project
PM_BASE_URL=http://100.80.250.84:8765 python3 pr.py
```

## Bekannte Hinweise

- `PM_BASE_URL` hat Vorrang vor gespeicherter Client-Konfiguration.
- Falsch gespeicherte Client-URL kann auf Windows in `C:\Users\<NAME>\.pmtool\client.json` geaendert oder geloescht werden.
- `http://100.80.250.84:8765` ist aktuell die wichtige Adresse fuer Tests.
- Fuer produktiven Betrieb waere HTTPS ueber Caddy besser.
- Ein `git diff --check` war frueher noch nicht als sauber bestaetigt; vor Commit erneut pruefen.
