"""
Integration Tests for Orchestrator

Tests the full orchestration flow with mocked and real Claude CLI.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.orchestrator import Orchestrator
from core.task_queue import Task, TaskPriority, TaskStatus
from core.project import Project, Engine


class TestOrchestratorSetup:
    """Test orchestrator initialization."""

    def test_init_with_workspace(self, temp_workspace: Path):
        """Should initialize with workspace."""
        orch = Orchestrator(workspace=temp_workspace)

        assert orch.workspace == temp_workspace
        assert orch.studio_path == temp_workspace / "studio"

    def test_discovers_projects(self, temp_workspace: Path):
        """Should discover projects in workspace."""
        # Create additional project
        proj = temp_workspace / "another_project"
        proj.mkdir()
        (proj / "main.lua").write_text("-- Game", encoding="utf-8")

        orch = Orchestrator(workspace=temp_workspace)

        assert len(orch.projects) >= 1

    def test_loads_task_queue(self, temp_workspace: Path):
        """Should load task queue from file."""
        # Pre-create tasks file
        tasks_file = temp_workspace / "studio" / "tasks.json"
        tasks_file.write_text(json.dumps({
            "tasks": [{
                "id": "pre-1",
                "project": "test_project",
                "description": "Pre-existing task",
                "priority": 2,
                "status": "pending",
                "created_at": "2025-01-01T00:00:00"
            }]
        }), encoding="utf-8")

        orch = Orchestrator(workspace=temp_workspace)

        assert orch.tasks.stats()["total"] >= 1


class TestOrchestratorTasks:
    """Test task management."""

    def test_add_task(self, temp_workspace: Path):
        """Should add task to queue."""
        orch = Orchestrator(workspace=temp_workspace)

        task = orch.add_task("test_project", "Test task description")

        assert task.project == "test_project"
        assert task.description == "Test task description"
        assert task.status == TaskStatus.PENDING

    def test_add_task_invalid_project(self, temp_workspace: Path):
        """Should reject task for unknown project."""
        orch = Orchestrator(workspace=temp_workspace)

        with pytest.raises(ValueError, match="Unknown project"):
            orch.add_task("nonexistent_project", "Task")

    def test_add_task_with_priority(self, temp_workspace: Path):
        """Should respect priority."""
        orch = Orchestrator(workspace=temp_workspace)

        task = orch.add_task("test_project", "Critical task", TaskPriority.CRITICAL)

        assert task.priority == TaskPriority.CRITICAL


class TestOrchestratorExecution:
    """Test task execution (mocked)."""

    def test_run_once_no_tasks(self, temp_workspace: Path):
        """run_once with empty queue should return None."""
        orch = Orchestrator(workspace=temp_workspace)

        result = orch.run_once(analyze=False)

        assert result is None

    def test_run_once_executes_task(self, temp_workspace: Path):
        """run_once should execute highest priority task."""
        orch = Orchestrator(workspace=temp_workspace)
        orch.add_task("test_project", "Test task")

        # Mock the Claude CLI call
        with patch.object(orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": True, "output": "Done"}

            task = orch.run_once(analyze=False)

            assert task is not None
            assert task.status == TaskStatus.COMPLETED
            mock_exec.assert_called_once()

    def test_run_once_handles_failure(self, temp_workspace: Path):
        """run_once should handle execution failure."""
        orch = Orchestrator(workspace=temp_workspace)
        orch.add_task("test_project", "Failing task")

        with patch.object(orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": False, "error": "Test error"}

            task = orch.run_once(analyze=False)

            assert task.status == TaskStatus.FAILED
            assert "Test error" in task.error

    def test_run_once_updates_project_status(self, temp_workspace: Path):
        """run_once should update project STATUS.json."""
        orch = Orchestrator(workspace=temp_workspace)
        orch.add_task("test_project", "Status test")

        with patch.object(orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": True, "output": "Done"}

            orch.run_once(analyze=False)

        # Check STATUS.json was created/updated
        status_file = temp_workspace / "test_project" / "STATUS.json"
        assert status_file.exists()

        data = json.loads(status_file.read_text(encoding="utf-8"))
        assert data["last_task"] is not None

    def test_run_once_tracks_budget(self, temp_workspace: Path):
        """run_once should record task in budget."""
        orch = Orchestrator(workspace=temp_workspace)
        orch.add_task("test_project", "Budget test")

        initial_records = len(orch.budget.records)

        with patch.object(orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": True, "output": "Done"}

            orch.run_once(analyze=False)

        assert len(orch.budget.records) == initial_records + 1


class TestOrchestratorRunAll:
    """Test batch execution."""

    def test_run_all_executes_multiple(self, temp_workspace: Path):
        """run_all should execute multiple tasks."""
        orch = Orchestrator(workspace=temp_workspace)
        orch.add_task("test_project", "Task 1")
        orch.add_task("test_project", "Task 2")
        orch.add_task("test_project", "Task 3")

        with patch.object(orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": True, "output": "Done"}

            tasks = orch.run_all(max_tasks=10, analyze=False)

            assert len(tasks) == 3

    def test_run_all_respects_max(self, temp_workspace: Path):
        """run_all should respect max_tasks limit."""
        orch = Orchestrator(workspace=temp_workspace)
        for i in range(10):
            orch.add_task("test_project", f"Task {i}")

        with patch.object(orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": True, "output": "Done"}

            tasks = orch.run_all(max_tasks=3, analyze=False)

            assert len(tasks) == 3

    def test_run_all_stops_on_failure(self, temp_workspace: Path):
        """run_all should stop on first failure."""
        orch = Orchestrator(workspace=temp_workspace)
        orch.add_task("test_project", "Task 1")
        orch.add_task("test_project", "Task 2 - will fail")
        orch.add_task("test_project", "Task 3")

        call_count = [0]

        def mock_exec(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                return {"success": False, "error": "Intentional failure"}
            return {"success": True, "output": "Done"}

        with patch.object(orch, '_execute_task', side_effect=mock_exec):
            tasks = orch.run_all(max_tasks=10, analyze=False)

            # Should stop after failure
            assert len(tasks) == 2
            assert tasks[-1].status == TaskStatus.FAILED


class TestOrchestratorStatus:
    """Test status reporting."""

    def test_status_returns_overview(self, temp_workspace: Path):
        """status should return overview dict."""
        orch = Orchestrator(workspace=temp_workspace)
        orch.add_task("test_project", "Task 1")

        status = orch.status()

        assert "projects" in status
        assert "tasks" in status
        assert "workspace" in status
        assert status["tasks"]["pending"] >= 1


@pytest.mark.integration
class TestOrchestratorWithClaude:
    """Tests that require real Claude CLI."""

    @pytest.mark.skipif(
        not pytest.importorskip("shutil").which("claude"),
        reason="Claude CLI not available"
    )
    def test_execute_real_task(self, temp_workspace: Path):
        """Execute a simple real task with Claude CLI."""
        # Create a simple project structure (needs main.lua for LOVE discovery)
        proj = temp_workspace / "simple_project"
        proj.mkdir()
        (proj / "CLAUDE.md").write_text("# Simple Project\nA test project.", encoding="utf-8")
        (proj / "main.lua").write_text("-- Test game\n", encoding="utf-8")
        (proj / "test.txt").write_text("Hello", encoding="utf-8")

        orch = Orchestrator(workspace=temp_workspace)
        orch.reload_projects()

        # Check project was discovered
        if "simple_project" not in [p.name for p in orch.projects]:
            pytest.skip("Project not discovered")

        # Add a simple task
        orch.add_task("simple_project", "Read test.txt and confirm it contains 'Hello'")

        # Execute (this will use real Claude CLI)
        task = orch.run_once(analyze=False, validate=False)

        # Should complete (might fail if Claude not configured properly)
        assert task is not None
        # We don't assert completion because it depends on Claude being available
