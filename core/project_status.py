"""
Project Status

Inter-project communication via STATUS.json files.
Each project maintains its own status file that other projects can read.

Usage:
    from core.project_status import ProjectStatus

    status = ProjectStatus.load("./workspace/hamster")
    status.set_working("Adding new feature")
    status.save()

    # Other project can read:
    other = ProjectStatus.load("./workspace/backpack_hero")
    if other.state == "blocked":
        print(f"Blocked by: {other.blocked_by}")
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger("studio.project_status")


class ProjectState(str, Enum):
    """Project state."""
    IDLE = "idle"           # No active work
    WORKING = "working"     # Task in progress
    BLOCKED = "blocked"     # Waiting on something
    ERROR = "error"         # Last task failed
    READY = "ready"         # Ready for next task


@dataclass
class ProjectStatus:
    """Status of a project for inter-project communication."""

    project: str
    state: ProjectState = ProjectState.IDLE
    current_task: Optional[str] = None
    last_task: Optional[str] = None
    last_task_status: Optional[str] = None  # completed/failed
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    blocked_by: Optional[str] = None  # Project name or resource
    error_message: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0

    # Path to status file
    _path: Optional[Path] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "project": self.project,
            "state": self.state.value,
            "current_task": self.current_task,
            "last_task": self.last_task,
            "last_task_status": self.last_task_status,
            "last_updated": self.last_updated,
            "blocked_by": self.blocked_by,
            "error_message": self.error_message,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], path: Optional[Path] = None) -> "ProjectStatus":
        """Create from dictionary."""
        return cls(
            project=data.get("project", "unknown"),
            state=ProjectState(data.get("state", "idle")),
            current_task=data.get("current_task"),
            last_task=data.get("last_task"),
            last_task_status=data.get("last_task_status"),
            last_updated=data.get("last_updated", datetime.now().isoformat()),
            blocked_by=data.get("blocked_by"),
            error_message=data.get("error_message"),
            tasks_completed=data.get("tasks_completed", 0),
            tasks_failed=data.get("tasks_failed", 0),
            _path=path
        )

    @classmethod
    def load(cls, project_path: str | Path) -> "ProjectStatus":
        """Load status from project directory."""
        path = Path(project_path)
        status_file = path / "STATUS.json"

        if status_file.exists():
            try:
                data = json.loads(status_file.read_text(encoding="utf-8"))
                status = cls.from_dict(data, status_file)
                return status
            except Exception as e:
                logger.warning(f"Failed to load STATUS.json: {e}")

        # Return default status
        return cls(
            project=path.name,
            _path=status_file
        )

    def save(self) -> None:
        """Save status to STATUS.json."""
        if not self._path:
            logger.warning("No path set, cannot save status")
            return

        self.last_updated = datetime.now().isoformat()

        self._path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        logger.debug(f"Saved status for {self.project}")

    # State transitions

    def set_working(self, task: str) -> None:
        """Mark project as working on a task."""
        self.state = ProjectState.WORKING
        self.current_task = task
        self.blocked_by = None
        self.error_message = None

    def set_completed(self, task: str) -> None:
        """Mark current task as completed."""
        self.state = ProjectState.READY
        self.last_task = task
        self.last_task_status = "completed"
        self.current_task = None
        self.tasks_completed += 1

    def set_failed(self, task: str, error: str) -> None:
        """Mark current task as failed."""
        self.state = ProjectState.ERROR
        self.last_task = task
        self.last_task_status = "failed"
        self.current_task = None
        self.error_message = error
        self.tasks_failed += 1

    def set_blocked(self, blocked_by: str) -> None:
        """Mark project as blocked."""
        self.state = ProjectState.BLOCKED
        self.blocked_by = blocked_by

    def set_idle(self) -> None:
        """Mark project as idle."""
        self.state = ProjectState.IDLE
        self.current_task = None
        self.blocked_by = None


def load_all_statuses(workspace: str | Path) -> Dict[str, ProjectStatus]:
    """Load status from all projects in workspace."""
    workspace = Path(workspace)
    statuses = {}

    for project_dir in workspace.iterdir():
        if not project_dir.is_dir():
            continue
        if project_dir.name.startswith(".") or project_dir.name == "studio":
            continue

        status = ProjectStatus.load(project_dir)
        statuses[status.project] = status

    return statuses


def print_all_statuses(workspace: str | Path) -> str:
    """Get formatted status report for all projects."""
    statuses = load_all_statuses(workspace)

    lines = ["Project Statuses:", ""]

    for name, status in sorted(statuses.items()):
        state_icon = {
            ProjectState.IDLE: "-",
            ProjectState.WORKING: "*",
            ProjectState.BLOCKED: "!",
            ProjectState.ERROR: "X",
            ProjectState.READY: "+"
        }.get(status.state, "?")

        line = f"  {state_icon} {name:<20} [{status.state.value}]"

        if status.current_task:
            line += f" → {status.current_task[:30]}"
        elif status.last_task:
            line += f" (last: {status.last_task[:25]})"

        if status.blocked_by:
            line += f" BLOCKED BY: {status.blocked_by}"

        if status.error_message:
            line += f" ERROR: {status.error_message[:30]}"

        lines.append(line)

    lines.append("")
    lines.append(f"Total: {len(statuses)} projects")

    return "\n".join(lines)
