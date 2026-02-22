"""
Task Queue

Priority queue for managing tasks across projects.
Tasks are persisted to JSON and ordered by priority.

Usage:
    from core.task_queue import TaskQueue, Task

    queue = TaskQueue.load("tasks.json")
    queue.add(Task(project="backpack_hero", description="Add pause menu"))

    task = queue.pop_best()
    # ... execute task ...
    queue.complete(task.id)

    queue.save()
"""

import heapq
import json
import uuid
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
import logging

logger = logging.getLogger("studio.task_queue")


class TaskStatus(str, Enum):
    """Task status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskPriority(int, Enum):
    """Task priority (lower = higher priority)."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKLOG = 4


@dataclass
class Task:
    """A task to be executed on a project."""

    project: str
    description: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    parent_id: Optional[str] = None  # For subtasks

    def __post_init__(self):
        if isinstance(self.priority, int):
            self.priority = TaskPriority(self.priority)
        if isinstance(self.status, str):
            self.status = TaskStatus(self.status)

    def __lt__(self, other: "Task") -> bool:
        """Compare for heap ordering (lower priority value = higher priority)."""
        if self.priority != other.priority:
            return self.priority.value < other.priority.value
        # Same priority: older tasks first
        return self.created_at < other.created_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "project": self.project,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "parent_id": self.parent_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            project=data["project"],
            description=data["description"],
            priority=TaskPriority(data.get("priority", 2)),
            status=TaskStatus(data.get("status", "pending")),
            created_at=data.get("created_at", datetime.now().isoformat()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            error=data.get("error"),
            parent_id=data.get("parent_id")
        )


