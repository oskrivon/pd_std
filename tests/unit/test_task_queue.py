"""
Unit Tests for TaskQueue

Tests cover:
- Basic CRUD operations
- Priority ordering
- Thread safety
- Persistence (save/load)
- Project locking for parallel execution
"""

import json
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.task_queue import TaskQueue, Task, TaskPriority, TaskStatus


class TestTask:
    """Tests for Task dataclass."""

    def test_task_creation_defaults(self):
        """Task should have sensible defaults."""
        task = Task(project="test", description="Test task")

        assert task.project == "test"
        assert task.description == "Test task"
        assert task.priority == TaskPriority.NORMAL
        assert task.status == TaskStatus.PENDING
        assert task.id is not None
        assert len(task.id) == 8

    def test_task_priority_ordering(self):
        """Higher priority tasks should sort before lower priority."""
        critical = Task(project="a", description="Critical", priority=TaskPriority.CRITICAL)
        high = Task(project="a", description="High", priority=TaskPriority.HIGH)
        normal = Task(project="a", description="Normal", priority=TaskPriority.NORMAL)
        low = Task(project="a", description="Low", priority=TaskPriority.LOW)

        tasks = [low, normal, critical, high]
        sorted_tasks = sorted(tasks)

        assert sorted_tasks[0].priority == TaskPriority.CRITICAL
        assert sorted_tasks[1].priority == TaskPriority.HIGH
        assert sorted_tasks[2].priority == TaskPriority.NORMAL
        assert sorted_tasks[3].priority == TaskPriority.LOW

    def test_task_serialization_roundtrip(self):
        """Task should serialize and deserialize correctly."""
        original = Task(
            project="test",
            description="Test task",
            priority=TaskPriority.HIGH,
            parent_id="parent-123"
        )

        data = original.to_dict()
        restored = Task.from_dict(data)

        assert restored.id == original.id
        assert restored.project == original.project
        assert restored.description == original.description
        assert restored.priority == original.priority
        assert restored.parent_id == original.parent_id


class TestTaskQueueBasic:
    """Basic TaskQueue operations."""

    def test_add_and_get(self, empty_queue: TaskQueue):
        """Should add and retrieve tasks."""
        task = Task(project="test", description="Test task")
        empty_queue.add(task)

        retrieved = empty_queue.get(task.id)
        assert retrieved is not None
        assert retrieved.id == task.id
        assert retrieved.description == "Test task"

    def test_pop_best_returns_highest_priority(self, queue_with_tasks: TaskQueue):
        """pop_best should return highest priority task."""
        task = queue_with_tasks.pop_best()

        assert task is not None
        assert task.priority == TaskPriority.CRITICAL
        assert task.project == "proj_c"

    def test_pop_best_marks_in_progress(self, queue_with_tasks: TaskQueue):
        """pop_best should mark task as in_progress."""
        task = queue_with_tasks.pop_best()

        assert task.status == TaskStatus.IN_PROGRESS
        assert task.started_at is not None

    def test_pop_best_empty_queue(self, empty_queue: TaskQueue):
        """pop_best on empty queue should return None."""
        assert empty_queue.pop_best() is None

    def test_complete_task(self, queue_with_tasks: TaskQueue):
        """complete should mark task as completed."""
        task = queue_with_tasks.pop_best()
        queue_with_tasks.complete(task.id, "Done!")

        completed = queue_with_tasks.get(task.id)
        assert completed.status == TaskStatus.COMPLETED
        assert completed.result == "Done!"
        assert completed.completed_at is not None

    def test_fail_task(self, queue_with_tasks: TaskQueue):
        """fail should mark task as failed with error."""
        task = queue_with_tasks.pop_best()
        queue_with_tasks.fail(task.id, "Something went wrong")

        failed = queue_with_tasks.get(task.id)
        assert failed.status == TaskStatus.FAILED
        assert failed.error == "Something went wrong"

    def test_requeue_failed_task(self, queue_with_tasks: TaskQueue):
        """requeue should put failed task back in queue."""
        task = queue_with_tasks.pop_best()
        queue_with_tasks.fail(task.id, "Error")
        queue_with_tasks.requeue(task.id)

        requeued = queue_with_tasks.get(task.id)
        assert requeued.status == TaskStatus.PENDING
        assert requeued.error is None

    def test_stats(self, queue_with_tasks: TaskQueue):
        """stats should return correct counts."""
        stats = queue_with_tasks.stats()

        assert stats["pending"] == 4
        assert stats["in_progress"] == 0
        assert stats["completed"] == 0
        assert stats["total"] == 4


