"""
Pytest Configuration

Shared fixtures and configuration for all tests.
"""

import os
import sys
import json
import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# Add studio to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.task_queue import TaskQueue, Task, TaskPriority, TaskStatus
from core.project_status import ProjectStatus, ProjectState
from core.budget import Budget
from core.project import Project, Engine


# ============================================================================
# Fixtures: Temporary directories
# ============================================================================

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    path = Path(tempfile.mkdtemp(prefix="ptero_test_"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def temp_workspace(temp_dir: Path) -> Path:
    """Create a temporary workspace with studio structure."""
    studio = temp_dir / "studio"
    studio.mkdir()
    (studio / "logs").mkdir()
    (studio / "validation").mkdir()

    # Create a test project (needs main.lua for LOVE engine detection)
    test_project = temp_dir / "test_project"
    test_project.mkdir()
    (test_project / "CLAUDE.md").write_text("# Test Project\nA LOVE 2D test project.\n", encoding="utf-8")
    (test_project / "main.lua").write_text("-- Test game\nfunction love.load() end\n", encoding="utf-8")
    (test_project / "conf.lua").write_text("-- Config\n", encoding="utf-8")

    return temp_dir


# ============================================================================
# Fixtures: Task Queue
# ============================================================================

@pytest.fixture
def empty_queue(temp_dir: Path) -> TaskQueue:
    """Create an empty task queue."""
    return TaskQueue(temp_dir / "tasks.json")


@pytest.fixture
def queue_with_tasks(temp_dir: Path) -> TaskQueue:
    """Create a task queue with sample tasks."""
    queue = TaskQueue(temp_dir / "tasks.json")

    queue.add(Task(project="proj_a", description="Task A1", priority=TaskPriority.NORMAL))
    queue.add(Task(project="proj_a", description="Task A2", priority=TaskPriority.HIGH))
    queue.add(Task(project="proj_b", description="Task B1", priority=TaskPriority.LOW))
    queue.add(Task(project="proj_c", description="Task C1", priority=TaskPriority.CRITICAL))

    return queue


# ============================================================================
# Fixtures: Project Status
# ============================================================================

@pytest.fixture
def project_status(temp_dir: Path) -> ProjectStatus:
    """Create a project status instance."""
    project_dir = temp_dir / "test_project"
    project_dir.mkdir(exist_ok=True)
    return ProjectStatus.load(project_dir)


# ============================================================================
# Fixtures: Budget
# ============================================================================

@pytest.fixture
def empty_budget(temp_dir: Path) -> Budget:
    """Create an empty budget tracker."""
    return Budget(temp_dir / "budget.json")


@pytest.fixture
def budget_with_records(temp_dir: Path) -> Budget:
    """Create a budget with sample records."""
    budget = Budget(temp_dir / "budget.json")

    budget.record_task(
        task_id="task-1",
        project="test",
        description="Test task 1",
        output_length=1000,
        duration_seconds=30,
        success=True
    )
    budget.record_task(
        task_id="task-2",
        project="test",
        description="Test task 2",
        output_length=2000,
        duration_seconds=45,
        success=False
    )

    return budget


# ============================================================================
# Fixtures: Mock Claude CLI
# ============================================================================

@pytest.fixture
def mock_claude_cli(temp_dir: Path, monkeypatch):
    """
    Mock the Claude CLI for integration tests.
    Creates a fake 'claude' script that returns predefined responses.
    """
    # Create mock script
    if sys.platform == "win32":
        mock_script = temp_dir / "claude.cmd"
        mock_script.write_text('@echo {"success": true, "output": "Mock response"}', encoding="utf-8")
    else:
        mock_script = temp_dir / "claude"
        mock_script.write_text('#!/bin/bash\necho \'{"success": true, "output": "Mock response"}\'', encoding="utf-8")
        mock_script.chmod(0o755)

    # Add to PATH
    old_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{temp_dir}{os.pathsep}{old_path}")

    return mock_script


# ============================================================================
# Markers
# ============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, no external deps)")
    config.addinivalue_line("markers", "integration: Integration tests (may use Claude)")
    config.addinivalue_line("markers", "e2e: End-to-end tests (slow, full cycle)")
    config.addinivalue_line("markers", "slow: Slow tests")


# ============================================================================
# Skip conditions
# ============================================================================

def has_claude_cli() -> bool:
    """Check if Claude CLI is available."""
    return shutil.which("claude") is not None or shutil.which("claude.cmd") is not None


skip_without_claude = pytest.mark.skipif(
    not has_claude_cli(),
    reason="Claude CLI not available"
)
