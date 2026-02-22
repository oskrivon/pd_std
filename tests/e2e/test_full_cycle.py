"""
End-to-End Tests

Tests the complete cycle: add task → daemon → validate
These tests are slow and may use real Claude CLI.
"""

import json
import time
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.orchestrator import Orchestrator
from core.daemon import Daemon
from core.task_queue import TaskStatus


class TestFullCycleMocked:
    """Full cycle tests with mocked Claude CLI."""

    def test_add_run_complete_cycle(self, temp_workspace: Path):
        """Test: add task → run_once → completion."""
        orch = Orchestrator(workspace=temp_workspace)

        # 1. Add task
        task = orch.add_task("test_project", "Create hello.txt with 'Hello World'")
        assert task.status == TaskStatus.PENDING

        # 2. Mock execution
        with patch.object(orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": True, "output": "Created hello.txt"}

            # 3. Run
            completed = orch.run_once(analyze=False)

            # 4. Verify
            assert completed is not None
            assert completed.status == TaskStatus.COMPLETED
            assert completed.id == task.id

    def test_add_run_fail_cycle(self, temp_workspace: Path):
        """Test: add task → run_once → failure."""
        orch = Orchestrator(workspace=temp_workspace)

        task = orch.add_task("test_project", "Impossible task")

        with patch.object(orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": False, "error": "Cannot do this"}

            completed = orch.run_once(analyze=False)

            assert completed.status == TaskStatus.FAILED
            assert "Cannot do this" in completed.error

    def test_daemon_processes_queue(self, temp_workspace: Path):
        """Test daemon processing multiple tasks."""
        # Ensure test_project has main.lua for discovery
        (temp_workspace / "test_project" / "main.lua").write_text("-- game", encoding="utf-8")

        orch = Orchestrator(workspace=temp_workspace)
        orch.reload_projects()

        # Add multiple tasks
        orch.add_task("test_project", "Task 1")
        orch.add_task("test_project", "Task 2")
        orch.add_task("test_project", "Task 3")

        daemon = Daemon(
            workspace=temp_workspace,
            log_to_file=False,
            workers=1,
            analyze=False  # Skip analysis for mocked tests
        )

        # Mock execution
        with patch.object(daemon.orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": True, "output": "Done"}

            # Run with max_tasks limit
            stats = daemon.run(max_tasks=3)

            assert stats["tasks_completed"] == 3
            assert stats["tasks_failed"] == 0

    def test_daemon_stops_on_consecutive_failures(self, temp_workspace: Path):
        """Daemon should stop after N consecutive failures."""
        (temp_workspace / "test_project" / "main.lua").write_text("-- game", encoding="utf-8")

        orch = Orchestrator(workspace=temp_workspace)
        orch.reload_projects()

        for i in range(10):
            orch.add_task("test_project", f"Task {i}")

        daemon = Daemon(
            workspace=temp_workspace,
            log_to_file=False,
            max_consecutive_failures=2,
            analyze=False  # Skip analysis for mocked tests
        )

        with patch.object(daemon.orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": False, "error": "Always fails"}

            stats = daemon.run(max_tasks=10)

            # Should stop after 2 consecutive failures
            assert stats["tasks_failed"] == 2

    def test_budget_tracking_through_cycle(self, temp_workspace: Path):
        """Budget should track task execution."""
        orch = Orchestrator(workspace=temp_workspace)

        initial_records = len(orch.budget.records)

        orch.add_task("test_project", "Task 1")
        orch.add_task("test_project", "Task 2")

        with patch.object(orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": True, "output": "Done"}

            orch.run_all(max_tasks=2, analyze=False)

        assert len(orch.budget.records) == initial_records + 2

    def test_project_status_through_cycle(self, temp_workspace: Path):
        """Project STATUS.json should be updated."""
        orch = Orchestrator(workspace=temp_workspace)

        orch.add_task("test_project", "Status test task")

        with patch.object(orch, '_execute_task') as mock_exec:
            mock_exec.return_value = {"success": True, "output": "Done"}

            orch.run_once(analyze=False)

        status_file = temp_workspace / "test_project" / "STATUS.json"
        assert status_file.exists()

        data = json.loads(status_file.read_text(encoding="utf-8"))
        assert data["state"] == "ready"
        assert data["tasks_completed"] >= 1


class TestCLICycle:
    """Test CLI commands end-to-end."""

    def test_cli_add_task(self, temp_workspace: Path):
        """Test CLI add command."""
        cli_path = Path(__file__).parent.parent.parent / "cli.py"

        result = subprocess.run(
            [
                sys.executable, str(cli_path),
                "--workspace", str(temp_workspace),
                "add", "test_project", "Test CLI task"
            ],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Added task" in result.stdout

    def test_cli_tasks_list(self, temp_workspace: Path):
        """Test CLI tasks command."""
        cli_path = Path(__file__).parent.parent.parent / "cli.py"

        # First add a task
        orch = Orchestrator(workspace=temp_workspace)
        orch.add_task("test_project", "List test task")

        result = subprocess.run(
            [
                sys.executable, str(cli_path),
                "--workspace", str(temp_workspace),
                "tasks"
            ],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Pending" in result.stdout or "pending" in result.stdout.lower()

    def test_cli_status(self, temp_workspace: Path):
        """Test CLI status command."""
        cli_path = Path(__file__).parent.parent.parent / "cli.py"

        result = subprocess.run(
            [
                sys.executable, str(cli_path),
                "--workspace", str(temp_workspace),
                "status"
            ],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Ptero Dactyl Studio" in result.stdout


@pytest.mark.e2e
@pytest.mark.slow
class TestFullCycleReal:
    """Full cycle tests with real Claude CLI."""

    @pytest.mark.skipif(
        not pytest.importorskip("shutil").which("claude"),
        reason="Claude CLI not available"
    )
    def test_real_simple_task(self, temp_workspace: Path):
        """Execute a real simple task end-to-end."""
        # Create test project with main.lua for discovery
        proj = temp_workspace / "real_test"
        proj.mkdir()
        (proj / "CLAUDE.md").write_text("# Real Test\nA test project.", encoding="utf-8")
        (proj / "main.lua").write_text("-- game", encoding="utf-8")
        (proj / "data.txt").write_text("initial content", encoding="utf-8")

        orch = Orchestrator(workspace=temp_workspace)
        orch.reload_projects()

        # Check project was discovered
        if "real_test" not in [p.name for p in orch.projects]:
            pytest.skip("Project not discovered")

        # Add a simple task
        task = orch.add_task(
            "real_test",
            "Read data.txt and append ' - modified' to its content"
        )

        # Execute (real Claude)
        completed = orch.run_once(analyze=False, validate=False)

        # Task should complete
        assert completed is not None
        # Result depends on Claude, so we just check it ran

    @pytest.mark.skipif(
        not pytest.importorskip("shutil").which("claude"),
        reason="Claude CLI not available"
    )
    def test_real_task_with_analysis(self, temp_workspace: Path):
        """Execute task with Opus analysis."""
        proj = temp_workspace / "analyzed_test"
        proj.mkdir()
        (proj / "CLAUDE.md").write_text("# Analyzed Test", encoding="utf-8")
        (proj / "main.lua").write_text("-- game", encoding="utf-8")

        orch = Orchestrator(workspace=temp_workspace)
        orch.reload_projects()

        # Check project was discovered
        if "analyzed_test" not in [p.name for p in orch.projects]:
            pytest.skip("Project not discovered")

        task = orch.add_task("analyzed_test", "Create a file hello.txt with text 'Hello'")

        # Execute with analysis
        completed = orch.run_once(analyze=True, validate=False)

        assert completed is not None
        # Analysis should have been performed (check logs)


class TestParallelExecution:
    """Test parallel worker execution."""

    def test_parallel_processes_different_projects(self, temp_workspace: Path):
        """Parallel workers should process different projects."""
        # Create multiple projects with main.lua for discovery
        for name in ["proj_a", "proj_b", "proj_c"]:
            proj = temp_workspace / name
            proj.mkdir()
            (proj / "CLAUDE.md").write_text(f"# {name}", encoding="utf-8")
            (proj / "main.lua").write_text("-- game", encoding="utf-8")

        orch = Orchestrator(workspace=temp_workspace)
        orch.reload_projects()

        # Add tasks to different projects
        orch.add_task("proj_a", "Task A")
        orch.add_task("proj_b", "Task B")
        orch.add_task("proj_c", "Task C")

        daemon = Daemon(
            workspace=temp_workspace,
            log_to_file=False,
            workers=3,
            analyze=False  # Skip analysis for mocked tests
        )

        executed_projects = []

        def mock_exec(self_orch, task, project, **kwargs):
            executed_projects.append(project.name)
            time.sleep(0.1)  # Simulate work
            return {"success": True, "output": "Done"}

        # Patch at class level since ParallelExecutor creates its own Orchestrator
        with patch.object(Orchestrator, '_execute_task', mock_exec):
            stats = daemon.run(max_tasks=3)

        # All three projects should have been processed
        assert len(set(executed_projects)) == 3
        assert stats["tasks_completed"] == 3
