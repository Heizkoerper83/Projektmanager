"""Simple collaboration server with browser login and web UI."""

from __future__ import annotations

import html
import hashlib
import io
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from pmtool.collab_accounts import (
    DEFAULT_ACCOUNTS_PATH,
    authenticate,
    authorize_account_creation_api_key,
    create_account,
    ensure_api_keys,
    list_accounts,
    set_account_enabled,
)
from pmtool.core import (
    add_milestone,
    add_project,
    add_task,
    add_task_note,
    add_template,
    clear_current_principal,
    create_task_from_template,
    delete_milestone,
    delete_project,
    delete_task,
    delete_template,
    get_connection,
    init_db,
    list_milestones,
    list_project_shares,
    list_projects,
    list_task_history,
    list_task_notes,
    list_tasks,
    list_templates,
    now_text,
    project_dashboard_counts,
    risk_rows_from_json,
    set_current_principal,
    share_project,
    table_columns,
    task_dashboard_counts,
    unshare_project,
    update_milestone,
    update_project,
    update_task,
    update_template,
)

# Security configuration
SESSION_TIMEOUT_SECONDS = 3600  # 1 hour
RATE_LIMIT_REQUESTS_PER_MINUTE = 60
MAX_REQUEST_BODY_BYTES = 1_000_000

GITHUB_REPO = "Heizkoerper83/Projektmanager"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
GITHUB_RELEASES_CACHE_SECONDS = 300
_RELEASE_CACHE: dict[str, object] = {"timestamp": 0.0, "downloads": []}


def _filter_row_columns(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        columns = table_columns(conn, table_name)
    return {key: value for key, value in row.items() if key in columns}


def _upsert_row(table_name: str, row: dict[str, Any]) -> None:
    filtered = _filter_row_columns(table_name, row)
    if not filtered:
        raise ValueError(f"Keine gueltigen Spalten fuer {table_name}")
    columns = list(filtered.keys())
    placeholders = ", ".join(["?"] * len(columns))
    column_sql = ", ".join(columns)
    values = [filtered[column] for column in columns]
    with get_connection() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO {table_name} ({column_sql}) VALUES ({placeholders})",
            values,
        )
        conn.commit()


