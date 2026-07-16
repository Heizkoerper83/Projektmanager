"""Core package for the local project management tool."""

from __future__ import annotations


from . import service as _service
from .models import Principal, ProjectInput, RiskData, TaskFilter, TaskInput
from .reports import build_weekly_project_report_markdown, generate_weekly_project_report

# Explicitly import and re-export all functions for type-checker compatibility
from .service import (
    add_milestone,
    add_project,
    add_task,
    add_task_note,
    add_template,
    complete_task,
    create_task_from_template,
    current_principal,
    delete_milestone,
    delete_project,
    delete_task,
    delete_template,
    export_csv,
    export_json,
    get_task,
    import_csv,
    import_json,
    init_db as _service_init_db,
    list_milestones,
    list_project_shares,
    list_projects,
    list_task_history,
    list_task_notes,
    list_tasks,
    list_templates,
    set_current_principal,
    share_project,
    unshare_project,
    update_milestone,
    update_project,
    update_task,
    update_template,
)

DB_PATH = _service.DB_PATH

def init_db() -> None:
    """Initialize the configured server database (compatibility wrapper)."""
    _service.DB_PATH = DB_PATH
    _service_init_db()

def __getattr__(name: str):
    return getattr(_service, name)

# Expose report helpers on the service module with report functions
_service.build_weekly_project_report_markdown = build_weekly_project_report_markdown
_service.generate_weekly_project_report = generate_weekly_project_report

# Export models
_service.ProjectInput = ProjectInput
_service.RiskData = RiskData
_service.TaskInput = TaskInput
_service.TaskFilter = TaskFilter
_service.Principal = Principal

__all__ = [
    # Models
    "Principal",
    "ProjectInput",
    "RiskData",
    "TaskFilter",
    "TaskInput",
    # Functions
    "add_milestone",
    "add_project",
    "add_task",
    "add_task_note",
    "add_template",
    "build_weekly_project_report_markdown",
    "complete_task",
    "create_task_from_template",
    "current_principal",
    "delete_milestone",
    "delete_project",
    "delete_task",
    "delete_template",
    "export_csv",
    "export_json",
    "generate_weekly_project_report",
    "get_task",
    "import_csv",
    "import_json",
    "init_db",
    "list_milestones",
    "list_project_shares",
    "list_projects",
    "list_task_history",
    "list_task_notes",
    "list_tasks",
    "list_templates",
    "set_current_principal",
    "share_project",
    "unshare_project",
    "update_milestone",
    "update_project",
    "update_task",
    "update_template",
]

