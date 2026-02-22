"""
Context Isolation

Enforces project boundaries to prevent workers from modifying files
outside their assigned project.

Layers of protection:
1. Process isolation: --cwd limits initial context
2. Prompt isolation: Rules in system prompt
3. Post-validation: Git diff check after execution
4. Rollback: Undo changes if violations detected

Usage:
    from core.isolation import IsolationConfig, validate_changes

    config = IsolationConfig.load(project_path)
    violations = validate_changes(project_path, config)
    if violations:
        rollback_changes(project_path)
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Set, Any
from dataclasses import dataclass, field

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger("studio.isolation")


class IsolationViolation(Exception):
    """Raised when a worker attempts to access outside boundaries."""

    def __init__(self, violations: List[str], project: str):
        self.violations = violations
        self.project = project
        message = f"Isolation violation in {project}: {', '.join(violations)}"
        super().__init__(message)


@dataclass
class IsolationConfig:
    """
    Project isolation configuration.
    Loaded from .isolation file in project root.
    """
    project_id: str
    boundary: Path
    allowed_external_reads: List[str] = field(default_factory=list)
    allowed_external_writes: List[str] = field(default_factory=list)
    restricted_paths: List[str] = field(default_factory=lambda: [
        ".git/",
        ".env",
        ".env.*",
        "secrets/",
        "credentials.*"
    ])
    allowed_tools: List[str] = field(default_factory=lambda: [
        "Read", "Write", "Edit", "Bash", "Glob", "Grep", "TodoWrite"
    ])
    timeout: int = 300

    @classmethod
    def load(cls, project_path: Path) -> "IsolationConfig":
        """
        Load isolation config from .isolation file.
        Falls back to defaults if file doesn't exist.
        """
        isolation_file = project_path / ".isolation"

        if isolation_file.exists() and YAML_AVAILABLE:
            try:
                with open(isolation_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                return cls(
                    project_id=data.get("project_id", project_path.name),
                    boundary=Path(data.get("boundary", str(project_path))),
                    allowed_external_reads=data.get("allowed_external_reads", []),
                    allowed_external_writes=data.get("allowed_external_writes", []),
                    restricted_paths=data.get("restricted_paths", cls.restricted_paths),
                    allowed_tools=data.get("allowed_tools", cls.allowed_tools),
                    timeout=data.get("timeout", 300)
                )
            except Exception as e:
                logger.warning(f"Failed to load .isolation: {e}, using defaults")

        # Default config
        return cls(
            project_id=project_path.name,
            boundary=project_path
        )

    def save(self, project_path: Path) -> None:
        """Save isolation config to .isolation file."""
        if not YAML_AVAILABLE:
            logger.warning("PyYAML not installed, cannot save .isolation")
            return

        isolation_file = project_path / ".isolation"
        data = {
            "project_id": self.project_id,
            "boundary": str(self.boundary),
            "allowed_external_reads": self.allowed_external_reads,
            "allowed_external_writes": self.allowed_external_writes,
            "restricted_paths": self.restricted_paths,
            "allowed_tools": self.allowed_tools,
            "timeout": self.timeout
        }

        with open(isolation_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    def is_path_allowed(self, path: Path, write: bool = False) -> bool:
        """
        Check if a path is allowed for read/write operations.

        Args:
            path: Path to check
            write: True for write operations, False for read

        Returns:
            True if operation is allowed
        """
        resolved = path.resolve()
        boundary_resolved = self.boundary.resolve()

        # Check if within boundary
        try:
            rel_path = resolved.relative_to(boundary_resolved)
            # Within boundary - check restricted paths
            for restricted in self.restricted_paths:
                if self._is_restricted(rel_path, restricted):
                    return False
            return True
        except ValueError:
            # Outside boundary
            pass

        # Check allowed external paths
        allowed_list = self.allowed_external_writes if write else self.allowed_external_reads
        for pattern in allowed_list:
            if self._matches_glob(resolved, pattern):
                return True

        return False

    def _is_restricted(self, rel_path: Path, pattern: str) -> bool:
        """Check if relative path matches a restricted pattern."""
        import fnmatch
        path_str = str(rel_path).replace("\\", "/")
        pattern = pattern.replace("\\", "/")

        # Directory pattern (ends with /)
        if pattern.endswith("/"):
            dir_name = pattern.rstrip("/")
            # Check if path starts with this directory
            if path_str.startswith(dir_name + "/") or path_str == dir_name:
                return True
            # Check if any part of path matches
            parts = path_str.split("/")
            if dir_name in parts:
                return True

        # Wildcard pattern
        elif "*" in pattern:
            return fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(rel_path.name, pattern)

        # Exact match
        else:
            return path_str == pattern or rel_path.name == pattern

        return False

    def _matches_glob(self, path: Path, pattern: str) -> bool:
        """Check if path matches a glob pattern."""
        import fnmatch
        try:
            return fnmatch.fnmatch(str(path), f"*/{pattern}")
        except Exception:
            return False


def get_changed_files(project_path: Path) -> List[Path]:
    """
    Get list of files changed since last commit (including untracked).

    Returns:
        List of changed file paths (absolute)
    """
    files: Set[Path] = set()

    try:
        # Get staged and unstaged changes (modified/deleted files)
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line:
                    files.add(project_path / line)

        # Get all changes (including untracked) using git status --porcelain
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                # Porcelain format: XY filename (XY is 2 chars, then space, then filename)
                # Example: " M file.txt", "?? new.txt", "A  staged.txt"
                if line and len(line) > 3:
                    # Status codes: ?? = untracked, M = modified, A = added, etc.
                    filename = line[3:]  # Skip "XY "
                    if " -> " in filename:  # Renamed: "old -> new"
                        filename = filename.split(" -> ")[1]
                    filename = filename.strip()
                    if filename:
                        files.add(project_path / filename)

        return list(files)

    except Exception as e:
        logger.warning(f"Failed to get changed files: {e}")
        return []


def validate_changes(
    project_path: Path,
    config: Optional[IsolationConfig] = None
) -> List[str]:
    """
    Validate that all changes are within allowed boundaries.

    Args:
        project_path: Path to project
        config: Isolation config (loads from file if not provided)

    Returns:
        List of violation descriptions (empty if all OK)
    """
    if config is None:
        config = IsolationConfig.load(project_path)

    changed_files = get_changed_files(project_path)
    violations = []

    for file_path in changed_files:
        if not config.is_path_allowed(file_path, write=True):
            violations.append(f"OUT_OF_BOUNDS: {file_path}")

    return violations


def rollback_changes(project_path: Path) -> bool:
    """
    Rollback all uncommitted changes in project.

    Returns:
        True if successful
    """
    try:
        # Reset staged changes
        subprocess.run(
            ["git", "reset", "HEAD"],
            cwd=project_path,
            capture_output=True,
            check=True
        )

        # Discard unstaged changes
        subprocess.run(
            ["git", "checkout", "."],
            cwd=project_path,
            capture_output=True,
            check=True
        )

        # Clean untracked files
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=project_path,
            capture_output=True,
            check=True
        )

        logger.info(f"Rolled back changes in {project_path}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to rollback: {e}")
        return False


def build_isolation_prompt(project_path: Path, config: Optional[IsolationConfig] = None) -> str:
    """
    Build isolation rules for worker system prompt.

    Args:
        project_path: Path to project
        config: Isolation config

    Returns:
        Isolation rules text to include in prompt
    """
    if config is None:
        config = IsolationConfig.load(project_path)

    allowed_reads = "\n".join(f"  - {p}" for p in config.allowed_external_reads) or "  (none)"

    return f"""