def _app_html(principal: dict[str, Any]) -> str:
    role = principal.get("role", "reader")
    name = principal.get("name", "")
    write_enabled = "true" if role == "editor" else "false"
    return f"""<!doctype html>
<html lang="de">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Projektmanager Web</title>
    <style>
        :root {{ --bg:#f6f8fb; --panel:#ffffff; --line:#d8deea; --text:#1b2636; --muted:#5f6f84; --accent:#0069d9; --danger:#c62828; --ok:#1d7a42; }}
        * {{ box-sizing:border-box; }}
        body {{ margin:0; font-family:Segoe UI, Arial, sans-serif; background:linear-gradient(180deg, #edf2fb 0%, #f8fbff 40%, #f6f8fb 100%); color:var(--text); }}
        header {{ padding:14px 18px; background:#102038; color:#fff; display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }}
        .header-meta {{ font-size:13px; opacity:0.9; }}
        .header-actions {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
        .header-btn {{ display:inline-block; padding:8px 12px; border-radius:8px; background:#2f6fdb; color:#fff; text-decoration:none; font-size:13px; font-weight:600; }}
        .header-btn:hover {{ background:#3d7def; }}
        main {{ max-width:1400px; margin:16px auto; padding:0 14px 30px; }}
        .dashboard {{ display:grid; grid-template-columns:repeat(4, minmax(120px, 1fr)); gap:10px; margin-bottom:12px; }}
        .kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:10px; }}
        .kpi .k {{ color:var(--muted); font-size:12px; }}
        .kpi .v {{ font-size:20px; font-weight:700; margin-top:4px; }}
        .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
        .card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; }}
        h2 {{ margin:0 0 10px; font-size:18px; }}
        h3 {{ margin:0 0 8px; font-size:15px; }}
        table {{ width:100%; border-collapse:collapse; font-size:13px; }}
        th, td {{ border-bottom:1px solid var(--line); text-align:left; padding:6px; vertical-align:top; }}
        th {{ color:var(--muted); font-weight:600; }}
        tr.selected {{ background:#ecf4ff; }}
        input, select, textarea, button {{ font:inherit; padding:8px; border-radius:8px; border:1px solid var(--line); }}
        input, select, textarea {{ width:100%; }}
        textarea {{ min-height:72px; resize:vertical; }}
        button {{ width:auto; cursor:pointer; background:var(--accent); color:#fff; border:none; }}
        button.secondary {{ background:#4f5f76; }}
        button.danger {{ background:var(--danger); }}
        .row {{ display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap; }}
        .row > * {{ flex:1 1 180px; }}
        .muted {{ color:var(--muted); font-size:13px; }}
        .ok {{ color:var(--ok); }}
        .hidden {{ display:none; }}
        .split {{ display:grid; grid-template-columns:1.1fr 1fr; gap:10px; }}
        .list-box {{ border:1px solid var(--line); border-radius:8px; padding:8px; max-height:180px; overflow:auto; background:#fbfdff; }}
        .compact-item {{ border-bottom:1px solid #e9eef7; padding:6px 0; font-size:12px; }}
        .compact-item:last-child {{ border-bottom:none; }}
        @media (max-width: 1100px) {{ .grid, .split {{ grid-template-columns:1fr; }} .dashboard {{ grid-template-columns:repeat(2, minmax(120px, 1fr)); }} }}
    </style>
</head>
<body>
<header>
    <div>
        <strong>Projektmanager Web</strong>
        <div class="header-meta">Account: {name} ({role})</div>
    </div>
    <div class="header-actions">
        <a href="#download" class="header-btn">Download</a>
        <a href="/logout" style="color:#fff">Logout</a>
    </div>
</header>
<main>
    <div class="dashboard" id="dashboard"></div>
    <div class="grid">
        <section class="card">
            <h2>Projekte</h2>
            <div class="split">
                <div>
                    <table>
                        <thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Offen</th></tr></thead>
                        <tbody id="projectsBody"></tbody>
                    </table>
                </div>
                <div>
                    <h3>Projekt bearbeiten</h3>
                    <input id="projectId" type="hidden" />
                    <div class="row"><input id="projectName" placeholder="Name" /></div>
                    <div class="row"><select id="projectStatus"><option value="active">active</option><option value="paused">paused</option><option value="done">done</option></select></div>
                    <div class="row"><input id="projectGoal" placeholder="Ziel" /></div>
                    <div class="row"><input id="projectMilestone" placeholder="Milestone" /></div>
                    <div class="row"><input id="projectNextReview" type="text" placeholder="YYYY-MM-DD" inputmode="numeric" /></div>
                    <div class="row"><textarea id="projectDescription" placeholder="Beschreibung"></textarea></div>
                    <div class="row">
                        <button id="projectCreateBtn" class="hidden">Neues Projekt</button>
                        <button id="projectSaveBtn" class="hidden">Speichern</button>
                        <button id="projectDeleteBtn" class="danger hidden">Löschen</button>
                        <button id="projectClearBtn" class="secondary">Auswahl aufheben</button>
                    </div>
                </div>
            </div>
        </section>

        <section class="card">
            <h2>Aufgaben</h2>
            <div class="row">
                <select id="taskProjectFilter"><option value="">Alle Projekte</option></select>
                <select id="taskStatusFilter"><option value="">Alle Status</option><option value="open">open</option><option value="in_progress">in_progress</option><option value="blocked">blocked</option><option value="done">done</option></select>
                <input id="taskSearch" placeholder="Suche Titel, Details, Tags ..." />
                <button id="reloadTasksBtn" class="secondary">Aktualisieren</button>
            </div>
            <div class="split">
                <div>
                    <table>
                        <thead><tr><th>ID</th><th>Projekt</th><th>Titel</th><th>Status</th><th>Prio</th></tr></thead>
                        <tbody id="tasksBody"></tbody>
                    </table>
                </div>
                <div>
                    <h3>Aufgabe bearbeiten</h3>
                    <input id="taskId" type="hidden" />
                    <div class="row"><input id="taskTitle" placeholder="Titel" /></div>
                    <div class="row"><select id="taskProject"></select></div>
                    <div class="row"><select id="taskStatus"><option value="open">open</option><option value="in_progress">in_progress</option><option value="blocked">blocked</option><option value="done">done</option></select></div>
                    <div class="row"><input id="taskPriority" type="number" min="1" max="5" placeholder="Priorität" /></div>
                    <div class="row"><input id="taskDue" type="text" placeholder="YYYY-MM-DD" inputmode="numeric" /><input id="taskEstimate" type="number" min="0" placeholder="Schätzung (min)" /></div>
                    <div class="row"><input id="taskContext" placeholder="Kontext" /><select id="taskEnergy"><option value="low">low</option><option value="medium">medium</option><option value="high">high</option></select></div>
                    <div class="row"><input id="taskTags" placeholder="Tags (a,b,c)" /><input id="taskRecurrence" type="number" min="1" placeholder="Wiederholung Tage" /></div>
                    <div class="row"><input id="taskBlockedReason" placeholder="Blocker" /></div>
                    <div class="row"><textarea id="taskDetails" placeholder="Details"></textarea></div>
                    <div class="row">
                        <button id="taskCreateBtn" class="hidden">Neue Aufgabe</button>
                        <button id="taskSaveBtn" class="hidden">Speichern</button>
                        <button id="taskDeleteBtn" class="danger hidden">Löschen</button>
                        <button id="taskFromTemplateBtn" class="secondary hidden">Aus Vorlage erstellen</button>
                        <button id="taskClearBtn" class="secondary">Auswahl aufheben</button>
                    </div>
                    <div class="row">
                        <select id="taskTemplateSelect"><option value="">Vorlage wählen</option></select>
                    </div>
                    <div class="split">
                        <div>
                            <h3>Notizen</h3>
                            <div class="row"><textarea id="taskNoteInput" placeholder="Neue Notiz"></textarea></div>
                            <div class="row"><button id="taskNoteAddBtn" class="hidden">Notiz speichern</button></div>
                            <div class="list-box" id="taskNotesBox"></div>
                        </div>
                        <div>
                            <h3>Historie</h3>
                            <div class="list-box" id="taskHistoryBox"></div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    </div>

    <div class="grid" style="margin-top:12px;">
        <section class="card">
            <h2>Meilensteine</h2>
            <div class="row"><select id="milestoneProject"></select><input id="milestoneTitle" placeholder="Titel" /><input id="milestoneDue" type="text" placeholder="YYYY-MM-DD" inputmode="numeric" /><select id="milestoneStatus"><option value="open">open</option><option value="in_progress">in_progress</option><option value="blocked">blocked</option><option value="done">done</option></select></div>
            <div class="row"><input id="milestoneId" type="hidden" /><button id="milestoneCreateBtn" class="hidden">Neu</button><button id="milestoneSaveBtn" class="hidden">Speichern</button><button id="milestoneDeleteBtn" class="danger hidden">Löschen</button><button id="milestoneClearBtn" class="secondary">Auswahl aufheben</button></div>
            <table><thead><tr><th>ID</th><th>Projekt</th><th>Titel</th><th>Due</th><th>Status</th></tr></thead><tbody id="milestonesBody"></tbody></table>
        </section>

        <section class="card">
            <h2>Vorlagen</h2>
            <div class="row"><input id="templateName" placeholder="Name" /><input id="templateTitle" placeholder="Titel" /><select id="templateProject"></select></div>
            <div class="row"><select id="templateStatus"><option value="open">open</option><option value="in_progress">in_progress</option><option value="blocked">blocked</option><option value="done">done</option></select><input id="templatePriority" type="number" min="1" max="5" placeholder="Prio" /><input id="templateDueOffset" type="number" placeholder="Due Offset Tage" /></div>
            <div class="row"><input id="templateContext" placeholder="Kontext" /><select id="templateEnergy"><option value="low">low</option><option value="medium">medium</option><option value="high">high</option></select><input id="templateRecurrence" type="number" min="1" placeholder="Wiederholung Tage" /></div>
            <div class="row"><input id="templateTags" placeholder="Tags" /></div>
            <div class="row"><textarea id="templateDetails" placeholder="Details"></textarea></div>
            <div class="row"><input id="templateId" type="hidden" /><button id="templateCreateBtn" class="hidden">Neu</button><button id="templateSaveBtn" class="hidden">Speichern</button><button id="templateDeleteBtn" class="danger hidden">Löschen</button><button id="templateClearBtn" class="secondary">Auswahl aufheben</button></div>
            <table><thead><tr><th>ID</th><th>Name</th><th>Titel</th><th>Status</th><th>Prio</th></tr></thead><tbody id="templatesBody"></tbody></table>
        </section>
    </div>

    <p id="status" class="muted"></p>

    <section class="card" style="margin-top:12px;" id="download">
    <h2>Download</h2>
        <p>Waehle das passende Paket fuer dein System:</p>
    <div class="row">
            <select id="packageSelect"></select>
            <button id="packageDownloadBtn" class="secondary">Download</button>
    </div>
        <p class="muted" id="packageHint"></p>
  </section>

  <section class="card" style="margin-top:12px;">
    <h2>Projektbericht</h2>
    <div class="row">
      <select id="reportProject"><option value="">Projekt wählen</option></select>
      <button id="reportLoadBtn" class="secondary">Bericht vorladen</button>
    </div>
    <div class="split" style="margin-top:12px;">
      <div>
        <h3>Berichtsformular</h3>
        <div class="row"><strong>Projekttitel:</strong> <span id="reportTitle"></span></div>
        <div class="row"><input id="reportTeam" placeholder="Projektteam" /></div>
        <div class="row"><input id="reportDateField" type="text" placeholder="YYYY-MM-DD" inputmode="numeric" /></div>
        <h3>Was haben wir diese Woche geplant?</h3>
        <div class="row"><textarea id="reportPlanned" placeholder="Punkt 1&#10;Punkt 2&#10;Punkt 3" rows="4"></textarea></div>
        <h3>Was haben wir tatsächlich erreicht?</h3>
        <div class="row"><textarea id="reportAchieved" placeholder="Punkt 1&#10;Punkt 2&#10;Punkt 3" rows="4"></textarea></div>
        <h3>Projektstatus</h3>
        <div class="row">
          <label><input type="checkbox" id="reportStatusOnTrack" /> Im Plan</label>
          <label><input type="checkbox" id="reportStatusAtRisk" /> Im Verzug</label>
          <label><input type="checkbox" id="reportStatusFaster" /> Schneller als geplant</label>
        </div>
        <h3>Bei Verzug: Gegenmaßnahmen</h3>
        <div class="row"><textarea id="reportMeasures" placeholder="Gegenmaßnahme 1&#10;Gegenmaßnahme 2" rows="3"></textarea></div>
        <h3>Top 3 Projektrisiken und Gegenmaßnahmen</h3>
        <div style="margin-bottom:8px;">
          <strong>Risiko 1:</strong>
          <div class="row"><input id="reportRisk1" placeholder="Risikobeschreibung" /></div>
          <div class="row"><input id="reportMeasure1" placeholder="Gegenmaßnahme" /></div>
        </div>
        <div style="margin-bottom:8px;">
          <strong>Risiko 2:</strong>
          <div class="row"><input id="reportRisk2" placeholder="Risikobeschreibung" /></div>
          <div class="row"><input id="reportMeasure2" placeholder="Gegenmaßnahme" /></div>
        </div>
        <div style="margin-bottom:8px;">
          <strong>Risiko 3:</strong>
          <div class="row"><input id="reportRisk3" placeholder="Risikobeschreibung" /></div>
          <div class="row"><input id="reportMeasure3" placeholder="Gegenmaßnahme" /></div>
        </div>
        <h3>Nächster Meilenstein</h3>
        <div class="row"><input id="reportMilestoneTitle" placeholder="Bezeichnung" /></div>
        <div class="row"><input id="reportMilestoneDate" type="text" placeholder="YYYY-MM-DD" inputmode="numeric" /></div>
        <div class="row">
          <button id="reportGenerateBtn">Bericht generieren</button>
          <button id="reportDownloadBtn" class="secondary hidden">Download .md</button>
          <button id="reportClearReportBtn" class="secondary">Formular zurücksetzen</button>
        </div>
      </div>
      <div>
        <h3>Vorschau</h3>
        <pre id="reportPreview" style="background:#f5f5f5; padding:10px; border-radius:8px; font-size:12px; max-height:600px; overflow:auto; white-space:pre-wrap; word-wrap:break-word;"></pre>
      </div>
    </div>
  </section>
</main>

<script>
const canWrite = {write_enabled};
const state = {{ projects: [], tasks: [], milestones: [], templates: [], downloads: [], selectedProjectId: null, selectedTaskId: null, selectedMilestoneId: null, selectedTemplateId: null, currentReport: null }};

function byId(id) {{ return document.getElementById(id); }}
function toIntOrNull(v) {{ if (v === '' || v === null || typeof v === 'undefined') return null; const n = Number(v); return Number.isFinite(n) ? n : null; }}
function toDateOrNull(v) {{ return (v || '').trim() || null; }}
function esc(v) {{ return String(v ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'); }}

function setStatus(text, ok = true) {{
    const el = byId('status');
    el.textContent = text;
    el.className = ok ? 'muted ok' : 'muted';
}}

async function api(path, options = {{}}) {{
    const res = await fetch(path, Object.assign({{ credentials: 'include' }}, options));
    if (!res.ok) {{
        let msg = 'Fehler';
        try {{ const payload = await res.json(); msg = payload.error || JSON.stringify(payload); }} catch {{}}
        throw new Error(msg);
    }}
    return await res.json();
}}

function showWriteControls() {{
    if (!canWrite) return;
    for (const id of ['projectCreateBtn','projectSaveBtn','projectDeleteBtn','taskCreateBtn','taskSaveBtn','taskDeleteBtn','taskFromTemplateBtn','taskNoteAddBtn','milestoneCreateBtn','milestoneSaveBtn','milestoneDeleteBtn','templateCreateBtn','templateSaveBtn','templateDeleteBtn']) {{
        byId(id).classList.remove('hidden');
    }}
}}

function renderDashboard(data) {{
    const host = byId('dashboard');
    const pairs = [
        ['Open Tasks', data.tasks.open],
        ['In Progress', data.tasks.in_progress],
        ['Blocked', data.tasks.blocked],
        ['Due Today', data.tasks.today],
        ['Overdue', data.tasks.overdue],
        ['Aktive Projekte', data.projects.active],
        ['Pausiert', data.projects.paused],
        ['Abgeschlossen', data.projects.done],
    ];
    host.innerHTML = pairs.map(([k, v]) => `<div class="kpi"><div class="k">${{k}}</div><div class="v">${{v ?? 0}}</div></div>`).join('');
}}

function refreshProjectSelects() {{
    const items = [['taskProject', true], ['milestoneProject', false], ['templateProject', true], ['taskProjectFilter', true], ['reportProject', true]];
    for (const [id, withEmpty] of items) {{
        const el = byId(id);
        const current = el.value;
        el.innerHTML = withEmpty ? '<option value="">-</option>' : '';
        for (const p of state.projects) {{
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = `${{p.id}}: ${{p.name}}`;
            el.appendChild(opt);
        }}
        if ([...el.options].some((o) => o.value === current)) el.value = current;
    }}
}}

function renderProjects() {{
    const body = byId('projectsBody');
    body.innerHTML = '';
    for (const p of state.projects) {{
        const tr = document.createElement('tr');
        if (state.selectedProjectId === p.id) tr.classList.add('selected');
        tr.innerHTML = `<td>${{p.id}}</td><td>${{esc(p.name)}}</td><td>${{esc(p.status)}}</td><td>${{p.open_tasks ?? 0}}</td>`;
        tr.onclick = () => selectProject(p.id);
        body.appendChild(tr);
    }}
    refreshProjectSelects();
}}

function selectProject(projectId) {{
    state.selectedProjectId = projectId;
    renderProjects();
    const p = state.projects.find((x) => x.id === projectId);
    if (!p) return;
    byId('projectId').value = p.id;
    byId('projectName').value = p.name || '';
    byId('projectStatus').value = p.status || 'active';
    byId('projectGoal').value = p.goal || '';
    byId('projectMilestone').value = p.milestone || '';
    byId('projectNextReview').value = p.next_review_date || '';
    byId('projectDescription').value = p.description || '';
}}

function clearProjectForm() {{
    state.selectedProjectId = null;
    renderProjects();
    for (const id of ['projectId','projectName','projectGoal','projectMilestone','projectNextReview','projectDescription']) byId(id).value = '';
    byId('projectStatus').value = 'active';
}}

function renderTasks() {{
    const body = byId('tasksBody');
    const statusFilter = byId('taskStatusFilter').value;
    const searchFilter = byId('taskSearch').value.trim().toLowerCase();
    const filtered = state.tasks.filter((t) => {{
        if (statusFilter && t.status !== statusFilter) return false;
        if (!searchFilter) return true;
        return [t.title, t.details, t.tags, t.context, t.blocked_reason, t.project_name].join(' ').toLowerCase().includes(searchFilter);
    }});
    body.innerHTML = '';
    for (const t of filtered) {{
        const tr = document.createElement('tr');
        if (state.selectedTaskId === t.id) tr.classList.add('selected');
        tr.innerHTML = `<td>${{t.id}}</td><td>${{esc(t.project_name || '-')}}</td><td>${{esc(t.title)}}</td><td>${{esc(t.status)}}</td><td>${{t.priority}}</td>`;
        tr.onclick = () => selectTask(t.id);
        body.appendChild(tr);
    }}
}}

async function selectTask(taskId) {{
    state.selectedTaskId = taskId;
    renderTasks();
    const t = state.tasks.find((x) => x.id === taskId);
    if (!t) return;
    byId('taskId').value = t.id;
    byId('taskTitle').value = t.title || '';
    byId('taskProject').value = t.project_id || '';
    byId('taskStatus').value = t.status || 'open';
    byId('taskPriority').value = t.priority ?? 3;
    byId('taskDue').value = t.due_date || '';
    byId('taskEstimate').value = t.estimate_minutes ?? 0;
    byId('taskContext').value = t.context || '';
    byId('taskEnergy').value = t.energy_level || 'medium';
    byId('taskTags').value = t.tags || '';
    byId('taskRecurrence').value = t.recurrence_days ?? '';
    byId('taskBlockedReason').value = t.blocked_reason || '';
    byId('taskDetails').value = t.details || '';
    await loadTaskNotesHistory(taskId);
}}

function clearTaskForm() {{
    state.selectedTaskId = null;
    renderTasks();
    for (const id of ['taskId','taskTitle','taskDue','taskEstimate','taskContext','taskTags','taskRecurrence','taskBlockedReason','taskDetails','taskNoteInput']) byId(id).value = '';
    byId('taskProject').value = '';
    byId('taskStatus').value = 'open';
    byId('taskPriority').value = 3;
    byId('taskEnergy').value = 'medium';
    byId('taskNotesBox').innerHTML = '';
    byId('taskHistoryBox').innerHTML = '';
}}

function renderMilestones() {{
    const body = byId('milestonesBody');
    body.innerHTML = '';
    for (const m of state.milestones) {{
        const tr = document.createElement('tr');
        if (state.selectedMilestoneId === m.id) tr.classList.add('selected');
        tr.innerHTML = `<td>${{m.id}}</td><td>${{esc(m.project_name || '-')}}</td><td>${{esc(m.title)}}</td><td>${{esc(m.due_date || '-')}}</td><td>${{esc(m.status)}}</td>`;
        tr.onclick = () => selectMilestone(m.id);
        body.appendChild(tr);
    }}
}}

function selectMilestone(id) {{
    state.selectedMilestoneId = id;
    renderMilestones();
    const m = state.milestones.find((x) => x.id === id);
    if (!m) return;
    byId('milestoneId').value = m.id;
    byId('milestoneProject').value = m.project_id || '';
    byId('milestoneTitle').value = m.title || '';
    byId('milestoneDue').value = m.due_date || '';
    byId('milestoneStatus').value = m.status || 'open';
}}

function clearMilestoneForm() {{
    state.selectedMilestoneId = null;
    renderMilestones();
    for (const id of ['milestoneId','milestoneTitle','milestoneDue']) byId(id).value = '';
    byId('milestoneStatus').value = 'open';
    if (byId('milestoneProject').options.length > 0) byId('milestoneProject').selectedIndex = 0;
}}

function renderTemplates() {{
    const body = byId('templatesBody');
    const select = byId('taskTemplateSelect');
    body.innerHTML = '';
    select.innerHTML = '<option value="">Vorlage wählen</option>';
    for (const t of state.templates) {{
        const tr = document.createElement('tr');
        if (state.selectedTemplateId === t.id) tr.classList.add('selected');
        tr.innerHTML = `<td>${{t.id}}</td><td>${{esc(t.name)}}</td><td>${{esc(t.title)}}</td><td>${{esc(t.status)}}</td><td>${{t.priority}}</td>`;
        tr.onclick = () => selectTemplate(t.id);
        body.appendChild(tr);
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = `${{t.name}} (#${{t.id}})`;
        select.appendChild(opt);
    }}
}}

function selectTemplate(id) {{
    state.selectedTemplateId = id;
    renderTemplates();
    const t = state.templates.find((x) => x.id === id);
    if (!t) return;
    byId('templateId').value = t.id;
    byId('templateName').value = t.name || '';
    byId('templateTitle').value = t.title || '';
    byId('templateProject').value = t.project_id || '';
    byId('templateStatus').value = t.status || 'open';
    byId('templatePriority').value = t.priority ?? 3;
    byId('templateDueOffset').value = t.due_offset_days ?? '';
    byId('templateContext').value = t.context || '';
    byId('templateEnergy').value = t.energy_level || 'medium';
    byId('templateRecurrence').value = t.recurrence_days ?? '';
    byId('templateTags').value = t.tags || '';
    byId('templateDetails').value = t.details || '';
}}

function clearTemplateForm() {{
    state.selectedTemplateId = null;
    renderTemplates();
    for (const id of ['templateId','templateName','templateTitle','templateDueOffset','templateContext','templateRecurrence','templateTags','templateDetails']) byId(id).value = '';
    byId('templateStatus').value = 'open';
    byId('templatePriority').value = 3;
    byId('templateEnergy').value = 'medium';
    byId('templateProject').value = '';
}}

function clearReportForm() {{
    for (const id of ['reportTeam','reportDateField','reportPlanned','reportAchieved','reportMeasures','reportRisk1','reportMeasure1','reportRisk2','reportMeasure2','reportRisk3','reportMeasure3','reportMilestoneTitle','reportMilestoneDate']) byId(id).value = '';
    for (const id of ['reportStatusOnTrack','reportStatusAtRisk','reportStatusFaster']) byId(id).checked = false;
    byId('reportTitle').textContent = '';
    byId('reportPreview').textContent = '';
    byId('reportDownloadBtn').classList.add('hidden');
    state.currentReport = null;
}}

function generateReport() {{
    const projectId = byId('reportProject').value;
    if (!projectId) return setStatus('Bitte Projekt auswählen.', false);
    
    const projectName = state.projects.find((p) => p.id === Number(projectId))?.name || '';
    byId('reportTitle').textContent = projectName;
    
    const plannedList = byId('reportPlanned').value.split('\\n').filter((l) => l.trim()).map((l) => '• ' + l.trim());
    const achievedList = byId('reportAchieved').value.split('\\n').filter((l) => l.trim()).map((l) => '• ' + l.trim());
    const measuresList = byId('reportMeasures').value.split('\\n').filter((l) => l.trim()).map((l) => '• ' + l.trim());
    
    const statusParts = [];
    if (byId('reportStatusOnTrack').checked) statusParts.push('x\\tIm Plan');
    if (byId('reportStatusAtRisk').checked) statusParts.push('x\\tIm Verzug');
    if (byId('reportStatusFaster').checked) statusParts.push('x\\tSchneller als geplant');
    const statusSection = statusParts.length ? statusParts.join('\\n') : 'x\\tIm Plan';
    
    let report = `# Projektbericht

## Allgemeine Angaben
Projekttitel: ${{projectName}}
Projektteam: ${{byId('reportTeam').value || '_____________'}}
Datum: ${{byId('reportDateField').value || '_____________'}}


## Was haben wir in dieser Woche geplant?
${{plannedList.length ? plannedList.join('\\n') : '• _____________'}}


## Was haben wir tatsächlich erreicht?
${{achievedList.length ? achievedList.join('\\n') : '• _____________'}}


## Projektstatus
Wir sind:
${{statusSection}}


## Bei Verzug: Gegenmaßnahmen
${{measuresList.length ? measuresList.join('\\n') : '• _____________'}}


## Top 3 Projektrisiken und Gegenmaßnahmen
1. Risiko: ${{byId('reportRisk1').value || '_____________'}}
   Gegenmaßnahme: ${{byId('reportMeasure1').value || '_____________'}}

2. Risiko: ${{byId('reportRisk2').value || '_____________'}}
   Gegenmaßnahme: ${{byId('reportMeasure2').value || '_____________'}}

3. Risiko: ${{byId('reportRisk3').value || '_____________'}}
   Gegenmaßnahme: ${{byId('reportMeasure3').value || '_____________'}}


## Nächster Meilenstein
Bezeichnung: ${{byId('reportMilestoneTitle').value || '_____________'}}
Geplantes Datum: ${{byId('reportMilestoneDate').value || '_____________'}}
`;
    
    byId('reportPreview').textContent = report;
    byId('reportDownloadBtn').classList.remove('hidden');
    state.currentReport = report;
    setStatus('Bericht generiert.');
}}

function downloadReport() {{
    if (!state.currentReport) return setStatus('Bitte erst Bericht generieren.', false);
    const projectName = byId('reportProject').options[byId('reportProject').selectedIndex]?.text || 'bericht';
    const date = byId('reportDateField').value || 'undatiert';
    const filename = `bericht_${{projectName.replace(/[^a-z0-9]/gi, '_')}}_${{date}}.md`;
    const blob = new Blob([state.currentReport], {{ type: 'text/markdown' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setStatus('Bericht heruntergeladen: ' + filename);
}}

async function loadDashboard() {{
    renderDashboard(await api('/api/dashboard'));
}}

async function loadProjects() {{
    state.projects = await api('/api/projects');
    renderProjects();
}}

async function loadTasks() {{
    const pid = byId('taskProjectFilter').value;
    const query = pid ? `?project_id=${{encodeURIComponent(pid)}}&include_done=true` : '?include_done=true';
    state.tasks = await api('/api/tasks' + query);
    renderTasks();
}}

async function loadMilestones() {{
    state.milestones = await api('/api/milestones');
    renderMilestones();
}}

async function loadTemplates() {{
    state.templates = await api('/api/templates');
    renderTemplates();
}}

async function loadDownloads() {{
    const payload = await api('/api/downloads');
    state.downloads = payload.downloads || [];
    renderDownloads();
}}

async function loadTaskNotesHistory(taskId) {{
    const notes = await api('/api/tasks/' + taskId + '/notes');
    const history = await api('/api/tasks/' + taskId + '/history');
    byId('taskNotesBox').innerHTML = notes.length ? notes.map((n) => `<div class="compact-item"><strong>${{n.created_at}}</strong><br/>${{esc(n.note)}}</div>`).join('') : '<div class="muted">Keine Notizen</div>';
    byId('taskHistoryBox').innerHTML = history.length ? history.map((h) => `<div class="compact-item"><strong>${{h.created_at}}</strong> • ${{esc(h.action)}}<br/>${{esc(h.details || '')}}</div>`).join('') : '<div class="muted">Keine Historie</div>';
}}

async function reloadAll() {{
    await Promise.all([loadDashboard(), loadProjects(), loadTasks(), loadMilestones(), loadTemplates(), loadDownloads()]);
}}

function renderDownloads() {{
    const select = byId('packageSelect');
    const button = byId('packageDownloadBtn');
    const hint = byId('packageHint');
    select.innerHTML = '';
    if (!state.downloads.length) {{
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'Keine Pakete verfuegbar';
        select.appendChild(opt);
        select.disabled = true;
        button.disabled = true;
        hint.textContent = 'Der Server hat derzeit keine Pakete bereit.';
        return;
    }}
    select.disabled = false;
    button.disabled = false;
    hint.textContent = '';
    for (const item of state.downloads) {{
        const opt = document.createElement('option');
        opt.value = item.id;
        opt.textContent = `${{item.label}} (${{item.filename}})`;
        select.appendChild(opt);
    }}
}}

function bindEvents() {{
    byId('reloadTasksBtn').onclick = () => loadTasks().then(() => setStatus('Aufgaben aktualisiert.')).catch((e) => setStatus(e.message, false));
    byId('taskProjectFilter').onchange = () => loadTasks().catch((e) => setStatus(e.message, false));
    byId('taskStatusFilter').onchange = renderTasks;
    byId('taskSearch').oninput = renderTasks;
    byId('projectClearBtn').onclick = clearProjectForm;
    byId('taskClearBtn').onclick = clearTaskForm;
    byId('milestoneClearBtn').onclick = clearMilestoneForm;
    byId('templateClearBtn').onclick = clearTemplateForm;
    byId('reportLoadBtn').onclick = () => byId('reportDateField').valueAsDate = new Date();
    byId('reportGenerateBtn').onclick = generateReport;
    byId('reportDownloadBtn').onclick = downloadReport;
    byId('reportClearReportBtn').onclick = clearReportForm;
    byId('packageDownloadBtn').onclick = () => {{
        const id = byId('packageSelect').value;
        if (!id) return setStatus('Bitte Paket waehlen.', false);
        const item = state.downloads.find((entry) => entry.id === id);
        const url = item && item.url ? item.url : '/download/package/' + encodeURIComponent(id);
        const a = document.createElement('a');
        a.href = url;
        if (item && item.filename) {{
            a.download = item.filename;
        }}
        a.rel = 'noopener';
        a.target = '_blank';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setStatus('Download gestartet.');
    }};

    if (!canWrite) return;

    byId('projectCreateBtn').onclick = async () => {{
        try {{
            await api('/api/projects', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{
                name: byId('projectName').value.trim(),
                description: byId('projectDescription').value,
                status: byId('projectStatus').value,
                goal: byId('projectGoal').value,
                milestone: byId('projectMilestone').value,
                next_review_date: toDateOrNull(byId('projectNextReview').value),
            }}) }});
            clearProjectForm();
            await reloadAll();
            setStatus('Projekt erstellt.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('projectSaveBtn').onclick = async () => {{
        const id = byId('projectId').value;
        if (!id) return setStatus('Bitte Projekt auswählen.', false);
        try {{
            await api('/api/projects/' + id, {{ method:'PATCH', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{
                name: byId('projectName').value.trim(),
                description: byId('projectDescription').value,
                status: byId('projectStatus').value,
                goal: byId('projectGoal').value,
                milestone: byId('projectMilestone').value,
                next_review_date: toDateOrNull(byId('projectNextReview').value),
            }}) }});
            await reloadAll();
            setStatus('Projekt gespeichert.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('projectDeleteBtn').onclick = async () => {{
        const id = byId('projectId').value;
        if (!id) return setStatus('Bitte Projekt auswählen.', false);
        if (!confirm('Projekt wirklich löschen?')) return;
        try {{
            await api('/api/projects/' + id, {{ method:'DELETE' }});
            clearProjectForm();
            await reloadAll();
            setStatus('Projekt gelöscht.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('taskCreateBtn').onclick = async () => {{
        try {{
            await api('/api/tasks', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{
                title: byId('taskTitle').value.trim(),
                project_id: toIntOrNull(byId('taskProject').value),
                status: byId('taskStatus').value,
                priority: Number(byId('taskPriority').value || 3),
                due_date: toDateOrNull(byId('taskDue').value),
                details: byId('taskDetails').value,
                blocked_reason: byId('taskBlockedReason').value,
                context: byId('taskContext').value,
                energy_level: byId('taskEnergy').value,
                estimate_minutes: Number(byId('taskEstimate').value || 0),
                tags: byId('taskTags').value,
                recurrence_days: toIntOrNull(byId('taskRecurrence').value),
            }}) }});
            clearTaskForm();
            await reloadAll();
            setStatus('Aufgabe erstellt.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('taskSaveBtn').onclick = async () => {{
        const id = byId('taskId').value;
        if (!id) return setStatus('Bitte Aufgabe auswählen.', false);
        try {{
            await api('/api/tasks/' + id, {{ method:'PATCH', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{
                title: byId('taskTitle').value.trim(),
                project_id: toIntOrNull(byId('taskProject').value),
                status: byId('taskStatus').value,
                priority: Number(byId('taskPriority').value || 3),
                due_date: toDateOrNull(byId('taskDue').value),
                details: byId('taskDetails').value,
                blocked_reason: byId('taskBlockedReason').value,
                context: byId('taskContext').value,
                energy_level: byId('taskEnergy').value,
                estimate_minutes: Number(byId('taskEstimate').value || 0),
                tags: byId('taskTags').value,
                recurrence_days: toIntOrNull(byId('taskRecurrence').value),
            }}) }});
            await reloadAll();
            await selectTask(Number(id));
            setStatus('Aufgabe gespeichert.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('taskDeleteBtn').onclick = async () => {{
        const id = byId('taskId').value;
        if (!id) return setStatus('Bitte Aufgabe auswählen.', false);
        if (!confirm('Aufgabe wirklich löschen?')) return;
        try {{
            await api('/api/tasks/' + id, {{ method:'DELETE' }});
            clearTaskForm();
            await reloadAll();
            setStatus('Aufgabe gelöscht.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('taskFromTemplateBtn').onclick = async () => {{
        const templateId = byId('taskTemplateSelect').value;
        if (!templateId) return setStatus('Bitte Vorlage auswählen.', false);
        try {{
            await api('/api/tasks/from-template', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{
                template_id: Number(templateId),
                title: byId('taskTitle').value.trim() || null,
                project_id: toIntOrNull(byId('taskProject').value),
                due_date: toDateOrNull(byId('taskDue').value),
            }}) }});
            await reloadAll();
            setStatus('Aufgabe aus Vorlage erstellt.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('taskNoteAddBtn').onclick = async () => {{
        const id = byId('taskId').value;
        if (!id) return setStatus('Bitte Aufgabe auswählen.', false);
        const note = byId('taskNoteInput').value.trim();
        if (!note) return setStatus('Notiz darf nicht leer sein.', false);
        try {{
            await api('/api/tasks/' + id + '/notes', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{ note }}) }});
            byId('taskNoteInput').value = '';
            await loadTaskNotesHistory(Number(id));
            setStatus('Notiz gespeichert.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('milestoneCreateBtn').onclick = async () => {{
        try {{
            await api('/api/milestones', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{
                project_id: Number(byId('milestoneProject').value),
                title: byId('milestoneTitle').value.trim(),
                due_date: toDateOrNull(byId('milestoneDue').value),
                status: byId('milestoneStatus').value,
            }}) }});
            clearMilestoneForm();
            await loadMilestones();
            setStatus('Meilenstein erstellt.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('milestoneSaveBtn').onclick = async () => {{
        const id = byId('milestoneId').value;
        if (!id) return setStatus('Bitte Meilenstein auswählen.', false);
        try {{
            await api('/api/milestones/' + id, {{ method:'PATCH', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{
                project_id: Number(byId('milestoneProject').value),
                title: byId('milestoneTitle').value.trim(),
                due_date: toDateOrNull(byId('milestoneDue').value),
                status: byId('milestoneStatus').value,
            }}) }});
            await loadMilestones();
            setStatus('Meilenstein gespeichert.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('milestoneDeleteBtn').onclick = async () => {{
        const id = byId('milestoneId').value;
        if (!id) return setStatus('Bitte Meilenstein auswählen.', false);
        if (!confirm('Meilenstein wirklich löschen?')) return;
        try {{
            await api('/api/milestones/' + id, {{ method:'DELETE' }});
            clearMilestoneForm();
            await loadMilestones();
            setStatus('Meilenstein gelöscht.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('templateCreateBtn').onclick = async () => {{
        try {{
            await api('/api/templates', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{
                name: byId('templateName').value.trim(),
                title: byId('templateTitle').value.trim(),
                project_id: toIntOrNull(byId('templateProject').value),
                status: byId('templateStatus').value,
                priority: Number(byId('templatePriority').value || 3),
                due_offset_days: toIntOrNull(byId('templateDueOffset').value),
                context: byId('templateContext').value,
                energy_level: byId('templateEnergy').value,
                recurrence_days: toIntOrNull(byId('templateRecurrence').value),
                tags: byId('templateTags').value,
                details: byId('templateDetails').value,
            }}) }});
            clearTemplateForm();
            await loadTemplates();
            setStatus('Vorlage erstellt.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('templateSaveBtn').onclick = async () => {{
        const id = byId('templateId').value;
        if (!id) return setStatus('Bitte Vorlage auswählen.', false);
        try {{
            await api('/api/templates/' + id, {{ method:'PATCH', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{
                name: byId('templateName').value.trim(),
                title: byId('templateTitle').value.trim(),
                project_id: toIntOrNull(byId('templateProject').value),
                status: byId('templateStatus').value,
                priority: Number(byId('templatePriority').value || 3),
                due_offset_days: toIntOrNull(byId('templateDueOffset').value),
                context: byId('templateContext').value,
                energy_level: byId('templateEnergy').value,
                recurrence_days: toIntOrNull(byId('templateRecurrence').value),
                tags: byId('templateTags').value,
                details: byId('templateDetails').value,
            }}) }});
            await loadTemplates();
            setStatus('Vorlage gespeichert.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};

    byId('templateDeleteBtn').onclick = async () => {{
        const id = byId('templateId').value;
        if (!id) return setStatus('Bitte Vorlage auswählen.', false);
        if (!confirm('Vorlage wirklich löschen?')) return;
        try {{
            await api('/api/templates/' + id, {{ method:'DELETE' }});
            clearTemplateForm();
            await loadTemplates();
            setStatus('Vorlage gelöscht.');
        }} catch (e) {{ setStatus(e.message, false); }}
    }};
}}

showWriteControls();
bindEvents();
reloadAll().then(() => setStatus('Bereit.')).catch((e) => setStatus(e.message, false));
</script>
</body>
</html>
"""


