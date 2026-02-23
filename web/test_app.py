"""
Tests for Ptero Studio Web Dashboard

Run: cd studio && python -m pytest web/test_app.py -v
"""

import pytest
import os
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["PTERO_WORKSPACE"] = "C:/Ptero Dactyl Games"

from fastapi.testclient import TestClient
from web.app import app


@pytest.fixture
def client():
    """Test client fixture with proper lifespan handling."""
    with TestClient(app) as c:
        yield c


class TestPages:
    """Test page rendering."""

    def test_index_loads(self, client):
        """Main dashboard loads."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Ptero Studio" in response.text

    def test_tasks_page_loads(self, client):
        """Tasks page loads."""
        response = client.get("/tasks")
        assert response.status_code == 200
        assert "Tasks" in response.text

    def test_projects_page_loads(self, client):
        """Projects page loads."""
        response = client.get("/projects")
        assert response.status_code == 200
        assert "Projects" in response.text


class TestPartials:
    """Test HTMX partials."""

    def test_stats_partial(self, client):
        """Stats partial returns valid HTML."""
        response = client.get("/partials/stats")
        assert response.status_code == 200
        assert "Pending" in response.text
        assert "Completed" in response.text

    def test_tasks_list_partial(self, client):
        """Tasks list partial works."""
        response = client.get("/partials/tasks-list")
        assert response.status_code == 200


class TestTasksAPI:
    """Test task operations."""

    def test_add_task(self, client):
        """Add task via form."""
        response = client.post(
            "/tasks/add",
            data={
                "project": "backpack_hero",
                "description": "Test task from web",
                "priority": "normal"
            }
        )
        assert response.status_code == 200

    def test_add_task_with_priority(self, client):
        """Add high priority task."""
        response = client.post(
            "/tasks/add",
            data={
                "project": "backpack_hero",
                "description": "Urgent test task",
                "priority": "high"
            }
        )
        assert response.status_code == 200


class TestAPI:
    """Test JSON API endpoints."""

    def test_api_tasks(self, client):
        """GET /api/tasks returns JSON."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_api_tasks_filter_project(self, client):
        """Filter tasks by project."""
        response = client.get("/api/tasks?project=backpack_hero")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        for task in data:
            assert task["project"] == "backpack_hero"

    def test_api_stats(self, client):
        """GET /api/stats returns stats."""
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "pending" in data
        assert "completed" in data
        assert "failed" in data
        assert "daemon_running" in data


class TestDaemon:
    """Test daemon control."""

    def test_daemon_start(self, client):
        """Start daemon returns response."""
        response = client.post("/daemon/start", data={"workers": 1})
        assert response.status_code == 200

    def test_daemon_stop(self, client):
        """Stop daemon returns response."""
        response = client.post("/daemon/stop")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
