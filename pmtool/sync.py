"""Synchronization between local app and collaboration server."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from pmtool.core import (
    get_connection,
    init_db,
    list_milestones,
    list_projects,
    list_tasks,
    list_templates,
    risk_rows_from_json,
    table_columns,
    update_milestone,
    update_project,
    update_task,
    update_template,
)


def _filter_row_columns(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        columns = table_columns(conn, table_name)
    return {key: value for key, value in row.items() if key in columns}


def _upsert_row(table_name: str, row: dict[str, Any]) -> None:
    init_db()
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


def _replace_project_shares(rows: list[dict[str, Any]]) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM project_shares")
        for row in rows:
            filtered = _filter_row_columns("project_shares", row)
            if not filtered:
                continue
            columns = list(filtered.keys())
            placeholders = ", ".join(["?"] * len(columns))
            column_sql = ", ".join(columns)
            values = [filtered[column] for column in columns]
            conn.execute(
                f"INSERT OR REPLACE INTO project_shares ({column_sql}) VALUES ({placeholders})",
                values,
            )
        conn.commit()


def _collect_owned_project_share_rows(account_email: str | None) -> list[dict[str, Any]]:
    if not account_email:
        return []
    owner = str(account_email).strip().lower()
    if not owner:
        return []
    init_db()
    with get_connection() as conn:
        project_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM projects WHERE LOWER(owner_account) = ? OR owner_account = ''",
                (owner,),
            ).fetchall()
        ]
        if not project_ids:
            return []
        placeholders = ", ".join(["?"] * len(project_ids))
        rows = conn.execute(
            f"SELECT * FROM project_shares WHERE project_id IN ({placeholders})",
            project_ids,
        ).fetchall()
        return [dict(row) for row in rows]


def _collect_owned_project_ids(account_email: str | None) -> list[int]:
    if not account_email:
        return []
    owner = str(account_email).strip().lower()
    if not owner:
        return []
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM projects WHERE LOWER(owner_account) = ?",
            (owner,),
        ).fetchall()
        return [int(row["id"]) for row in rows]


class SyncClient:
    """Client for synchronizing with a remote Projektmanager server."""

    def __init__(self, server_url: str) -> None:
        """Initialize sync client with server URL.
        
        Args:
            server_url: Base URL of the server (e.g., 'https://100.80.250.84')
        """
        self.server_url = server_url.rstrip("/")
        self.auth_cookie: str | None = None

    def set_auth_cookie(self, cookie: str) -> None:
        """Set authentication cookie for API requests.
        
        Args:
            cookie: Session cookie value (typically PMTOOL_SESSION)
        """
        self.auth_cookie = cookie

    def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        """Make HTTP request to server.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., '/api/sync/projects')
            data: JSON data for POST/PUT requests
            expect_json: Whether to parse response as JSON
            
        Returns:
            Parsed JSON response or raw response
            
        Raises:
            URLError: If connection fails
            ValueError: If request returns error status
        """
        url = urljoin(self.server_url, path)
        
        if data is not None:
            data = json.dumps(data).encode('utf-8')
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        if self.auth_cookie:
            headers['Cookie'] = f'PMTOOL_SESSION={self.auth_cookie}'
        
        request = Request(url, data=data, headers=headers, method=method)
        
        try:
            with urlopen(request, timeout=10) as response:
                if expect_json:
                    return json.loads(response.read().decode('utf-8'))
                return response.read()
        except URLError as e:
            raise URLError(f"Server connection failed ({url}): {e}")

    def fetch_projects(self, since: str | None = None) -> list[dict[str, Any]]:
        """Fetch projects from server.
        
        Args:
            since: ISO timestamp to fetch only changes since this time
            
        Returns:
            List of project dictionaries
        """
        path = "/api/sync/projects"
        if since:
            path += f"?since={since}"
        return self._request("GET", path)

    def fetch_tasks(
        self,
        since: str | None = None,
        project_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch tasks from server.
        
        Args:
            since: ISO timestamp to fetch only changes since this time
            project_id: Optional project filter
            
        Returns:
            List of task dictionaries
        """
        path = "/api/sync/tasks"
        params = []
        if since:
            params.append(f"since={since}")
        if project_id is not None:
            params.append(f"project_id={project_id}")
        if params:
            path += "?" + "&".join(params)
        return self._request("GET", path)

    def fetch_milestones(
        self,
        since: str | None = None,
        project_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch milestones from server.
        
        Args:
            since: ISO timestamp to fetch only changes since this time
            project_id: Optional project filter
            
        Returns:
            List of milestone dictionaries
        """
        path = "/api/sync/milestones"
        params = []
        if since:
            params.append(f"since={since}")
        if project_id is not None:
            params.append(f"project_id={project_id}")
        if params:
            path += "?" + "&".join(params)
        return self._request("GET", path)

    def fetch_templates(self, since: str | None = None) -> list[dict[str, Any]]:
        """Fetch templates from server.
        
        Args:
            since: ISO timestamp to fetch only changes since this time
            
        Returns:
            List of template dictionaries
        """
        path = "/api/sync/templates"
        if since:
            path += f"?since={since}"
        return self._request("GET", path)

    def fetch_project_shares(self, since: str | None = None) -> list[dict[str, Any]]:
        path = "/api/sync/project-shares"
        if since:
            path += f"?since={since}"
        return self._request("GET", path)

    def upload_changes(
        self,
        projects: list[dict[str, Any]] | None = None,
        tasks: list[dict[str, Any]] | None = None,
        milestones: list[dict[str, Any]] | None = None,
        templates: list[dict[str, Any]] | None = None,
        project_shares: list[dict[str, Any]] | None = None,
        owned_project_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Upload local changes to server.
        
        Args:
            projects: List of modified projects
            tasks: List of modified tasks
            milestones: List of modified milestones
            templates: List of modified templates
            
        Returns:
            Response with 'ok' flag and list of conflicts
        """
        payload = {
            "projects": projects or [],
            "tasks": tasks or [],
            "milestones": milestones or [],
            "templates": templates or [],
            "project_shares": project_shares or [],
        }
        if owned_project_ids is not None:
            payload["owned_project_ids"] = owned_project_ids
        return self._request("POST", "/api/sync/upload", data=payload)


class SyncManager:
    """Manage synchronization between local and remote data."""

    def __init__(
        self,
        server_url: str,
        auth_cookie: str | None = None,
        account_email: str | None = None,
    ) -> None:
        """Initialize sync manager.
        
        Args:
            server_url: Base URL of collaboration server
            auth_cookie: Optional session cookie
            account_email: Optional email to invalidate cache when switching users
        """
        self.client = SyncClient(server_url)
        if auth_cookie:
            self.client.set_auth_cookie(auth_cookie)

        # Track last sync time
        self.sync_cache_file = Path.home() / ".pmtool_sync_cache.json"
        self._cache: dict[str, str | None] = self._load_cache()
        cached_server = str(self._cache.get("server_url") or "").strip()
        cached_account = str(self._cache.get("account_email") or "").strip().lower()
        current_account = str(account_email or "").strip().lower()
        if cached_server and cached_server != self.client.server_url:
            self._cache["last_sync"] = None
        if cached_account and current_account and cached_account != current_account:
            self._cache["last_sync"] = None
        self._cache["server_url"] = self.client.server_url
        if current_account:
            self._cache["account_email"] = current_account
        self._save_cache()

    def _load_cache(self) -> dict[str, str | None]:
        """Load sync cache from file."""
        if self.sync_cache_file.exists():
            try:
                return json.loads(self.sync_cache_file.read_text())
            except (json.JSONDecodeError, Exception):
                pass
        return {"last_sync": None, "server_url": None, "account_email": None}

    def _save_cache(self) -> None:
        """Save sync cache to file."""
        try:
            self.sync_cache_file.write_text(json.dumps(self._cache, indent=2))
        except Exception:
            pass

    def get_last_sync_time(self) -> str | None:
        """Get timestamp of last successful sync."""
        return self._cache.get("last_sync")

    def sync_from_server(self, force_full: bool = False) -> dict[str, Any]:
        """Download updates from server.
        
        Returns:
            Dictionary with downloaded data:
            {
                'projects': [...],
                'tasks': [...],
                'milestones': [...],
                'templates': [...]
            }
        """
        result = {
            "projects": [],
            "tasks": [],
            "milestones": [],
            "templates": [],
            "project_shares": [],
            "conflicts": [],
        }
        
        since = None if force_full else self.get_last_sync_time()
        
        try:
            # Fetch all data from server
            result["projects"] = self.client.fetch_projects(since=since)
            result["tasks"] = self.client.fetch_tasks(since=since)
            result["milestones"] = self.client.fetch_milestones(since=since)
            result["templates"] = self.client.fetch_templates(since=since)
            result["project_shares"] = self.client.fetch_project_shares(since=since)
            
            # Apply updates to local database
            for project in result["projects"]:
                try:
                    update_project(
                        project.get("id"),
                        name=project.get("name"),
                        team=project.get("team"),
                        description=project.get("description"),
                        status=project.get("status"),
                        goal=project.get("goal"),
                        milestone=project.get("milestone"),
                        risk=project.get("risk"),
                        risk_rows=risk_rows_from_json(project.get("risk_rows_json")),
                        risk_probability=project.get("risk_probability"),
                        risk_impact=project.get("risk_impact"),
                        risk_weight=project.get("risk_weight"),
                        risk_countermeasure=project.get("risk_countermeasure"),
                        next_review_date=project.get("next_review_date"),
                    )
                except ValueError as e:
                    if "existiert nicht" in str(e):
                        try:
                            _upsert_row("projects", project)
                            continue
                        except ValueError as upsert_error:
                            e = upsert_error
                    result["conflicts"].append({
                        "type": "project",
                        "id": project.get("id"),
                        "error": str(e),
                    })
            
            for task in result["tasks"]:
                try:
                    update_task(
                        task.get("id"),
                        title=task.get("title"),
                        details=task.get("details"),
                        status=task.get("status"),
                        priority=task.get("priority"),
                        due_date=task.get("due_date"),
                        blocked_reason=task.get("blocked_reason"),
                        risk=task.get("risk"),
                        risk_rows=risk_rows_from_json(task.get("risk_rows_json")),
                        risk_probability=task.get("risk_probability"),
                        risk_impact=task.get("risk_impact"),
                        risk_weight=task.get("risk_weight"),
                        risk_countermeasure=task.get("risk_countermeasure"),
                        project_id=task.get("project_id"),
                        context=task.get("context"),
                        energy_level=task.get("energy_level"),
                        estimate_minutes=task.get("estimate_minutes"),
                        tags=task.get("tags"),
                        recurrence_days=task.get("recurrence_days"),
                    )
                except ValueError as e:
                    if "existiert nicht" in str(e):
                        try:
                            _upsert_row("tasks", task)
                            continue
                        except ValueError as upsert_error:
                            e = upsert_error
                    result["conflicts"].append({
                        "type": "task",
                        "id": task.get("id"),
                        "error": str(e),
                    })
            
            for milestone in result["milestones"]:
                try:
                    update_milestone(
                        milestone.get("id"),
                        title=milestone.get("title"),
                        due_date=milestone.get("due_date"),
                        status=milestone.get("status"),
                        project_id=milestone.get("project_id"),
                    )
                except ValueError as e:
                    if "existiert nicht" in str(e):
                        try:
                            _upsert_row("project_milestones", milestone)
                            continue
                        except ValueError as upsert_error:
                            e = upsert_error
                    result["conflicts"].append({
                        "type": "milestone",
                        "id": milestone.get("id"),
                        "error": str(e),
                    })
            
            for template in result["templates"]:
                try:
                    update_template(
                        template.get("id"),
                        name=template.get("name"),
                        title=template.get("title"),
                        details=template.get("details"),
                        project_id=template.get("project_id"),
                        status=template.get("status"),
                        priority=template.get("priority"),
                        due_offset_days=template.get("due_offset_days"),
                        context=template.get("context"),
                        energy_level=template.get("energy_level"),
                        tags=template.get("tags"),
                        recurrence_days=template.get("recurrence_days"),
                    )
                except ValueError as e:
                    if "existiert nicht" in str(e):
                        try:
                            _upsert_row("task_templates", template)
                            continue
                        except ValueError as upsert_error:
                            e = upsert_error
                    result["conflicts"].append({
                        "type": "template",
                        "id": template.get("id"),
                        "error": str(e),
                    })

            if since is None:
                _replace_project_shares(result["project_shares"])
            else:
                for share_row in result["project_shares"]:
                    try:
                        _upsert_row("project_shares", share_row)
                    except ValueError as e:
                        result["conflicts"].append({
                            "type": "project_share",
                            "id": share_row.get("id"),
                            "error": str(e),
                        })
            
            # Update sync cache
            self._cache["last_sync"] = datetime.utcnow().isoformat()
            self._cache["server_url"] = self.client.server_url
            self._save_cache()
            
            result["status"] = "synced"
            
        except URLError as e:
            result["error"] = str(e)
            result["status"] = "offline"
        
        return result

    def sync_to_server(
        self,
        projects: list[dict[str, Any]] | None = None,
        tasks: list[dict[str, Any]] | None = None,
        milestones: list[dict[str, Any]] | None = None,
        templates: list[dict[str, Any]] | None = None,
        project_shares: list[dict[str, Any]] | None = None,
        owned_project_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Upload local changes to server.
        
        Args:
            projects: List of modified projects
            tasks: List of modified tasks
            milestones: List of modified milestones
            templates: List of modified templates
            
        Returns:
            Upload result with conflicts list
        """
        try:
            result = self.client.upload_changes(
                projects=projects,
                tasks=tasks,
                milestones=milestones,
                templates=templates,
                project_shares=project_shares,
                owned_project_ids=owned_project_ids,
            )
            
            # Update sync cache on success
            self._cache["last_sync"] = datetime.utcnow().isoformat()
            self._save_cache()
            
            return result
            
        except URLError as e:
            return {"error": str(e), "status": "offline"}

    def full_sync(self, force_full: bool = False) -> dict[str, Any]:
        """Perform full synchronization (download then upload).
        
        Returns:
            Sync result with status, downloaded data, and conflicts
        """
        account_email = self._cache.get("account_email")
        local_share_rows: list[dict[str, Any]] = []
        if force_full:
            local_share_rows = _collect_owned_project_share_rows(account_email)

        # Download from server first
        download_result = self.sync_from_server(force_full=force_full)
        
        if download_result.get("status") == "offline":
            return {
                "status": "offline",
                "error": download_result.get("error"),
            }
        
        if force_full and local_share_rows:
            for row in local_share_rows:
                try:
                    _upsert_row("project_shares", row)
                except ValueError:
                    pass

        # Prepare local data for upload (all items)
        projects = [dict(row) for row in list_projects()]
        tasks = [dict(row) for row in list_tasks(include_done=True)]
        milestones = [dict(row) for row in list_milestones()]
        templates = [dict(row) for row in list_templates()]
        project_shares = _collect_owned_project_share_rows(account_email)
        owned_project_ids = _collect_owned_project_ids(account_email) if (force_full and account_email) else None
        
        # Upload to server
        upload_result = self.sync_to_server(
            projects=projects,
            tasks=tasks,
            milestones=milestones,
            templates=templates,
            project_shares=project_shares,
            owned_project_ids=owned_project_ids,
        )
        
        return {
            "status": "synced",
            "downloaded": download_result,
            "uploaded": upload_result,
            "last_sync": self.get_last_sync_time(),
        }


class AutoSyncManager:
    """Manage automatic synchronization at regular intervals."""

    def __init__(
        self,
        sync_manager: SyncManager,
        interval_seconds: int = 300,
        enabled: bool = True,
        on_sync_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Initialize auto-sync manager.
        
        Args:
            sync_manager: SyncManager instance to use
            interval_seconds: Sync interval in seconds (default 300 = 5 minutes)
            enabled: Whether to start auto-sync immediately
            on_sync_callback: Optional callback function(result_dict) when sync completes
        """
        self.sync_manager = sync_manager
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self.on_sync_callback = on_sync_callback
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.last_sync_result: dict[str, Any] | None = None
        
        # Load config from file
        self._config_file = Path.home() / ".pmtool_autosync_config.json"
        self._load_config()
        
        if self.enabled:
            self.start()

    def _load_config(self) -> None:
        """Load auto-sync configuration from file."""
        if self._config_file.exists():
            try:
                config = json.loads(self._config_file.read_text())
                self.enabled = config.get("enabled", True)
                self.interval_seconds = config.get("interval_seconds", 300)
            except (json.JSONDecodeError, Exception):
                pass

    def _save_config(self) -> None:
        """Save auto-sync configuration to file."""
        try:
            config = {
                "enabled": self.enabled,
                "interval_seconds": self.interval_seconds,
            }
            self._config_file.write_text(json.dumps(config, indent=2))
        except Exception:
            pass

    def set_interval(self, seconds: int) -> None:
        """Set sync interval in seconds.
        
        Args:
            seconds: New interval (minimum 60 seconds, maximum 3600)
        """
        seconds = max(60, min(3600, seconds))  # Clamp between 60 and 3600
        with self._lock:
            self.interval_seconds = seconds
        self._save_config()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable auto-sync.
        
        Args:
            enabled: True to enable, False to disable
        """
        with self._lock:
            if enabled and not self.enabled:
                self.enabled = True
                self.start()
            elif not enabled and self.enabled:
                self.enabled = False
                self.stop()
        self._save_config()

    def start(self) -> None:
        """Start auto-sync background thread."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._sync_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop auto-sync background thread."""
        with self._lock:
            self._stop_event.set()
        
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _sync_loop(self) -> None:
        """Background loop for periodic synchronization."""
        while not self._stop_event.is_set():
            try:
                # Wait for interval (can be interrupted by stop event)
                if self._stop_event.wait(timeout=self.interval_seconds):
                    break
                
                # Perform sync
                with self._lock:
                    if not self.enabled:
                        continue
                    
                    try:
                        # Upload local changes to server
                        projects = [dict(row) for row in list_projects()]
                        tasks = [dict(row) for row in list_tasks(include_done=True)]
                        milestones = [dict(row) for row in list_milestones()]
                        templates = [dict(row) for row in list_templates()]
                        account_email = self.sync_manager._cache.get("account_email")
                        project_shares = _collect_owned_project_share_rows(account_email)
                        
                        result = self.sync_manager.sync_to_server(
                            projects=projects,
                            tasks=tasks,
                            milestones=milestones,
                            templates=templates,
                            project_shares=project_shares,
                        )
                        
                        self.last_sync_result = result
                        
                        # Call callback if provided
                        if self.on_sync_callback:
                            self.on_sync_callback(result)
                    
                    except Exception:
                        # Silently ignore errors in background sync
                        pass
            
            except Exception:
                # Safety: never crash the background thread
                pass

    def get_status(self) -> dict[str, Any]:
        """Get current auto-sync status.
        
        Returns:
            Dictionary with enabled status, interval, and last result
        """
        with self._lock:
            return {
                "enabled": self.enabled,
                "interval_seconds": self.interval_seconds,
                "last_sync": self.last_sync_result,
                "last_sync_time": self.sync_manager.get_last_sync_time(),
            }

