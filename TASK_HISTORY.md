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

## 2026-06-02: Fix PyInstaller-Crash – missing imports in remote_core.py

**Status:** Abgeschlossen

**Betroffene Dateien:**
- `Project/pmtool/remote_core.py`

**Was wurde gemacht:**
Der Fehler trat auf, wenn die mit GitHub Actions gebaute `.exe` gestartet wurde:

```
ImportError: cannot import name 'export_csv' from 'pmtool.remote_core'
[PYI-27264: ERROR] Failed to execute script 'pr' due to unhandled exception!
```

**Ursache:**
- `pmtool/ui/dialogs.py` importiert `export_csv`, `export_json`, `import_csv`, `import_json` aus `pmtool.remote_core`
- `pmtool/remote_core.py` hat diese vier Funktionen nie selbst importiert – sie liegen in `pmtool.core.legacy`
- In normalem Python funktioniert das trotzdem, weil `pmtool/core/__init__.py` einen `sys.modules`-Swap-Trick macht (`sys.modules[__name__] = _legacy`)
- **PyInstaller** kann diesen Modul-Swap-Trick nicht korrekt auflösen → ImportError

**Fix:**
- `export_csv`, `export_json`, `import_csv`, `import_json` in den Import-Statement und die `__all__`-Liste von `remote_core.py` aufgenommen

**Entscheidungen / Begründungen:**
- Die Funktionen sind bereits in `pmtool.core.legacy` definiert – es reicht, sie in `remote_core.py` zu importieren und re-exportieren
- Die `__all__`-Liste wurde ebenfalls aktualisiert, damit der Export konsistent ist
- Kein Ändern des Modul-Swap-Mechanismus nötig, da dieser für normalen Python-Betrieb weiterhin funktioniert

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