def _app_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _select_best_file(paths: list[Path], prefer_checksum: bool = False) -> Path | None:
    if prefer_checksum:
        match = next((path for path in paths if path.is_file() and _checksum_matches(path)), None)
        if match is not None:
            return match
    return _latest_existing_file(paths)


def _download_candidates() -> list[dict[str, Any]]:
    base = _app_root()
    specs = [
        {
            "id": "windows",
            "label": "Windows (pr.exe)",
            "filename": "pr.exe",
            "paths": [base / "pr.exe", base / "dist" / "pr.exe"],
            "prefer_checksum": True,
        },
        {
            "id": "linux",
            "label": "Linux (pr)",
            "filename": "pr",
            "paths": [base / "dist" / "pr", base / "pr"],
            "prefer_checksum": False,
        },
        {
            "id": "macos",
            "label": "macOS (pr.pkg)",
            "filename": "pr.pkg",
            "paths": [base / "build" / "pr" / "pr.pkg", base / "dist" / "pr.pkg"],
            "prefer_checksum": False,
        },
    ]
    available: list[dict[str, Any]] = []
    for spec in specs:
        selected = _select_best_file(spec["paths"], prefer_checksum=spec["prefer_checksum"])
        if selected is None:
            continue
        available.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "filename": spec["filename"],
                "path": selected,
            }
        )
    return available


