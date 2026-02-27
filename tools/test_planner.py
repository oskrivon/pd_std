"""
Test Plan Generator

Generates test plans based on recent changes using Claude CLI (Opus).
Uses subscription, not API tokens.

Usage:
    from tools.test_planner import generate_test_plan

    plan = generate_test_plan("backpack_hero", commits=5)
    print(plan)
"""

import subprocess
import shutil
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger("studio.test_planner")

WORKSPACE = Path("C:/Ptero Dactyl Games")


def get_git_diff(project_path: Path, commits: int = 5) -> str:
    """Get git diff for last N commits."""
    try:
        # Get diff stats
        result = subprocess.run(
            ["git", "diff", f"HEAD~{commits}", "--stat"],
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        stats = result.stdout

        # Get commit messages
        result = subprocess.run(
            ["git", "log", f"HEAD~{commits}..HEAD", "--format=%s%n%b"],
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        messages = result.stdout

        return f"## Commit messages\n\n{messages}\n\n## Changed files\n\n{stats}"

    except Exception as e:
        logger.warning(f"Failed to get git diff: {e}")
        return ""


def get_progress(project_path: Path, lines: int = 100) -> str:
    """Get recent entries from PROGRESS.md."""
    progress_file = project_path / "docs" / "PROGRESS.md"
    if not progress_file.exists():
        return ""

    try:
        content = progress_file.read_text(encoding='utf-8')
        # Return first N lines (most recent entries are at top)
        return "\n".join(content.split("\n")[:lines])
    except Exception as e:
        logger.warning(f"Failed to read PROGRESS.md: {e}")
        return ""


def get_project_context(project_path: Path) -> str:
    """Get CLAUDE.md for project context."""
    claude_md = project_path / "CLAUDE.md"
    if not claude_md.exists():
        return ""

    try:
        return claude_md.read_text(encoding='utf-8')
    except Exception as e:
        logger.warning(f"Failed to read CLAUDE.md: {e}")
        return ""


def generate_test_plan(
    project: str,
    commits: int = 5,
    workspace: Optional[Path] = None
) -> str:
    """
    Generate test plan using Claude CLI (Opus).

    Args:
        project: Project name
        commits: Number of commits to analyze
        workspace: Workspace path (default: C:/Ptero Dactyl Games)

    Returns:
        Markdown test plan
    """
    workspace = workspace or WORKSPACE
    project_path = workspace / project

    if not project_path.exists():
        return f"Error: Project not found: {project}"

    # Gather context
    git_diff = get_git_diff(project_path, commits)
    progress = get_progress(project_path)
    context = get_project_context(project_path)

    if not git_diff:
        return "Error: No git changes found"

    # Build prompt
    prompt = f"""Ты QA-инженер. Сгенерируй тест-план для проекта на основе последних изменений.

## Контекст проекта

{context}

## Последние изменения

{git_diff}

## Что было сделано (из PROGRESS.md)

{progress}

## Задача

Создай конкретный тест-план в формате markdown:

1. **Критические тесты** — то, что может сломать игру (баги, новые механики)
2. **Важные тесты** — UX, новые фичи
3. **Регрессия** — проверить что старое не сломалось

Для каждого теста:
- [ ] Конкретное действие → ожидаемый результат

НЕ пиши generic тесты типа "проверить что работает".
Только конкретные кейсы на основе реальных изменений.

Укажи примерное время на полный прогон.
"""

    # Find Claude CLI
    claude_cmd = shutil.which("claude") or shutil.which("claude.cmd")
    if not claude_cmd:
        return "Error: Claude CLI not found"

    # Run Claude CLI with prompt via stdin
    try:
        proc = subprocess.run(
            [claude_cmd, "--print", "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=300,
            cwd=project_path
        )

        if proc.returncode == 0:
            return proc.stdout
        else:
            return f"Error: Claude CLI failed: {proc.stderr}"

    except subprocess.TimeoutExpired:
        return "Error: Claude CLI timeout (300s)"
    except Exception as e:
        return f"Error: {e}"


def save_test_plan(project: str, plan: str, workspace: Optional[Path] = None) -> Path:
    """Save test plan to project's docs folder."""
    workspace = workspace or WORKSPACE
    project_path = workspace / project
    docs_path = project_path / "docs"
    docs_path.mkdir(exist_ok=True)

    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"TEST_PLAN_{date_str}.md"
    filepath = docs_path / filename

    filepath.write_text(plan, encoding='utf-8')
    return filepath


if __name__ == "__main__":
    import sys

    project = sys.argv[1] if len(sys.argv) > 1 else "backpack_hero"
    commits = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    print(f"Generating test plan for {project} (last {commits} commits)...")
    plan = generate_test_plan(project, commits)
    print(plan)
