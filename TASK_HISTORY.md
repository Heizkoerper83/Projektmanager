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