class TestTaskQueuePersistence:
    """TaskQueue save/load operations."""

    def test_save_and_load(self, temp_dir: Path):
        """Queue should persist and restore correctly."""
        path = temp_dir / "tasks.json"

        # Create and save
        queue1 = TaskQueue(path)
        queue1.add(Task(project="a", description="Task 1"))
        queue1.add(Task(project="b", description="Task 2", priority=TaskPriority.HIGH))
        queue1.save()

        # Load in new instance
        queue2 = TaskQueue.load(path)

        assert queue2.stats()["total"] == 2
        assert queue2.stats()["pending"] == 2

    def test_reload_picks_up_changes(self, temp_dir: Path):
        """reload should pick up external changes."""
        path = temp_dir / "tasks.json"

        queue = TaskQueue(path)
        queue.add(Task(project="a", description="Task 1"))
        queue.save()

        # Simulate external modification
        data = json.loads(path.read_text(encoding="utf-8"))
        data["tasks"].append({
            "id": "external-1",
            "project": "b",
            "description": "External task",
            "priority": 2,
            "status": "pending",
            "created_at": "2025-01-01T00:00:00"
        })
        path.write_text(json.dumps(data), encoding="utf-8")

        queue.reload()
        assert queue.stats()["total"] == 2


class TestTaskQueueParallel:
    """Thread safety and parallel execution."""

    def test_pop_for_parallel_locks_project(self, queue_with_tasks: TaskQueue):
        """pop_for_parallel should lock the project."""
        task = queue_with_tasks.pop_for_parallel()

        assert task is not None
        assert task.project in queue_with_tasks._locked_projects

    def test_pop_for_parallel_skips_locked_projects(self, queue_with_tasks: TaskQueue):
        """pop_for_parallel should skip locked projects."""
        # Pop first task (proj_c - critical)
        task1 = queue_with_tasks.pop_for_parallel()
        assert task1.project == "proj_c"

        # Pop second task (should skip proj_c, get proj_a - high)
        task2 = queue_with_tasks.pop_for_parallel()
        assert task2.project == "proj_a"
        assert task2.priority == TaskPriority.HIGH

        # Pop third (should skip proj_c and proj_a)
        task3 = queue_with_tasks.pop_for_parallel()
        assert task3.project == "proj_b"

    def test_complete_releases_project_lock(self, queue_with_tasks: TaskQueue):
        """complete should release the project lock."""
        task = queue_with_tasks.pop_for_parallel()
        project = task.project

        assert project in queue_with_tasks._locked_projects

        queue_with_tasks.complete(task.id)

        assert project not in queue_with_tasks._locked_projects

    def test_fail_releases_project_lock(self, queue_with_tasks: TaskQueue):
        """fail should release the project lock."""
        task = queue_with_tasks.pop_for_parallel()
        project = task.project

        queue_with_tasks.fail(task.id, "Error")

        assert project not in queue_with_tasks._locked_projects

    def test_thread_safety_concurrent_adds(self, empty_queue: TaskQueue):
        """Multiple threads should safely add tasks."""
        n_threads = 10
        n_tasks_per_thread = 20

        def add_tasks(thread_id: int):
            for i in range(n_tasks_per_thread):
                empty_queue.add(Task(
                    project=f"proj_{thread_id}",
                    description=f"Task {thread_id}-{i}"
                ))

        threads = [
            threading.Thread(target=add_tasks, args=(i,))
            for i in range(n_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert empty_queue.stats()["total"] == n_threads * n_tasks_per_thread

    def test_thread_safety_concurrent_pop(self, temp_dir: Path):
        """Multiple threads should safely pop tasks without duplicates."""
        queue = TaskQueue(temp_dir / "tasks.json")

        # Add many tasks
        for i in range(100):
            queue.add(Task(project=f"proj_{i % 10}", description=f"Task {i}"))

        popped_ids = []
        lock = threading.Lock()

        def pop_tasks():
            while True:
                task = queue.pop_for_parallel()
                if task is None:
                    break
                with lock:
                    popped_ids.append(task.id)
                # Simulate work
                time.sleep(0.001)
                queue.complete(task.id)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(pop_tasks) for _ in range(5)]
            for f in futures:
                f.result()

        # No duplicates
        assert len(popped_ids) == len(set(popped_ids))
        # All tasks processed
        assert len(popped_ids) == 100


class TestTaskQueueFiltering:
    """Filtering and querying tasks."""

    def test_pending_all(self, queue_with_tasks: TaskQueue):
        """pending() should return all pending tasks."""
        pending = queue_with_tasks.pending()
        assert len(pending) == 4

    def test_pending_by_project(self, queue_with_tasks: TaskQueue):
        """pending(project) should filter by project."""
        pending = queue_with_tasks.pending(project="proj_a")
        assert len(pending) == 2
        assert all(t.project == "proj_a" for t in pending)

    def test_all_tasks(self, queue_with_tasks: TaskQueue):
        """all_tasks() should return all tasks regardless of status."""
        queue_with_tasks.pop_best()  # Mark one as in_progress

        all_tasks = queue_with_tasks.all_tasks()
        assert len(all_tasks) == 4

    def test_clear_completed(self, queue_with_tasks: TaskQueue):
        """clear_completed should remove old completed tasks."""
        # Complete some tasks
        for _ in range(2):
            task = queue_with_tasks.pop_best()
            queue_with_tasks.complete(task.id)

        # With before_days=7, recently completed tasks should NOT be removed
        removed = queue_with_tasks.clear_completed(before_days=7)
        assert removed == 0  # None old enough (completed just now)

        # All completed tasks should still be there
        completed = [t for t in queue_with_tasks.all_tasks() if t.status.value == "completed"]
        assert len(completed) == 2