class TaskQueue:
    """
    Priority queue for tasks.
    Uses heapq internally, persists to JSON.
    Thread-safe for parallel worker access.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = path
        self._tasks: Dict[str, Task] = {}  # id -> Task
        self._heap: List[Task] = []  # Heap of pending tasks
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._locked_projects: Set[str] = set()  # Projects currently being worked on

    @classmethod
    def load(cls, path: str | Path) -> "TaskQueue":
        """Load queue from JSON file."""
        path = Path(path)
        queue = cls(path)

        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for task_data in data.get("tasks", []):
                    task = Task.from_dict(task_data)
                    queue._tasks[task.id] = task
                    if task.status == TaskStatus.PENDING:
                        heapq.heappush(queue._heap, task)

                logger.info(f"Loaded {len(queue._tasks)} tasks from {path}")
            except Exception as e:
                logger.error(f"Failed to load tasks: {e}")

        return queue

    def reload(self) -> None:
        """Reload queue from disk (picks up external changes)."""
        if not self.path or not self.path.exists():
            return

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            new_tasks = {}
            new_heap = []

            for task_data in data.get("tasks", []):
                task = Task.from_dict(task_data)
                new_tasks[task.id] = task
                if task.status == TaskStatus.PENDING:
                    heapq.heappush(new_heap, task)

            self._tasks = new_tasks
            self._heap = new_heap
            logger.info(f"Reloaded {len(self._tasks)} tasks")
        except Exception as e:
            logger.error(f"Failed to reload tasks: {e}")

    def save(self) -> None:
        """Save queue to JSON file (thread-safe)."""
        if not self.path:
            logger.warning("No path set, cannot save")
            return

        with self._lock:
            data = {
                "tasks": [t.to_dict() for t in self._tasks.values()],
                "updated_at": datetime.now().isoformat()
            }

            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

            logger.info(f"Saved {len(self._tasks)} tasks to {self.path}")

    def add(self, task: Task) -> Task:
        """Add task to queue (thread-safe)."""
        with self._lock:
            self._tasks[task.id] = task
            if task.status == TaskStatus.PENDING:
                heapq.heappush(self._heap, task)

            logger.info(f"Added task {task.id}: {task.description[:50]}")
            return task

    def add_many(self, tasks: List[Task]) -> List[Task]:
        """Add multiple tasks."""
        for task in tasks:
            self.add(task)
        return tasks

    def get(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def pop_best(self, exclude_projects: Optional[Set[str]] = None) -> Optional[Task]:
        """
        Get highest priority pending task.
        Marks it as in_progress.

        Args:
            exclude_projects: Projects to skip (for parallel execution)
        """
        with self._lock:
            # Clean up heap (remove non-pending tasks)
            while self._heap:
                task = self._heap[0]
                if task.status == TaskStatus.PENDING:
                    break
                heapq.heappop(self._heap)

            if not self._heap:
                return None

            # Find best task not in excluded projects
            if exclude_projects:
                # Need to scan for non-excluded task
                temp = []
                result = None

                while self._heap:
                    task = heapq.heappop(self._heap)
                    if task.status != TaskStatus.PENDING:
                        continue
                    if task.project not in exclude_projects:
                        result = task
                        break
                    temp.append(task)

                # Put skipped tasks back
                for t in temp:
                    heapq.heappush(self._heap, t)

                if not result:
                    return None

                task = result
            else:
                task = heapq.heappop(self._heap)

            task.status = TaskStatus.IN_PROGRESS
            task.started_at = datetime.now().isoformat()

            logger.info(f"Popped task {task.id}: {task.description[:50]}")
            return task

    def pop_for_parallel(self) -> Optional[Task]:
        """
        Get task for parallel execution.
        Automatically excludes projects that are currently locked.
        Locks the project of the returned task.
        """
        with self._lock:
            task = self.pop_best(exclude_projects=self._locked_projects)
            if task:
                self._locked_projects.add(task.project)
            return task

    def release_project(self, project: str) -> None:
        """Release project lock after task completion."""
        with self._lock:
            self._locked_projects.discard(project)

    def complete(self, task_id: str, result: Optional[str] = None) -> Optional[Task]:
        """Mark task as completed (thread-safe)."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                logger.warning(f"Task not found: {task_id}")
                return None

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now().isoformat()
            task.result = result

            # Release project lock
            self._locked_projects.discard(task.project)

            logger.info(f"Completed task {task_id}")
            return task

    def fail(self, task_id: str, error: str) -> Optional[Task]:
        """Mark task as failed (thread-safe)."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now().isoformat()
            task.error = error

            # Release project lock
            self._locked_projects.discard(task.project)

            logger.warning(f"Failed task {task_id}: {error}")
            return task

    def requeue(self, task_id: str) -> Optional[Task]:
        """Put failed/blocked task back in queue."""
        task = self._tasks.get(task_id)
        if not task:
            return None

        task.status = TaskStatus.PENDING
        task.started_at = None
        task.error = None
        heapq.heappush(self._heap, task)

        return task

    def pending(self, project: Optional[str] = None) -> List[Task]:
        """Get all pending tasks, optionally filtered by project."""
        tasks = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
        if project:
            tasks = [t for t in tasks if t.project == project]
        return sorted(tasks)

    def all_tasks(self, project: Optional[str] = None) -> List[Task]:
        """Get all tasks, optionally filtered by project."""
        tasks = list(self._tasks.values())
        if project:
            tasks = [t for t in tasks if t.project == project]
        return tasks

    def stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        stats = {status.value: 0 for status in TaskStatus}
        for task in self._tasks.values():
            stats[task.status.value] += 1
        stats["total"] = len(self._tasks)
        return stats

    def clear_completed(self, before_days: int = 7) -> int:
        """Remove completed tasks older than N days."""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=before_days)
        removed = 0

        for task_id in list(self._tasks.keys()):
            task = self._tasks[task_id]
            if task.status == TaskStatus.COMPLETED and task.completed_at:
                completed = datetime.fromisoformat(task.completed_at)
                if completed < cutoff:
                    del self._tasks[task_id]
                    removed += 1

        return removed


# Module test
if __name__ == "__main__":
    # Test basic operations
    queue = TaskQueue()

    # Add tasks
    queue.add(Task(project="test", description="High priority", priority=TaskPriority.HIGH))
    queue.add(Task(project="test", description="Normal priority"))
    queue.add(Task(project="test", description="Low priority", priority=TaskPriority.LOW))

    print("Stats:", queue.stats())

    # Pop in priority order
    while task := queue.pop_best():
        print(f"  {task.priority.name}: {task.description}")
        queue.complete(task.id)

    print("After completion:", queue.stats())
