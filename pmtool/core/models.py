"""Data models for project management using dataclasses.

These models simplify function signatures by grouping related parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class RiskData:
    """Risk data for tasks and projects."""
    description: str = ""
    rows: Sequence[dict[str, Any]] | None = None
    probability: int = 3
    impact: int = 3
    weight: int | None = None
    countermeasure: str = ""


@dataclass
class TaskInput:
    """Input data for creating or updating a task.
    
    This replaces the 18+ parameters of add_task/update_task with a single
    structured object, making the API cleaner and more maintainable.
    """
    title: str
    project_id: int | None = None
    details: str = ""
    status: str = "open"
    priority: int = 3
    due_date: str | None = None
    blocked_reason: str = ""
    risk: RiskData | None = None
    context: str = ""
    energy_level: str = "medium"
    estimate_minutes: int = 0
    tags: str | Sequence[str] | None = None
    recurrence_days: int | None = None
    
    def __post_init__(self) -> None:
        """Initialize RiskData if only risk description provided."""
        if isinstance(self.risk, str):
            # Handle case where risk is just a string
            self.risk = RiskData(description=self.risk)
        elif self.risk is None:
            self.risk = RiskData()


@dataclass
class ProjectInput:
    """Input data for creating or updating a project.
    
    This replaces the 13+ parameters of add_project/update_project with a single
    structured object, making the API cleaner and more maintainable.
    """
    name: str
    description: str = ""
    status: str = "active"
    team: str = ""
    goal: str = ""
    milestone: str = ""
    risk: RiskData | None = None
    next_review_date: str | None = None
    
    def __post_init__(self) -> None:
        """Initialize RiskData if needed."""
        if isinstance(self.risk, str):
            # Handle case where risk is just a string
            self.risk = RiskData(description=self.risk)
        elif self.risk is None:
            self.risk = RiskData()


@dataclass
class TaskFilter:
    """Filter criteria for listing tasks."""
    project_id: int | None = None
    status: str | Sequence[str] | None = None
    due_filter: str | None = None
    tags: str | Sequence[str] | None = None
    context: str | None = None
    energy_level: str | None = None
    blocked_only: bool = False
    include_done: bool = False
    search: str | None = None
    limit: int | None = None
    offset: int = 0


@dataclass
class Principal:
    """Authenticated user principal."""
    name: str
    role: str  # "reader", "editor" or "admin"
