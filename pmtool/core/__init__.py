"""Core package for the local project management tool."""

from __future__ import annotations

import sys

from . import legacy as _legacy
from .models import Principal, ProjectInput, RiskData, TaskFilter, TaskInput
from .reports import build_weekly_project_report_markdown, generate_weekly_project_report

# Explicitly import and re-export all functions for type-checker compatibility
from .legacy import (
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
    init_db,
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

# Update legacy module with report functions
_legacy.build_weekly_project_report_markdown = build_weekly_project_report_markdown
_legacy.generate_weekly_project_report = generate_weekly_project_report

# Export models
_legacy.ProjectInput = ProjectInput
_legacy.RiskData = RiskData
_legacy.TaskInput = TaskInput
_legacy.TaskFilter = TaskFilter
_legacy.Principal = Principal

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

sys.modules[__name__] = _legacy
