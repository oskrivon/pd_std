"""
Unit Tests for ProjectStatus

Tests cover:
- State transitions
- Persistence (save/load)
- Multiple project status loading
"""

import json
from pathlib import Path

import pytest

from core.project_status import ProjectStatus, ProjectState, load_all_statuses


class TestProjectStatus:
    """Tests for ProjectStatus class."""

    def test_default_state(self, project_status: ProjectStatus):
        """New project should have idle state."""
        assert project_status.state == ProjectState.IDLE
        assert project_status.current_task is None
        assert project_status.tasks_completed == 0

    def test_set_working(self, project_status: ProjectStatus):
        """set_working should update state and current task."""
        project_status.set_working("Implementing feature X")

        assert project_status.state == ProjectState.WORKING
        assert project_status.current_task == "Implementing feature X"
        assert project_status.blocked_by is None

    def test_set_completed(self, project_status: ProjectStatus):
        """set_completed should update state and increment counter."""
        project_status.set_working("Task 1")
        project_status.set_completed("Task 1")

        assert project_status.state == ProjectState.READY
        assert project_status.current_task is None
        assert project_status.last_task == "Task 1"
        assert project_status.last_task_status == "completed"
        assert project_status.tasks_completed == 1

    def test_set_failed(self, project_status: ProjectStatus):
        """set_failed should update state and record error."""
        project_status.set_working("Task 1")
        project_status.set_failed("Task 1", "Connection timeout")

        assert project_status.state == ProjectState.ERROR
        assert project_status.current_task is None
        assert project_status.last_task == "Task 1"
        assert project_status.last_task_status == "failed"
        assert project_status.error_message == "Connection timeout"
        assert project_status.tasks_failed == 1

    def test_set_blocked(self, project_status: ProjectStatus):
        """set_blocked should record blocker."""
        project_status.set_working("Task 1")
        project_status.set_blocked("waiting for babylon")

        assert project_status.state == ProjectState.BLOCKED
        assert project_status.blocked_by == "waiting for babylon"

    def test_set_idle(self, project_status: ProjectStatus):
        """set_idle should clear working state."""
        project_status.set_working("Task 1")
        project_status.set_idle()

        assert project_status.state == ProjectState.IDLE
        assert project_status.current_task is None


class TestProjectStatusPersistence:
    """ProjectStatus save/load operations."""

    def test_save_creates_file(self, project_status: ProjectStatus):
        """save should create STATUS.json."""
        project_status.set_working("Test task")
        project_status.save()

        assert project_status._path.exists()

    def test_save_and_load_roundtrip(self, temp_dir: Path):
        """Status should persist and restore correctly."""
        project_dir = temp_dir / "test_project"
        project_dir.mkdir()

        # Create and save
        status1 = ProjectStatus.load(project_dir)
        status1.set_working("Important task")
        status1.set_completed("Important task")
        status1.save()

        # Load in new instance
        status2 = ProjectStatus.load(project_dir)

        assert status2.state == ProjectState.READY
        assert status2.last_task == "Important task"
        assert status2.tasks_completed == 1

    def test_load_nonexistent_returns_default(self, temp_dir: Path):
        """Loading from nonexistent file should return default status."""
        project_dir = temp_dir / "new_project"
        project_dir.mkdir()

        status = ProjectStatus.load(project_dir)

        assert status.state == ProjectState.IDLE
        assert status.project == "new_project"

    def test_load_corrupted_file_returns_default(self, temp_dir: Path):
        """Loading corrupted file should return default status."""
        project_dir = temp_dir / "corrupted_project"
        project_dir.mkdir()
        (project_dir / "STATUS.json").write_text("not valid json{{{", encoding="utf-8")

        status = ProjectStatus.load(project_dir)

        assert status.state == ProjectState.IDLE


class TestProjectStatusSerialization:
    """Serialization tests."""

    def test_to_dict(self, project_status: ProjectStatus):
        """to_dict should include all fields."""
        project_status.set_working("Task X")

        data = project_status.to_dict()

        assert data["project"] == project_status.project
        assert data["state"] == "working"
        assert data["current_task"] == "Task X"
        assert "last_updated" in data

    def test_from_dict(self):
        """from_dict should restore all fields."""
        data = {
            "project": "test",
            "state": "error",
            "current_task": None,
            "last_task": "Failed task",
            "last_task_status": "failed",
            "last_updated": "2025-01-01T00:00:00",
            "blocked_by": None,
            "error_message": "Something broke",
            "tasks_completed": 5,
            "tasks_failed": 2
        }

        status = ProjectStatus.from_dict(data)

        assert status.project == "test"
        assert status.state == ProjectState.ERROR
        assert status.last_task == "Failed task"
        assert status.error_message == "Something broke"
        assert status.tasks_completed == 5
        assert status.tasks_failed == 2


class TestLoadAllStatuses:
    """Tests for load_all_statuses function."""

    def test_load_multiple_projects(self, temp_dir: Path):
        """Should load status from all projects."""
        # Create projects
        for name in ["proj_a", "proj_b", "proj_c"]:
            proj_dir = temp_dir / name
            proj_dir.mkdir()

            status = ProjectStatus.load(proj_dir)
            status.set_working(f"Working on {name}")
            status.save()

        # Also create studio dir (should be ignored)
        (temp_dir / "studio").mkdir()

        statuses = load_all_statuses(temp_dir)

        assert len(statuses) == 3
        assert "proj_a" in statuses
        assert "proj_b" in statuses
        assert "proj_c" in statuses
        assert all(s.state == ProjectState.WORKING for s in statuses.values())

    def test_ignores_hidden_directories(self, temp_dir: Path):
        """Should ignore directories starting with dot."""
        (temp_dir / ".hidden").mkdir()
        (temp_dir / "visible").mkdir()

        statuses = load_all_statuses(temp_dir)

        assert ".hidden" not in statuses
        assert "visible" in statuses

    def test_ignores_studio_directory(self, temp_dir: Path):
        """Should ignore studio directory."""
        (temp_dir / "studio").mkdir()
        (temp_dir / "project").mkdir()

        statuses = load_all_statuses(temp_dir)

        assert "studio" not in statuses
        assert "project" in statuses


class TestStateTransitions:
    """Test valid state transitions."""

    def test_idle_to_working(self, project_status: ProjectStatus):
        """Can transition from idle to working."""
        assert project_status.state == ProjectState.IDLE
        project_status.set_working("Task")
        assert project_status.state == ProjectState.WORKING

    def test_working_to_completed(self, project_status: ProjectStatus):
        """Can transition from working to ready (completed)."""
        project_status.set_working("Task")
        project_status.set_completed("Task")
        assert project_status.state == ProjectState.READY

    def test_working_to_failed(self, project_status: ProjectStatus):
        """Can transition from working to error (failed)."""
        project_status.set_working("Task")
        project_status.set_failed("Task", "Error")
        assert project_status.state == ProjectState.ERROR

    def test_working_to_blocked(self, project_status: ProjectStatus):
        """Can transition from working to blocked."""
        project_status.set_working("Task")
        project_status.set_blocked("dependency")
        assert project_status.state == ProjectState.BLOCKED

    def test_error_to_working(self, project_status: ProjectStatus):
        """Can recover from error to working."""
        project_status.set_working("Task 1")
        project_status.set_failed("Task 1", "Error")
        project_status.set_working("Task 2")
        assert project_status.state == ProjectState.WORKING

    def test_blocked_clears_on_working(self, project_status: ProjectStatus):
        """Working should clear blocked_by."""
        project_status.set_blocked("something")
        project_status.set_working("New task")
        assert project_status.blocked_by is None
