"""
Unit Tests for Isolation

Tests cover:
- IsolationConfig loading and defaults
- Path validation (within/outside boundary)
- Restricted paths detection
- Changed files detection
- Violation logging
"""

import json
from pathlib import Path

import pytest

from core.isolation import (
    IsolationConfig,
    IsolationViolation,
    validate_changes,
    build_isolation_prompt,
    get_changed_files
)


class TestIsolationConfig:
    """Tests for IsolationConfig class."""

    def test_default_config(self, temp_dir: Path):
        """Should create default config when no .isolation file."""
        config = IsolationConfig.load(temp_dir)

        assert config.project_id == temp_dir.name
        assert config.boundary == temp_dir
        assert ".git/" in config.restricted_paths
        assert ".env" in config.restricted_paths

    def test_default_allowed_tools(self, temp_dir: Path):
        """Should have default allowed tools."""
        config = IsolationConfig.load(temp_dir)

        assert "Read" in config.allowed_tools
        assert "Write" in config.allowed_tools
        assert "Edit" in config.allowed_tools
        assert "Bash" in config.allowed_tools

    def test_default_timeout(self, temp_dir: Path):
        """Should have default timeout."""
        config = IsolationConfig.load(temp_dir)

        assert config.timeout == 300


class TestPathValidation:
    """Tests for path validation."""

    def test_path_within_boundary_allowed(self, temp_dir: Path):
        """Paths within boundary should be allowed."""
        config = IsolationConfig(
            project_id="test",
            boundary=temp_dir
        )

        file_path = temp_dir / "src" / "main.py"
        assert config.is_path_allowed(file_path, write=False) is True
        assert config.is_path_allowed(file_path, write=True) is True

    def test_path_outside_boundary_denied(self, temp_dir: Path):
        """Paths outside boundary should be denied."""
        config = IsolationConfig(
            project_id="test",
            boundary=temp_dir
        )

        outside_path = temp_dir.parent / "other_project" / "file.py"
        assert config.is_path_allowed(outside_path, write=False) is False
        assert config.is_path_allowed(outside_path, write=True) is False

    def test_restricted_path_denied(self, temp_dir: Path):
        """Restricted paths should be denied even within boundary."""
        config = IsolationConfig(
            project_id="test",
            boundary=temp_dir,
            restricted_paths=[".git/", ".env", "secrets/"]
        )

        # .git directory
        git_path = temp_dir / ".git" / "config"
        assert config.is_path_allowed(git_path, write=True) is False

        # .env file
        env_path = temp_dir / ".env"
        assert config.is_path_allowed(env_path, write=True) is False

        # secrets directory
        secret_path = temp_dir / "secrets" / "key.json"
        assert config.is_path_allowed(secret_path, write=True) is False

    def test_allowed_external_read(self, temp_dir: Path):
        """Allowed external paths should be readable."""
        workspace = temp_dir.parent
        config = IsolationConfig(
            project_id="test",
            boundary=temp_dir,
            allowed_external_reads=["studio/tools/**"]
        )

        # Should allow reading tools
        tools_path = workspace / "studio" / "tools" / "capture.py"
        assert config.is_path_allowed(tools_path, write=False) is True
        # But not writing
        assert config.is_path_allowed(tools_path, write=True) is False

    def test_allowed_external_write(self, temp_dir: Path):
        """Allowed external write paths should be writable."""
        workspace = temp_dir.parent
        config = IsolationConfig(
            project_id="test",
            boundary=temp_dir,
            allowed_external_writes=["shared/output/**"]
        )

        output_path = workspace / "shared" / "output" / "result.json"
        assert config.is_path_allowed(output_path, write=True) is True


class TestIsolationViolation:
    """Tests for IsolationViolation exception."""

    def test_violation_has_details(self):
        """Violation should contain project and violations."""
        violation = IsolationViolation(
            violations=["OUT_OF_BOUNDS: /other/file.py"],
            project="test_project"
        )

        assert violation.project == "test_project"
        assert len(violation.violations) == 1
        assert "OUT_OF_BOUNDS" in violation.violations[0]
        assert "test_project" in str(violation)


class TestValidateChanges:
    """Tests for validate_changes function."""

    def test_no_changes_no_violations(self, temp_dir: Path):
        """No changes should mean no violations."""
        # Create a git repo with no changes
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=temp_dir, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=temp_dir, capture_output=True
        )

        # Create and commit a file
        (temp_dir / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=temp_dir, capture_output=True
        )

        violations = validate_changes(temp_dir)
        assert len(violations) == 0

    def test_changes_within_boundary_allowed(self, temp_dir: Path):
        """Changes within boundary should not cause violations."""
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=temp_dir, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=temp_dir, capture_output=True
        )

        # Create and commit a file
        (temp_dir / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=temp_dir, capture_output=True
        )

        # Modify file (within boundary)
        (temp_dir / "file.txt").write_text("modified")

        violations = validate_changes(temp_dir)
        assert len(violations) == 0


class TestBuildIsolationPrompt:
    """Tests for build_isolation_prompt function."""

    def test_prompt_contains_boundary(self, temp_dir: Path):
        """Prompt should contain project boundary."""
        prompt = build_isolation_prompt(temp_dir)

        assert str(temp_dir) in prompt
        assert "ISOLATION RULES" in prompt

    def test_prompt_contains_forbidden_actions(self, temp_dir: Path):
        """Prompt should contain forbidden actions."""
        prompt = build_isolation_prompt(temp_dir)

        assert "FORBIDDEN ACTIONS" in prompt
        assert ".git" in prompt.lower() or "git directory" in prompt.lower()

    def test_prompt_contains_verification_warning(self, temp_dir: Path):
        """Prompt should warn about verification."""
        prompt = build_isolation_prompt(temp_dir)

        assert "VERIFICATION" in prompt
        assert "audited" in prompt.lower() or "rollback" in prompt.lower()


class TestGetChangedFiles:
    """Tests for get_changed_files function."""

    def test_no_git_repo_returns_empty(self, temp_dir: Path):
        """Non-git directory should return empty list."""
        files = get_changed_files(temp_dir)
        assert files == []

    def test_detects_modified_files(self, temp_dir: Path):
        """Should detect modified files."""
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=temp_dir, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=temp_dir, capture_output=True
        )

        # Create and commit
        (temp_dir / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=temp_dir, capture_output=True
        )

        # Modify
        (temp_dir / "file.txt").write_text("modified")

        files = get_changed_files(temp_dir)
        file_names = [f.name for f in files]
        assert "file.txt" in file_names

    def test_detects_new_files(self, temp_dir: Path):
        """Should detect new untracked files."""
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=temp_dir, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=temp_dir, capture_output=True
        )

        # Create initial commit
        (temp_dir / "initial.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=temp_dir, capture_output=True
        )

        # Add new file
        (temp_dir / "new_file.txt").write_text("new content")

        files = get_changed_files(temp_dir)
        # New file shows in git status
        file_names = [f.name for f in files]
        assert "new_file.txt" in file_names