def _github_release_downloads() -> list[dict[str, Any]]:
    now = time.time()
    cached = _RELEASE_CACHE.get("downloads", [])
    last_ts = float(_RELEASE_CACHE.get("timestamp", 0.0) or 0.0)
    if cached and (now - last_ts) < GITHUB_RELEASES_CACHE_SECONDS:
        return list(cached)

    try:
        request = urllib.request.Request(
            GITHUB_RELEASES_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "pmtool-server",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, ValueError):
        return []

    downloads: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for release in payload:
            if not isinstance(release, dict):
                continue
            tag = str(release.get("tag_name") or release.get("name") or "release").strip()
            assets = release.get("assets") or []
            if not isinstance(assets, list):
                continue
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                url = str(asset.get("browser_download_url") or "").strip()
                name = str(asset.get("name") or "asset").strip()
                if not url:
                    continue
                downloads.append(
                    {
                        "id": url,
                        "label": f"{tag} - {name}",
                        "filename": name,
                        "url": url,
                        "release": tag,
                    }
                )

    _RELEASE_CACHE["timestamp"] = now
    _RELEASE_CACHE["downloads"] = downloads
    return downloads


LOGIN_HTML = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Projektmanager Login</title>
  <style>
        :root { --bg1:#12233c; --bg2:#275e91; --panel:#ffffff; --line:#c9d9eb; --text:#142132; --muted:#4f647a; --accent:#0f766e; --accent2:#0b5f58; --danger:#b42318; --ok:#166534; }
        * { box-sizing:border-box; }
        body { margin:0; min-height:100vh; display:grid; place-items:center; padding:14px; color:var(--text); font-family:Segoe UI, Arial, sans-serif; background:radial-gradient(circle at 15% 20%, rgba(255,255,255,0.15), transparent 45%), linear-gradient(140deg, var(--bg1), var(--bg2)); }
        .shell { width:min(950px, 100%); display:grid; grid-template-columns:1fr 1fr; gap:12px; }
        .card { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:18px; box-shadow:0 16px 34px rgba(10, 20, 40, 0.2); }
        h1 { margin:0 0 8px; font-size:22px; }
        h2 { margin:0 0 8px; font-size:18px; }
        p { color:var(--muted); font-size:14px; margin:0 0 8px; }
        input, button, select { width:100%; font:inherit; padding:10px; border-radius:9px; margin-top:10px; }
        input, select { border:1px solid #bfd0e4; }
        button { border:none; background:var(--accent); color:#fff; cursor:pointer; font-weight:600; }
        button:hover { background:var(--accent2); }
        .err { color:var(--danger); min-height:18px; font-size:13px; margin-top:8px; }
        .ok { color:var(--ok); min-height:18px; font-size:13px; margin-top:8px; }
        .hint { color:var(--muted); font-size:12px; margin-top:8px; }
        .badge { display:inline-block; padding:4px 8px; border-radius:999px; background:#e9f7f4; color:#0f766e; font-size:12px; font-weight:700; margin-bottom:8px; }
        @media (max-width: 860px) {
            .shell { grid-template-columns:1fr; }
        }
  </style>
</head>
<body>
    <div class="shell">
        <form class="card" method="post" action="/login">
            <h1>Projektmanager Zugang</h1>
            <p>Anmeldung erfolgt mit E-Mail und Passwort.</p>
            <span class="badge">Sicherer Login</span>
            <input type="hidden" name="desktop_token" value="__DESKTOP_TOKEN__" />
            <input type="email" name="email" placeholder="E-Mail" required autofocus />
            <input type="password" name="password" placeholder="Passwort" required />
            <button type="submit">Einloggen</button>
            <div class="err">__LOGIN_ERROR__</div>
        </form>

        <form class="card" method="post" action="/register">
            <h2>Neuen Account erstellen</h2>
            <p>Account wird direkt aktiviert.</p>
                        <input type="email" name="email" placeholder="Neue E-Mail" required />
            <input type="password" name="password" placeholder="Passwort (mind. 8 Zeichen)" required />
            <button type="submit">Account anlegen</button>
            <div class="err">__REGISTER_ERROR__</div>
            <div class="ok">__REGISTER_INFO__</div>
            <div class="hint">Neue Accounts sind immer reader.</div>
        </form>
    </div>
</body>
</html>
"""


def _render_login_html(login_error: str = "", register_error: str = "", register_info: str = "", desktop_token: str = "") -> str:
        return (
                LOGIN_HTML
                .replace("__LOGIN_ERROR__", login_error)
                .replace("__REGISTER_ERROR__", register_error)
                .replace("__REGISTER_INFO__", register_info)
        .replace("__DESKTOP_TOKEN__", html.escape(desktop_token, quote=True))
        )


class _CollabHandler(BaseHTTPRequestHandler):
    server_version = "PMToolCollab/2.0"

    def _send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline';")

    def _sessions(self) -> dict[str, dict[str, Any]]:
        sessions = getattr(self.server, "sessions", None)
        if not isinstance(sessions, dict):
            sessions = {}
            setattr(self.server, "sessions", sessions)
        return sessions

    def _sessions_lock(self) -> threading.Lock:
        lock = getattr(self.server, "sessions_lock", None)
        if lock is None or not hasattr(lock, "acquire") or not hasattr(lock, "release"):
            lock = threading.Lock()
            setattr(self.server, "sessions_lock", lock)
        return lock

    def _desktop_logins(self) -> dict[str, dict[str, Any]]:
        desktop_logins = getattr(self.server, "desktop_logins", None)
        if not isinstance(desktop_logins, dict):
            desktop_logins = {}
            setattr(self.server, "desktop_logins", desktop_logins)
        return desktop_logins

    def _desktop_logins_lock(self) -> threading.Lock:
        lock = getattr(self.server, "desktop_logins_lock", None)
        if lock is None or not hasattr(lock, "acquire") or not hasattr(lock, "release"):
            lock = threading.Lock()
            setattr(self.server, "desktop_logins_lock", lock)
        return lock

    def _request_log(self) -> dict[str, list[float]]:
        request_log = getattr(self.server, "request_log", None)
        if not isinstance(request_log, dict):
            request_log = {}
            setattr(self.server, "request_log", request_log)
        return request_log

    def _client_ip(self) -> str:
        return self.client_address[0] if self.client_address else "unknown"

    def _rate_limit_key(self) -> str:
        return self._client_ip()

    def _is_rate_limited(self) -> bool:
        key = self._rate_limit_key()
        now = time.time()
        window_start = now - 60
        request_log = self._request_log()
        recent = [ts for ts in request_log.get(key, []) if ts >= window_start]
        if len(recent) >= RATE_LIMIT_REQUESTS_PER_MINUTE:
            request_log[key] = recent
            return True
        recent.append(now)
        request_log[key] = recent
        return False
    def _enforce_rate_limit(self, path: str) -> bool:
        if not self._is_rate_limited():
            return True
        if path.startswith("/api/"):
            self._send_json({"error": "Zu viele Anfragen. Bitte kurz warten."}, status=HTTPStatus.TOO_MANY_REQUESTS)
            return False
        if path == "/login":
            self._send_html(
                _render_login_html(login_error="Zu viele Anfragen. Bitte kurz warten."),
                status=HTTPStatus.TOO_MANY_REQUESTS,
            )
            return False
        self._send_html("<h1>429 Too Many Requests</h1>", status=HTTPStatus.TOO_MANY_REQUESTS)
        return False

    def _send_json(self, payload: dict[str, Any] | list[dict[str, Any]], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_str: str, status: int = 200) -> None:
        body = html_str.encode("utf-8")
        self.send_response(status)
        self._send_security_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self._send_security_headers()
        self.send_header("Location", location)
        self.end_headers()

    def _read_content_length(self) -> int:
        raw = self.headers.get("Content-Length", "0")
        try:
            content_length = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Ungültiger Content-Length Header") from exc
        if content_length < 0:
            raise ValueError("Ungültiger Content-Length Header")
        if content_length > MAX_REQUEST_BODY_BYTES:
            raise ValueError("Request-Body ist zu groß")
        return content_length

    def _read_json(self) -> dict[str, Any]:
        content_length = self._read_content_length()
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Ungültiger JSON-Body") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON-Body muss ein Objekt sein")
        return data

    def _read_form(self) -> dict[str, str]:
        content_length = self._read_content_length()
        raw = self.rfile.read(content_length) if content_length > 0 else b""
        parsed = parse_qs(raw.decode("utf-8"))
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def _get_cookie(self, key: str) -> str | None:
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
        except CookieError:
            return None
        morsel = cookie.get(key)
        if morsel is None:
            return None
        return morsel.value

    def _set_session_cookie(self, session_id: str) -> None:
        self.send_header("Set-Cookie", f"PMTOOL_SESSION={session_id}; HttpOnly; Path=/; SameSite=Lax")

    def _clear_session_cookie(self) -> None:
        self.send_header("Set-Cookie", "PMTOOL_SESSION=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax")

    def _clear_session(self, session_id: str) -> None:
        sessions = self._sessions()
        with self._sessions_lock():
            sessions.pop(session_id, None)

    def _create_session(self, principal: dict[str, Any]) -> str:
        session_id = secrets.token_urlsafe(32)
        session_data = dict(principal)
        session_data["_last_activity"] = time.time()
        sessions = self._sessions()
        with self._sessions_lock():
            sessions[session_id] = session_data
        return session_id

    def _set_desktop_login(self, token: str, principal: dict[str, Any], session_id: str | None = None) -> None:
        token = token.strip()
        if not token:
            return
        payload = {
            "account": {k: v for k, v in principal.items() if not str(k).startswith("_")},
            "created_at": time.time(),
        }
        if session_id:
            payload["session_id"] = session_id
        with self._desktop_logins_lock():
            self._desktop_logins()[token] = payload

    def _pop_desktop_login(self, token: str) -> dict[str, Any] | None:
        token = token.strip()
        if not token:
            return None
        with self._desktop_logins_lock():
            return self._desktop_logins().pop(token, None)

    def _is_valid_creation_api_key(self, api_key: str) -> bool:
        value = (api_key or "").strip()
        if not value:
            return False
        legacy_api_key = getattr(self.server, "legacy_api_key", None)
        if legacy_api_key and secrets.compare_digest(value, str(legacy_api_key)):
            return True
        accounts_path = getattr(self.server, "accounts_path", DEFAULT_ACCOUNTS_PATH)
        return authorize_account_creation_api_key(value, accounts_path, require_editor=True) is not None

    def _authenticate(self) -> dict[str, Any] | None:
        """Authenticate only via active session cookie."""
        cookie_session = self._get_cookie("PMTOOL_SESSION")
        if cookie_session:
            sessions = self._sessions()
            with self._sessions_lock():
                principal = sessions.get(cookie_session)
            if isinstance(principal, dict):
                now = time.time()
                last_activity = principal.get("_last_activity", 0)
                if not isinstance(last_activity, (int, float)):
                    last_activity = 0
                if now - float(last_activity) > SESSION_TIMEOUT_SECONDS:
                    with self._sessions_lock():
                        sessions.pop(cookie_session, None)
                    return None
                with self._sessions_lock():
                    principal["_last_activity"] = now
                return {k: v for k, v in principal.items() if not k.startswith("_")}

        return None

    def _require_auth_json(self) -> dict[str, Any] | None:
        principal = self._authenticate()
        if principal is None:
            self._send_json({"error": "Unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
            return None
        return principal

    def _require_write_json(self, principal: dict[str, Any]) -> bool:
        if principal.get("role", "reader") != "editor":
            self._send_json({"error": "Du bist nicht berechtigt."}, status=HTTPStatus.FORBIDDEN)
            return False
        return True

    def _bool_param(self, query: dict[str, list[str]], key: str, default: bool = False) -> bool:
        value = query.get(key, [str(default)])[0].strip().lower()
        return value in {"1", "true", "yes", "on"}

    def _request_base_url(self) -> str:
        proto = self.headers.get("X-Forwarded-Proto", "").strip()
        if not proto:
            proto = "https" if self.server.server_port == 443 else "http"
        host = self.headers.get("X-Forwarded-Host", "").strip() or self.headers.get("Host", "").strip()
        if not host:
            host = f"localhost:{self.server.server_port}"
        return f"{proto}://{host}"

    def _path_id(self, prefix: str, path: str) -> int | None:
        if not path.startswith(prefix):
            return None
        suffix = path[len(prefix) :]
        if not suffix or "/" in suffix:
            return None
        try:
            return int(suffix)
        except ValueError:
            return None

    def _handle_get_api(self, parsed_path: Any) -> bool:
        principal = self._require_auth_json()
        if principal is None:
            return True

        path = parsed_path.path
        if path in {"/me", "/api/me"}:
            self._send_json({"account": principal})
            return True

        if path in {"/projects", "/api/projects"}:
            self._send_json([dict(row) for row in list_projects()])
            return True

        if path.startswith("/api/projects/") and path.endswith("/shares"):
            project_id_str = path[len("/api/projects/") : -len("/shares")]
            try:
                project_id = int(project_id_str)
            except ValueError:
                self._send_json({"error": "project_id muss eine Zahl sein"}, status=HTTPStatus.BAD_REQUEST)
                return True
            self._send_json([dict(row) for row in list_project_shares(project_id)])
            return True

        if path in {"/tasks", "/api/tasks"}:
            query = parse_qs(parsed_path.query)
            project_id = query.get("project_id", [None])[0]
            status = query.get("status", [None])[0]
            search = query.get("search", [None])[0]
            due_filter = query.get("due_filter", [None])[0]
            tag = query.get("tag", [None])[0]
            context = query.get("context", [None])[0]
            energy_level = query.get("energy_level", [None])[0]
            include_done = self._bool_param(query, "include_done", default=True)

            if project_id in (None, ""):
                project_id_value = None
            else:
                try:
                    project_id_value = int(project_id)
                except ValueError:
                    self._send_json({"error": "project_id muss eine Zahl sein"}, status=HTTPStatus.BAD_REQUEST)
                    return True

            rows = list_tasks(
                project_id=project_id_value,
                status=status,
                search=search,
                due_filter=due_filter,
                tag=tag,
                context=context,
                energy_level=energy_level,
                include_done=include_done,
            )
            self._send_json([dict(row) for row in rows])
            return True

        if path == "/api/dashboard":
            self._send_json({"tasks": task_dashboard_counts(), "projects": project_dashboard_counts()})
            return True

        if path == "/api/milestones":
            query = parse_qs(parsed_path.query)
            project_id = query.get("project_id", [None])[0]
            if project_id in (None, ""):
                project_id_value = None
            else:
                try:
                    project_id_value = int(project_id)
                except ValueError:
                    self._send_json({"error": "project_id muss eine Zahl sein"}, status=HTTPStatus.BAD_REQUEST)
                    return True
            self._send_json([dict(row) for row in list_milestones(project_id_value)])
            return True

        if path == "/api/templates":
            self._send_json([dict(row) for row in list_templates()])
            return True

        if path == "/api/downloads":
            downloads = _github_release_downloads()
            if not downloads:
                downloads = [
                    {
                        "id": entry["id"],
                        "label": entry["label"],
                        "filename": entry["filename"],
                        "url": f"/download/package/{entry['id']}",
                    }
                    for entry in _download_candidates()
                ]
            self._send_json({"downloads": downloads})
            return True

        # Sync API für lokale App-Synchronisierung
        if path == "/api/sync/projects":
            query = parse_qs(parsed_path.query)
            since = query.get("since", [None])[0]
            projects = [dict(row) for row in list_projects()]
            if since:
                # Nur Projekte die seit 'since' geändert wurden
                projects = [p for p in projects if p.get("updated_at", "") >= since]
            self._send_json(projects)
            return True

        if path == "/api/sync/tasks":
            query = parse_qs(parsed_path.query)
            since = query.get("since", [None])[0]
            project_id = query.get("project_id", [None])[0]
            project_id_value = None if project_id in (None, "") else int(project_id)
            tasks = [dict(row) for row in list_tasks(project_id=project_id_value, include_done=True)]
            if since:
                # Nur Aufgaben die seit 'since' geändert wurden
                tasks = [t for t in tasks if t.get("updated_at", "") >= since]
            self._send_json(tasks)
            return True

        if path == "/api/sync/milestones":
            query = parse_qs(parsed_path.query)
            since = query.get("since", [None])[0]
            project_id = query.get("project_id", [None])[0]
            project_id_value = None if project_id in (None, "") else int(project_id)
            milestones = [dict(row) for row in list_milestones(project_id_value)]
            if since:
                milestones = [m for m in milestones if m.get("updated_at", "") >= since]
            self._send_json(milestones)
            return True

        if path == "/api/sync/templates":
            query = parse_qs(parsed_path.query)
            since = query.get("since", [None])[0]
            templates = [dict(row) for row in list_templates()]
            if since:
                templates = [t for t in templates if t.get("updated_at", "") >= since]
            self._send_json(templates)
            return True

        if path == "/api/sync/project-shares":
            query = parse_qs(parsed_path.query)
            since = query.get("since", [None])[0]
            project_ids = [row["id"] for row in list_projects()]
            if not project_ids:
                self._send_json([])
                return True
            placeholders = ", ".join(["?"] * len(project_ids))
            with get_connection() as conn:
                rows = conn.execute(
                    f"SELECT id, project_id, account_name, created_at FROM project_shares WHERE project_id IN ({placeholders})",
                    project_ids,
                ).fetchall()
            shares = [dict(row) for row in rows]
            if since:
                shares = [s for s in shares if s.get("created_at", "") >= since]
            self._send_json(shares)
            return True

        if path.startswith("/api/tasks/") and path.endswith("/notes"):
            task_id_str = path[len("/api/tasks/") : -len("/notes")]
            try:
                task_id = int(task_id_str)
            except ValueError:
                self._send_json({"error": "task_id muss eine Zahl sein"}, status=HTTPStatus.BAD_REQUEST)
                return True
            self._send_json([dict(row) for row in list_task_notes(task_id)])
            return True

        if path.startswith("/api/tasks/") and path.endswith("/history"):
            task_id_str = path[len("/api/tasks/") : -len("/history")]
            try:
                task_id = int(task_id_str)
            except ValueError:
                self._send_json({"error": "task_id muss eine Zahl sein"}, status=HTTPStatus.BAD_REQUEST)
                return True
            self._send_json([dict(row) for row in list_task_history(task_id)])
            return True

        return False

    def do_GET(self) -> None:  # noqa: N802
        principal_for_context = self._authenticate()
        if principal_for_context is not None:
            set_current_principal(principal_for_context)
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if not self._enforce_rate_limit(path):
                return

            if path == "/health":
                self._send_json({"status": "ok"})
                return

            if path == "/":
                if self._authenticate() is None:
                    self._redirect("/login")
                else:
                    self._redirect("/app")
                return

            if path == "/login":
                query = parse_qs(parsed.query)
                desktop_token = query.get("desktop_token", [""])[0].strip()
                principal = self._authenticate()
                if principal is not None:
                    if desktop_token:
                        session_id = self._get_cookie("PMTOOL_SESSION")
                        self._set_desktop_login(desktop_token, principal, session_id=session_id)
                    self._redirect("/app")
                    return
                self._send_html(_render_login_html(desktop_token=desktop_token))
                return

            if path == "/logout":
                session_id = self._get_cookie("PMTOOL_SESSION")
                if session_id:
                    self._clear_session(session_id)
                self._clear_session_cookie()
                self._redirect("/login")
                return

            if path == "/api/desktop-login":
                query = parse_qs(parsed.query)
                token = query.get("token", [""])[0].strip()
                payload = self._pop_desktop_login(token)
                if payload is None:
                    self._send_json({"status": "pending"})
                else:
                    self._send_json({
                        "status": "ready",
                        "account": payload.get("account", {}),
                        "session_id": payload.get("session_id"),
                    })
                return

            if path == "/download/exe":
                principal = self._authenticate()
                if principal is None:
                    self._redirect("/login")
                    return
                candidate_paths = [
                    Path(__file__).resolve().parents[1] / "pr.exe",
                    Path(__file__).resolve().parents[1] / "dist" / "pr.exe",
                ]
                exe_path = next((path for path in candidate_paths if path.is_file() and _checksum_matches(path)), None)
                if exe_path is None:
                    exe_path = _latest_existing_file(candidate_paths)
                if exe_path is None:
                    self._send_html("<h1>404 - exe nicht gefunden</h1>", status=HTTPStatus.NOT_FOUND)
                    return
                try:
                    with open(exe_path, "rb") as f:
                        exe_data = f.read()
                    self.send_response(HTTPStatus.OK)
                    self._send_security_headers()
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Disposition", "attachment; filename=pr.exe")
                    self.send_header("Content-Length", str(len(exe_data)))
                    self.end_headers()
                    self.wfile.write(exe_data)
                except (OSError, IOError) as e:
                    self._send_html(f"<h1>500 - Fehler beim Laden: {str(e)}</h1>", status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            if path.startswith("/download/package/"):
                principal = self._authenticate()
                if principal is None:
                    self._redirect("/login")
                    return
                package_id = path[len("/download/package/") :].strip("/")
                downloads = {entry["id"]: entry for entry in _download_candidates()}
                package = downloads.get(package_id)
                if package is None:
                    self._send_html("<h1>404 - Paket nicht gefunden</h1>", status=HTTPStatus.NOT_FOUND)
                    return
                try:
                    config_payload = {
                        "base_url": self._request_base_url(),
                    }
                    archive_name = f"pmtool-{package_id}.zip"
                    buffer = io.BytesIO()
                    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
                        zip_file.writestr("pmtool_server.json", json.dumps(config_payload, indent=2))
                        zip_file.write(package["path"], arcname=package["filename"])
                        checksum_path = package["path"].with_name(f"{package['path'].name}.sha256")
                        if checksum_path.is_file():
                            zip_file.write(checksum_path, arcname=checksum_path.name)
                    archive_data = buffer.getvalue()
                    self.send_response(HTTPStatus.OK)
                    self._send_security_headers()
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition", f"attachment; filename={archive_name}")
                    self.send_header("Content-Length", str(len(archive_data)))
                    self.end_headers()
                    self.wfile.write(archive_data)
                except (OSError, IOError, ValueError) as e:
                    self._send_html(f"<h1>500 - Fehler beim Laden: {str(e)}</h1>", status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            if path == "/app":
                principal = self._authenticate()
                if principal is None:
                    self._redirect("/login")
                    return
                if principal.get("role", "reader") != "editor":
                    self._send_html("<h1>Du bist nicht berechtigt.</h1>", status=HTTPStatus.FORBIDDEN)
                    return
                self._send_html(_app_html(principal))
                return

            if path.startswith("/api/") or path in {"/me", "/projects", "/tasks"}:
                principal = self._authenticate()
                if principal is None:
                    self._send_json({"error": "Unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
                    return
                if principal.get("role", "reader") != "editor":
                    self._send_json({"error": "Du bist nicht berechtigt."}, status=HTTPStatus.FORBIDDEN)
                    return
                if self._handle_get_api(parsed):
                    return

            self._send_html("<h1>404 Not Found</h1>", status=HTTPStatus.NOT_FOUND)
        finally:
            clear_current_principal()

    def do_POST(self) -> None:  # noqa: N802
        principal_for_context = self._authenticate()
        if principal_for_context is not None:
            set_current_principal(principal_for_context)
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if not self._enforce_rate_limit(path):
                return

            if path == "/login":
                try:
                    payload = self._read_form()
                    email = payload.get("email", "").strip()
                    password = payload.get("password", "")
                    desktop_token = payload.get("desktop_token", "").strip()
                except ValueError as exc:
                    self._send_html(_render_login_html(login_error=str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return

                try:
                    principal = authenticate(
                        email=email,
                        password=password,
                        path=getattr(self.server, "accounts_path", DEFAULT_ACCOUNTS_PATH),
                    )
                except ValueError as exc:
                    self._send_html(_render_login_html(login_error=str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return
                if principal is None:
                    self._send_html(_render_login_html(login_error="E-Mail oder Passwort stimmt nicht."), status=HTTPStatus.UNAUTHORIZED)
                    return
                session_id = self._create_session(principal)
                self._set_desktop_login(desktop_token, principal, session_id=session_id)
                self.send_response(HTTPStatus.FOUND)
                self._send_security_headers()
                self._set_session_cookie(session_id)
                self.send_header("Location", "/app")
                self.end_headers()
                return

            if path == "/register":
                try:
                    payload = self._read_form()
                    email = payload.get("email", "").strip()
                    password = payload.get("password", "")
                except ValueError as exc:
                    self._send_html(_render_login_html(register_error=str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return

                accounts_path = getattr(self.server, "accounts_path", DEFAULT_ACCOUNTS_PATH)

                try:
                    result = create_account(email=email, password=password, role="reader", path=accounts_path)
                except ValueError as exc:
                    self._send_html(_render_login_html(register_error=str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return

                set_account_enabled(result["email"], True, path=accounts_path)
                self._send_html(
                    _render_login_html(register_info="Account erstellt und aktiviert."),
                    status=HTTPStatus.OK,
                )
                return

            principal = self._require_auth_json()
            if principal is None:
                return
            if path in {"/projects", "/api/projects"}:
                if not self._require_write_json(principal):
                    return
                try:
                    payload = self._read_json()
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                try:
                    name = payload.get("name", "").strip()
                    if not name:
                        raise ValueError("name erforderlich")
                    add_project(
                        name,
                        team=payload.get("team", ""),
                        description=payload.get("description", ""),
                        status=payload.get("status", "active"),
                        goal=payload.get("goal", ""),
                        milestone=payload.get("milestone", ""),
                        risk_probability=payload.get("risk_probability", payload.get("risk_weight", 3)),
                        risk_impact=payload.get("risk_impact", payload.get("risk_weight", 3)),
                        risk=payload.get("risk", ""),
                        risk_weight=payload.get("risk_weight", 3),
                        risk_countermeasure=payload.get("risk_countermeasure", ""),
                        next_review_date=payload.get("next_review_date"),
                    )
                    self._send_json({"ok": True})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            project_id = self._path_id("/api/projects/", path)
            if project_id is not None:
                if not self._require_write_json(principal):
                    return
                try:
                    payload = self._read_json()
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                try:
                    update_project(
                        project_id,
                        name=payload.get("name"),
                        team=payload.get("team"),
                        description=payload.get("description"),
                        status=payload.get("status"),
                        goal=payload.get("goal"),
                        milestone=payload.get("milestone"),
                        risk_probability=payload.get("risk_probability"),
                        risk_impact=payload.get("risk_impact"),
                        risk=payload.get("risk"),
                        risk_weight=payload.get("risk_weight"),
                        risk_countermeasure=payload.get("risk_countermeasure"),
                        next_review_date=payload.get("next_review_date"),
                    )
                    self._send_json({"ok": True})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path.startswith("/api/projects/") and path.endswith("/share"):
                if not self._require_write_json(principal):
                    return
                project_id_str = path[len("/api/projects/") : -len("/share")]
                try:
                    project_id = int(project_id_str)
                    payload = self._read_json()
                    account_name = str(payload.get("account_name", "")).strip()
                    if not account_name:
                        raise ValueError("account_name erforderlich")
                    share_project(project_id, account_name)
                    self._send_json({"ok": True})
                except (TypeError, ValueError) as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path.startswith("/api/projects/") and path.endswith("/unshare"):
                if not self._require_write_json(principal):
                    return
                project_id_str = path[len("/api/projects/") : -len("/unshare")]
                try:
                    project_id = int(project_id_str)
                    payload = self._read_json()
                    account_name = str(payload.get("account_name", "")).strip()
                    if not account_name:
                        raise ValueError("account_name erforderlich")
                    unshare_project(project_id, account_name)
                    self._send_json({"ok": True})
                except (TypeError, ValueError) as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path in {"/tasks", "/api/tasks"}:
                if not self._require_write_json(principal):
                    return
                try:
                    payload = self._read_json()
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                try:
                    title = payload.get("title", "").strip()
                    if not title:
                        raise ValueError("title erforderlich")
                    project_id = payload.get("project_id")
                    status_val = payload.get("status", "open")
                    priority = payload.get("priority", 3)
                    add_task(
                        title,
                        project_id=project_id,
                        status=status_val,
                        priority=priority,
                        due_date=payload.get("due_date"),
                        details=payload.get("details", ""),
                        blocked_reason=payload.get("blocked_reason", ""),
                        risk_probability=payload.get("risk_probability", payload.get("risk_weight", 3)),
                        risk_impact=payload.get("risk_impact", payload.get("risk_weight", 3)),
                        risk=payload.get("risk", ""),
                        risk_weight=payload.get("risk_weight", 3),
                        risk_countermeasure=payload.get("risk_countermeasure", ""),
                        context=payload.get("context", ""),
                        energy_level=payload.get("energy_level", "medium"),
                        estimate_minutes=payload.get("estimate_minutes", 0),
                        tags=payload.get("tags", ""),
                        recurrence_days=payload.get("recurrence_days"),
                    )
                    self._send_json({"ok": True})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/tasks/from-template":
                if not self._require_write_json(principal):
                    return
                try:
                    payload = self._read_json()
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                try:
                    template_id = int(payload.get("template_id"))
                    task_id = create_task_from_template(
                        template_id,
                        title=payload.get("title"),
                        project_id=payload.get("project_id"),
                        due_date=payload.get("due_date"),
                    )
                    self._send_json({"ok": True, "task_id": task_id})
                except (TypeError, ValueError) as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path.startswith("/api/tasks/") and path.endswith("/notes"):
                if not self._require_write_json(principal):
                    return
                task_id_str = path[len("/api/tasks/") : -len("/notes")]
                try:
                    task_id = int(task_id_str)
                    payload = self._read_json()
                    note = payload.get("note", "").strip()
                    add_task_note(task_id, note)
                    self._send_json({"ok": True})
                except (TypeError, ValueError) as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path.startswith("/api/tasks/") and path.count("/") == 3:
                task_id_str = path.rsplit("/", 1)[1]
                try:
                    task_id = int(task_id_str)
                except ValueError:
                    self._send_json({"error": "task_id muss eine Zahl sein"}, status=HTTPStatus.BAD_REQUEST)
                    return

                if not self._require_write_json(principal):
                    return
                try:
                    payload = self._read_json()
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return

                try:
                    update_task(task_id, **payload)
                    self._send_json({"ok": True})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/milestones":
                if not self._require_write_json(principal):
                    return
                try:
                    payload = self._read_json()
                    project_id = int(payload.get("project_id"))
                    title = str(payload.get("title", "")).strip()
                    if not title:
                        raise ValueError("title erforderlich")
                    add_milestone(project_id, title, payload.get("due_date"), payload.get("status", "open"))
                    self._send_json({"ok": True})
                except (TypeError, ValueError) as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            milestone_id = self._path_id("/api/milestones/", path)
            if milestone_id is not None:
                if not self._require_write_json(principal):
                    return
                try:
                    payload = self._read_json()
                    update_milestone(
                        milestone_id,
                        title=payload.get("title"),
                        due_date=payload.get("due_date"),
                        status=payload.get("status"),
                        project_id=payload.get("project_id"),
                    )
                    self._send_json({"ok": True})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/templates":
                if not self._require_write_json(principal):
                    return
                try:
                    payload = self._read_json()
                    name = str(payload.get("name", "")).strip()
                    title = str(payload.get("title", "")).strip()
                    if not name or not title:
                        raise ValueError("name und title erforderlich")
                    add_template(
                        name,
                        title,
                        details=payload.get("details", ""),
                        project_id=payload.get("project_id"),
                        status=payload.get("status", "open"),
                        priority=payload.get("priority", 3),
                        due_offset_days=payload.get("due_offset_days"),
                        context=payload.get("context", ""),
                        energy_level=payload.get("energy_level", "medium"),
                        tags=payload.get("tags", ""),
                        recurrence_days=payload.get("recurrence_days"),
                    )
                    self._send_json({"ok": True})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            template_id = self._path_id("/api/templates/", path)
            if template_id is not None:
                if not self._require_write_json(principal):
                    return
                try:
                    payload = self._read_json()
                    update_template(
                        template_id,
                        name=payload.get("name"),
                        title=payload.get("title"),
                        details=payload.get("details"),
                        project_id=payload.get("project_id"),
                        status=payload.get("status"),
                        priority=payload.get("priority"),
                        due_offset_days=payload.get("due_offset_days"),
                        context=payload.get("context"),
                        energy_level=payload.get("energy_level"),
                        tags=payload.get("tags"),
                        recurrence_days=payload.get("recurrence_days"),
                    )
                    self._send_json({"ok": True})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            # Sync API - Upload lokale Änderungen zum Server
            if path == "/api/sync/upload":
                if not self._require_write_json(principal):
                    return
                try:
                    payload = self._read_json()
                    conflicts = []
                    principal_name = str(principal.get("name", "")).strip().lower()
                    
                    # Projekte
                    for project_data in payload.get("projects", []):
                        try:
                            update_project(
                                project_data.get("id"),
                                name=project_data.get("name"),
                                team=project_data.get("team"),
                                description=project_data.get("description"),
                                status=project_data.get("status"),
                                goal=project_data.get("goal"),
                                milestone=project_data.get("milestone"),
                                risk=project_data.get("risk"),
                                risk_rows=risk_rows_from_json(project_data.get("risk_rows_json")),
                                risk_probability=project_data.get("risk_probability"),
                                risk_impact=project_data.get("risk_impact"),
                                risk_weight=project_data.get("risk_weight"),
                                risk_countermeasure=project_data.get("risk_countermeasure"),
                                next_review_date=project_data.get("next_review_date"),
                            )
                        except ValueError as e:
                            if "existiert nicht" in str(e):
                                try:
                                    _upsert_row("projects", project_data)
                                    continue
                                except ValueError as upsert_error:
                                    e = upsert_error
                            conflicts.append({"type": "project", "id": project_data.get("id"), "error": str(e)})
                    
                    # Aufgaben
                    for task_data in payload.get("tasks", []):
                        try:
                            update_task(
                                task_data.get("id"),
                                title=task_data.get("title"),
                                details=task_data.get("details"),
                                status=task_data.get("status"),
                                priority=task_data.get("priority"),
                                due_date=task_data.get("due_date"),
                                blocked_reason=task_data.get("blocked_reason"),
                                risk=task_data.get("risk"),
                                risk_rows=risk_rows_from_json(task_data.get("risk_rows_json")),
                                risk_probability=task_data.get("risk_probability"),
                                risk_impact=task_data.get("risk_impact"),
                                risk_weight=task_data.get("risk_weight"),
                                risk_countermeasure=task_data.get("risk_countermeasure"),
                                project_id=task_data.get("project_id"),
                                context=task_data.get("context"),
                                energy_level=task_data.get("energy_level"),
                                estimate_minutes=task_data.get("estimate_minutes"),
                                tags=task_data.get("tags"),
                                recurrence_days=task_data.get("recurrence_days"),
                            )
                        except ValueError as e:
                            if "existiert nicht" in str(e):
                                try:
                                    _upsert_row("tasks", task_data)
                                    continue
                                except ValueError as upsert_error:
                                    e = upsert_error
                            conflicts.append({"type": "task", "id": task_data.get("id"), "error": str(e)})
                    
                    # Meilensteine
                    for milestone_data in payload.get("milestones", []):
                        try:
                            update_milestone(
                                milestone_data.get("id"),
                                title=milestone_data.get("title"),
                                due_date=milestone_data.get("due_date"),
                                status=milestone_data.get("status"),
                                project_id=milestone_data.get("project_id"),
                            )
                        except ValueError as e:
                            if "existiert nicht" in str(e):
                                try:
                                    _upsert_row("project_milestones", milestone_data)
                                    continue
                                except ValueError as upsert_error:
                                    e = upsert_error
                            conflicts.append({"type": "milestone", "id": milestone_data.get("id"), "error": str(e)})
                    
                    # Vorlagen
                    for template_data in payload.get("templates", []):
                        try:
                            update_template(
                                template_data.get("id"),
                                name=template_data.get("name"),
                                title=template_data.get("title"),
                                details=template_data.get("details"),
                                project_id=template_data.get("project_id"),
                                status=template_data.get("status"),
                                priority=template_data.get("priority"),
                                due_offset_days=template_data.get("due_offset_days"),
                                context=template_data.get("context"),
                                energy_level=template_data.get("energy_level"),
                                tags=template_data.get("tags"),
                                recurrence_days=template_data.get("recurrence_days"),
                            )
                        except ValueError as e:
                            if "existiert nicht" in str(e):
                                try:
                                    _upsert_row("task_templates", template_data)
                                    continue
                                except ValueError as upsert_error:
                                    e = upsert_error
                            conflicts.append({"type": "template", "id": template_data.get("id"), "error": str(e)})

                    # Projekt-Freigaben (nur fuer Projekte des Owners)
                    share_rows = payload.get("project_shares", [])
                    if share_rows:
                        shares_by_project: dict[int, list[dict[str, Any]]] = {}
                        for row in share_rows:
                            try:
                                project_id = int(row.get("project_id"))
                            except (TypeError, ValueError):
                                continue
                            shares_by_project.setdefault(project_id, []).append(row)

                        with get_connection() as conn:
                            for project_id, rows in shares_by_project.items():
                                owner_row = conn.execute(
                                    "SELECT owner_account FROM projects WHERE id = ?",
                                    (project_id,),
                                ).fetchone()
                                owner_account = str(owner_row["owner_account"] or "").strip().lower() if owner_row else ""
                                if owner_account and owner_account != principal_name:
                                    continue
                                if not owner_account:
                                    conn.execute(
                                        "UPDATE projects SET owner_account = ?, updated_at = ? WHERE id = ?",
                                        (principal_name, now_text(), project_id),
                                    )
                                conn.execute("DELETE FROM project_shares WHERE project_id = ?", (project_id,))
                                for row in rows:
                                    filtered = {k: v for k, v in row.items() if k in {"project_id", "account_name", "created_at", "id"}}
                                    filtered["project_id"] = project_id
                                    account_name = str(filtered.get("account_name", "")).strip().lower()
                                    if not account_name:
                                        continue
                                    created_at = str(filtered.get("created_at") or now_text())
                                    conn.execute(
                                        "INSERT OR IGNORE INTO project_shares (project_id, account_name, created_at) VALUES (?, ?, ?)",
                                        (project_id, account_name, created_at),
                                    )
                            conn.commit()
                    
                    self._send_json({"ok": True, "conflicts": conflicts})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json({"error": "Not Found"}, status=HTTPStatus.NOT_FOUND)
        finally:
            clear_current_principal()
    def do_PATCH(self) -> None:  # noqa: N802
        """Handle PATCH requests (same as POST for our purposes)."""
        self.do_POST()

    def do_DELETE(self) -> None:  # noqa: N802
        principal_for_context = self._authenticate()
        if principal_for_context is not None:
            set_current_principal(principal_for_context)
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if not self._enforce_rate_limit(path):
                return

            principal = self._require_auth_json()
            if principal is None:
                return
            if not self._require_write_json(principal):
                return

            project_id = self._path_id("/api/projects/", path)
            if project_id is not None:
                try:
                    delete_project(project_id)
                    self._send_json({"ok": True})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            task_id = self._path_id("/api/tasks/", path)
            if task_id is not None:
                try:
                    delete_task(task_id)
                    self._send_json({"ok": True})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            milestone_id = self._path_id("/api/milestones/", path)
            if milestone_id is not None:
                try:
                    delete_milestone(milestone_id)
                    self._send_json({"ok": True})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            template_id = self._path_id("/api/templates/", path)
            if template_id is not None:
                try:
                    delete_template(template_id)
                    self._send_json({"ok": True})
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json({"error": "Not Found"}, status=HTTPStatus.NOT_FOUND)
        finally:
            clear_current_principal()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Suppress default logging."""
        pass


def run_collab_server(
    host: str = "0.0.0.0",
    port: int = 8765,
    accounts_path: str | Path = DEFAULT_ACCOUNTS_PATH,
    legacy_api_key: str | None = None,
) -> int:
    """Run the collaboration server with security features."""
    generated_keys = ensure_api_keys(accounts_path)

    server = ThreadingHTTPServer((host, port), _CollabHandler)
    server.sessions = {}
    server.sessions_lock = threading.Lock()
    server.desktop_logins = {}
    server.desktop_logins_lock = threading.Lock()
    server.request_log = {}
    server.accounts_path = Path(accounts_path)
    server.legacy_api_key = legacy_api_key

    print("=" * 70)
    print("🔐 SICHERER PROJEKTMANAGER SERVER")
    print("=" * 70)
    print(f"✓ Läuft auf:     http://{host}:{port}")
    print(f"✓ Login unter:   http://{host}:{port}/login")
    print(f"✓ Accounts:      {accounts_path}")
    print("")
    print("Sicherheitsmerkmale aktiv:")
    print("  ✓ Login nur mit E-Mail + Passwort")
    print("  ✓ API-Key nur für Account-Erstellung")
    if legacy_api_key:
        print("  ✓ Zusätzlicher globaler API-Key für Account-Erstellung aktiviert")
    print("  ✓ Session Timeout (1 Stunde)")
    print("  ✓ Session Cookies (HttpOnly, SameSite)")
    print("  ✓ Brute-Force-Schutz (5 Versuche)")
    print("  ✓ XSS & CSRF Protection")
    print("  ✓ Audit Logging aller Zugriffe")

    if generated_keys:
        print("")
        print("Neu erzeugte API-Keys für bestehende Accounts:")
        for entry in generated_keys:
            print(f"  - {entry['email']}: {entry['api_key']}")
        print("Hinweis: Diese Keys werden nur einmal im Terminal angezeigt.")

    print("=" * 70)
    print("Zum Beenden: Ctrl+C\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✓ Server wird beendet...")
        server.shutdown()
        return 0

    return 0


def _latest_existing_file(paths: list[Path]) -> Path | None:
    existing_paths = [path for path in paths if path.is_file()]
    if not existing_paths:
        return None
    return max(existing_paths, key=lambda path: path.stat().st_mtime)


def _checksum_matches(exe_path: Path) -> bool:
    checksum_path = exe_path.with_name(f"{exe_path.name}.sha256")
    if not checksum_path.is_file():
        return False

    try:
        expected_digest = checksum_path.read_text(encoding="utf-8").split()[0].strip()
    except (OSError, IndexError):
        return False

    hasher = hashlib.sha256()
    try:
        with exe_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError:
        return False

    return hasher.hexdigest() == expected_digest


if __name__ == "__main__":
    raise SystemExit(run_collab_server())
