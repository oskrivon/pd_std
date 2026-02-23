"""
SQLite-based Task Queue

Thread-safe task queue with proper transactions.
No more reload() needed - all operations go directly to DB.

Usage:
    from core.task_db import TaskDB, Task, TaskStatus

    db = TaskDB("studio/tasks.db")
    db.add(Task(project="hamster", description="Fix bug"))
    task = db.pop()  # Atomic pop with status update
"""

import sqlite3
import threading
import logging
from pathlib import Path
from typing import Optional, List, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger("studio.task_db")


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Task:
    """Task data structure."""
    project: str
    description: str
    id: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    parent_id: Optional[str] = None

    def __post_init__(self):
        if not self.id:
            import hashlib
            import time
            data = f"{self.project}{self.description}{time.time()}"
            self.id = hashlib.md5(data.encode()).hexdigest()[:8]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class TaskDB:
    """
    SQLite-based task queue.

    Thread-safe, transaction-based, no sync issues.
    """

    def __init__(self, db_path: str | Path = "tasks.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Thread-local connections
        self._local = threading.local()

        # Initialize schema
        self._init_schema()

        logger.info(f"TaskDB initialized: {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=30000")
        return self._local.conn

    @contextmanager
    def _transaction(self):
        """Context manager for transactions."""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema(self):
        """Create tables if not exist."""
        with self._transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    project TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority INTEGER DEFAULT 2,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    result TEXT,
                    error TEXT,
                    parent_id TEXT,
                    FOREIGN KEY (parent_id) REFERENCES tasks(id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status
                ON tasks(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_project
                ON tasks(project)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_priority_status
                ON tasks(priority DESC, status, created_at)
            """)

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        """Convert DB row to Task object."""
        return Task(
            id=row["id"],
            project=row["project"],
            description=row["description"],
            priority=TaskPriority(row["priority"]),
            status=TaskStatus(row["status"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            result=row["result"],
            error=row["error"],
            parent_id=row["parent_id"]
        )

    # ==================== Core Operations ====================

    def add(self, task: Task) -> Task:
        """Add a task to the queue."""
        with self._transaction() as conn:
            conn.execute("""
                INSERT INTO tasks (id, project, description, priority, status,
                                   created_at, started_at, completed_at,
                                   result, error, parent_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.project, task.description,
                task.priority.value, task.status.value,
                task.created_at, task.started_at, task.completed_at,
                task.result, task.error, task.parent_id
            ))
        logger.info(f"Added task {task.id}: {task.description[:50]}")
        return task

    def pop(self, exclude_projects: Optional[Set[str]] = None) -> Optional[Task]:
        """
        Atomically pop the highest priority pending task.

        Args:
            exclude_projects: Projects to skip (for parallel execution)

        Returns:
            Task marked as in_progress, or None if no tasks available
        """
        with self._transaction() as conn:
            # Build query
            query = """
                SELECT * FROM tasks
                WHERE status = 'pending'
            """
            params = []

            if exclude_projects:
                placeholders = ",".join("?" * len(exclude_projects))
                query += f" AND project NOT IN ({placeholders})"
                params.extend(exclude_projects)

            query += " ORDER BY priority DESC, created_at ASC LIMIT 1"

            row = conn.execute(query, params).fetchone()
            if not row:
                return None

            # Atomically update status
            now = datetime.now().isoformat()
            conn.execute("""
                UPDATE tasks
                SET status = 'in_progress', started_at = ?
                WHERE id = ?
            """, (now, row["id"]))

            task = self._row_to_task(row)
            task.status = TaskStatus.IN_PROGRESS
            task.started_at = now

            logger.info(f"Popped task {task.id}: {task.description[:50]}")
            return task

    def complete(self, task_id: str, result: Optional[str] = None) -> bool:
        """Mark task as completed."""
        with self._transaction() as conn:
            now = datetime.now().isoformat()
            cursor = conn.execute("""
                UPDATE tasks
                SET status = 'completed', completed_at = ?, result = ?
                WHERE id = ?
            """, (now, result, task_id))

            if cursor.rowcount > 0:
                logger.info(f"Completed task {task_id}")
                return True
            return False

    def fail(self, task_id: str, error: str) -> bool:
        """Mark task as failed."""
        with self._transaction() as conn:
            now = datetime.now().isoformat()
            cursor = conn.execute("""
                UPDATE tasks
                SET status = 'failed', completed_at = ?, error = ?
                WHERE id = ?
            """, (now, error, task_id))

            if cursor.rowcount > 0:
                logger.warning(f"Failed task {task_id}: {error[:50]}")
                return True
            return False

    def remove(self, task_id: str) -> bool:
        """Remove task from queue."""
        with self._transaction() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if cursor.rowcount > 0:
                logger.info(f"Removed task {task_id}")
                return True
            return False

    def reset_stuck(self) -> int:
        """Reset IN_PROGRESS tasks to PENDING (for crash recovery)."""
        with self._transaction() as conn:
            cursor = conn.execute("""
                UPDATE tasks
                SET status = 'pending', started_at = NULL
                WHERE status = 'in_progress'
            """)
            count = cursor.rowcount
            if count > 0:
                logger.info(f"Reset {count} stuck IN_PROGRESS tasks to PENDING")
            return count

    # ==================== Query Operations ====================

    def get(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return self._row_to_task(row) if row else None

    def all_tasks(self) -> List[Task]:
        """Get all tasks."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def pending_tasks(self) -> List[Task]:
        """Get pending tasks."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY priority DESC, created_at"
        ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def tasks_by_project(self, project: str) -> List[Task]:
        """Get tasks for a specific project."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM tasks WHERE project = ? ORDER BY created_at DESC",
            (project,)
        ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def stats(self) -> dict:
        """Get queue statistics."""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked
            FROM tasks
        """).fetchone()

        return {
            "total": row["total"] or 0,
            "pending": row["pending"] or 0,
            "in_progress": row["in_progress"] or 0,
            "completed": row["completed"] or 0,
            "failed": row["failed"] or 0,
            "blocked": row["blocked"] or 0
        }

    # ==================== Migration ====================

    @classmethod
    def from_json(cls, json_path: Path, db_path: Path) -> "TaskDB":
        """
        Migrate from JSON-based TaskQueue to SQLite.

        Args:
            json_path: Path to tasks.json
            db_path: Path for new tasks.db

        Returns:
            New TaskDB instance with migrated data
        """
        import json

        db = cls(db_path)

        if not json_path.exists():
            logger.info("No JSON file to migrate")
            return db

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tasks = data.get("tasks", [])
        migrated = 0

        for t in tasks:
            try:
                task = Task(
                    id=t["id"],
                    project=t["project"],
                    description=t["description"],
                    priority=TaskPriority(t.get("priority", 2)),
                    status=TaskStatus(t.get("status", "pending")),
                    created_at=t.get("created_at", ""),
                    started_at=t.get("started_at"),
                    completed_at=t.get("completed_at"),
                    result=t.get("result"),
                    error=t.get("error"),
                    parent_id=t.get("parent_id")
                )
                db.add(task)
                migrated += 1
            except Exception as e:
                logger.warning(f"Failed to migrate task {t.get('id')}: {e}")

        logger.info(f"Migrated {migrated} tasks from JSON to SQLite")
        return db


# Singleton instance for shared access
_default_db: Optional[TaskDB] = None
_db_lock = threading.Lock()


def get_task_db(db_path: Optional[Path] = None) -> TaskDB:
    """
    Get shared TaskDB instance.

    This ensures all components use the same DB connection pool.
    """
    global _default_db

    with _db_lock:
        if _default_db is None:
            path = db_path or Path("studio/tasks.db")
            _default_db = TaskDB(path)
        return _default_db


def reset_task_db():
    """Reset shared instance (for testing)."""
    global _default_db
    with _db_lock:
        _default_db = None
