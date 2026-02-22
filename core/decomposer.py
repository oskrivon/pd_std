"""
Task Decomposer

Breaks down high-level ideas into specific tasks using Claude Code.

Usage:
    from core.decomposer import decompose_idea

    tasks = decompose_idea(
        project="hamster",
        idea="Add a pause menu",
        project_path="C:/Ptero Dactyl Games/hamster"
    )
    # Returns list of task descriptions
"""

import subprocess
import sys
import shutil
import json
import re
from pathlib import Path
from typing import List, Optional
import logging

logger = logging.getLogger("studio.decomposer")


def decompose_idea(
    project: str,
    idea: str,
    project_path: str | Path,
    max_tasks: int = 5
) -> List[str]:
    """
    Decompose a high-level idea into specific tasks.

    Uses Claude Code to analyze the project and break down the idea.

    Args:
        project: Project name
        idea: High-level idea to decompose
        project_path: Path to project directory
        max_tasks: Maximum number of tasks to generate

    Returns:
        List of task descriptions
    """
    project_path = Path(project_path)

    prompt = f'''You are analyzing the "{project}" project to break down a feature request.

IDEA: {idea}

INSTRUCTIONS:
1. Look at the existing codebase structure
2. Break this idea into {max_tasks} or fewer specific, actionable tasks
3. Each task should be small enough to complete in one session
4. Order tasks by dependency (do X before Y)

OUTPUT FORMAT:
Return ONLY a JSON array of task descriptions, nothing else:
["Task 1 description", "Task 2 description", ...]

Example output:
["Create pause state enum", "Add key handler for ESC to toggle pause", "Create pause menu UI widget"]

DO NOT include explanations, just the JSON array.
'''

    # Find Claude CLI
    claude_cmd = shutil.which("claude") or shutil.which("claude.cmd")
    if not claude_cmd:
        logger.error("Claude CLI not found")
        return [idea]  # Return original idea as single task

    try:
        result = subprocess.run(
            [claude_cmd, "--dangerously-skip-permissions"],
            input=prompt,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
            shell=(sys.platform == "win32")
        )

        output = result.stdout.strip()

        # Extract JSON array from output
        tasks = _parse_tasks(output)

        if tasks:
            logger.info(f"Decomposed '{idea}' into {len(tasks)} tasks")
            return tasks
        else:
            logger.warning(f"Could not parse decomposition, using original idea")
            return [idea]

    except subprocess.TimeoutExpired:
        logger.error("Decomposition timed out")
        return [idea]
    except Exception as e:
        logger.error(f"Decomposition failed: {e}")
        return [idea]


def _parse_tasks(output: str) -> List[str]:
    """Parse task list from Claude output."""
    # Try to find JSON array in output
    # Handle markdown code blocks
    if "```" in output:
        match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', output, re.DOTALL)
        if match:
            output = match.group(1)

    # Find raw JSON array
    start = output.find("[")
    end = output.rfind("]") + 1

    if start >= 0 and end > start:
        try:
            tasks = json.loads(output[start:end])
            if isinstance(tasks, list) and all(isinstance(t, str) for t in tasks):
                return [t.strip() for t in tasks if t.strip()]
        except json.JSONDecodeError:
            pass

    # Fallback: try to parse numbered list
    lines = output.split("\n")
    tasks = []
    for line in lines:
        # Match "1. Task" or "- Task" patterns
        match = re.match(r'^\s*(?:\d+\.|-|\*)\s*(.+)$', line)
        if match:
            task = match.group(1).strip()
            if task and not task.startswith('[') and not task.startswith('{'):
                tasks.append(task)

    return tasks


# Module test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test decomposition
    tasks = decompose_idea(
        project="hamster",
        idea="Add sound effects when clicking objects",
        project_path="C:/Ptero Dactyl Games/hamster"
    )

    print("Decomposed tasks:")
    for i, task in enumerate(tasks, 1):
        print(f"  {i}. {task}")