ISOLATION RULES - STRICT COMPLIANCE REQUIRED

You are a worker agent operating within a SINGLE project.

BOUNDARIES:
- Project root: {config.boundary}
- You may ONLY read and modify files within this directory
- You may read (but NOT write): {allowed_reads}

FORBIDDEN ACTIONS:
- DO NOT read files outside {config.boundary} (except allowed paths above)
- DO NOT write/edit/delete files outside {config.boundary}
- DO NOT use cd to navigate outside {config.boundary}
- DO NOT spawn sub-agents that access other projects
- DO NOT modify .git directory directly
- DO NOT access: .env, secrets/, credentials.*

IF TASK REQUIRES EXTERNAL ACCESS:
- Return error: "ISOLATION_VIOLATION: Task requires access to [path]"
- Do NOT attempt to complete the task
- Orchestrator will handle cross-project coordination

VERIFICATION:
- Your changes WILL be audited after execution
- Violations trigger automatic rollback
- Repeated violations flag the task for human review
"""


def log_violation(
    project: str,
    violations: List[str],
    log_dir: Optional[Path] = None
) -> None:
    """
    Log isolation violation to file.

    Args:
        project: Project name
        violations: List of violations
        log_dir: Directory for logs (defaults to studio/logs)
    """
    import json
    from datetime import datetime

    if log_dir is None:
        log_dir = Path("studio/logs")

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "violations.jsonl"

    incident = {
        "timestamp": datetime.now().isoformat(),
        "project": project,
        "violations": violations,
        "action": "rollback"
    }

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(incident, ensure_ascii=False) + "\n")

    logger.warning(f"Logged violation: {project} - {violations}")


# CLI interface
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python -m core.isolation <project_path> [check|create]")
        sys.exit(1)

    project_path = Path(sys.argv[1])
    action = sys.argv[2] if len(sys.argv) > 2 else "check"

    if action == "check":
        config = IsolationConfig.load(project_path)
        violations = validate_changes(project_path, config)

        if violations:
            print(f"VIOLATIONS FOUND ({len(violations)}):")
            for v in violations:
                print(f"  - {v}")
            sys.exit(1)
        else:
            print("No violations detected")
            sys.exit(0)

    elif action == "create":
        config = IsolationConfig(
            project_id=project_path.name,
            boundary=project_path
        )
        config.save(project_path)
        print(f"Created .isolation in {project_path}")
