"""
Task Analyzer

Uses Opus to analyze and classify tasks before execution.
Determines task quality, type, and routing.

Usage:
    from core.analyzer import analyze_task, TaskType

    result = analyze_task(
        project="hamster",
        description="добавить парк с деревьями",
        project_path="./workspace/hamster"
    )

    if result.task_type == TaskType.UNCLEAR:
        print(f"Нужно уточнить: {result.feedback}")
    elif result.task_type == TaskType.COMPLEX:
        # Декомпозировать через Opus
        subtasks = result.subtasks
"""

import subprocess
import sys
import shutil
import json
import re
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import logging

logger = logging.getLogger("studio.analyzer")


class TaskType(str, Enum):
    """Task classification."""
    SIMPLE = "simple"      # Прямое выполнение, Sonnet
    CLEAR = "clear"        # Понятная задача, Sonnet с контекстом
    COMPLEX = "complex"    # Нужна декомпозиция, Opus → Sonnet
    UNCLEAR = "unclear"    # Вернуть пользователю


@dataclass
class AnalysisResult:
    """Result of task analysis."""
    task_type: TaskType
    confidence: float  # 0-1
    reasoning: str
    feedback: Optional[str] = None  # Для UNCLEAR - что уточнить
    subtasks: Optional[List[str]] = None  # Для COMPLEX - декомпозиция
    context_needed: Optional[List[str]] = None  # Какие файлы прочитать
    model_recommendation: str = "sonnet"  # Рекомендуемая модель


def analyze_task(
    project: str,
    description: str,
    project_path: str | Path,
    project_engine: str = "love"
) -> AnalysisResult:
    """
    Analyze task using Opus.

    Args:
        project: Project name
        description: Task description
        project_path: Path to project
        project_engine: Engine type (love, unreal)

    Returns:
        AnalysisResult with classification and routing info
    """
    project_path = Path(project_path)

    prompt = f'''Ты — архитектор игровой студии. Проанализируй задачу и определи её тип.

ИЗОЛЯЦИЯ: Ты работаешь ТОЛЬКО с проектом "{project}".
ИГНОРИРУЙ любую информацию о других проектах (backpack_hero, babylon, studio и т.д.).
Если в контексте упоминается "лава", "рюкзак", "треугольная сетка" — это НЕ относится к текущему проекту.

ПРОЕКТ: {project} ({project_engine} engine)
ЗАДАЧА: {description}

ТИПЫ ЗАДАЧ:
1. SIMPLE — простое изменение, одно действие (исправить опечатку, изменить число, добавить комментарий)
2. CLEAR — понятная задача средней сложности (добавить кнопку, новый state, обработчик события)
3. COMPLEX — сложная задача, требует декомпозиции (новая игровая механика, новый уровень/комната, система)
4. UNCLEAR — неоднозначная формулировка, нужно уточнение у пользователя

ВАЖНО для классификации:
- "уровень" в контексте игры = новая локация/комната, НЕ экран меню
- "добавить X с Y, Z" где Y, Z — игровые объекты = COMPLEX (новый контент)
- Если задача на русском про игровые объекты (дерево, скамейка, враг) — это игровой контент

Ответь СТРОГО в JSON формате:
{{
    "task_type": "simple|clear|complex|unclear",
    "confidence": 0.0-1.0,
    "reasoning": "почему такой тип",
    "feedback": "что уточнить (только для unclear)",
    "subtasks": ["подзадача1", "подзадача2"] или null,
    "context_files": ["файл1.lua", "файл2.lua"] или null
}}

Только JSON, без markdown.'''

    # Use Opus for analysis
    claude_cmd = shutil.which("claude") or shutil.which("claude.cmd")
    if not claude_cmd:
        logger.error("Claude CLI not found")
        return AnalysisResult(
            task_type=TaskType.CLEAR,
            confidence=0.5,
            reasoning="Fallback: Claude CLI not found",
            model_recommendation="sonnet"
        )

    # Isolation prompt to prevent cross-project context leaking
    isolation_prompt = f"""CRITICAL: You are analyzing a task for project "{project}" ONLY.
IGNORE all context about other projects (backpack_hero, babylon, studio, etc.).
If you see mentions of "lava map", "triangular grid", "backpack", "CCG", "Unreal" - these are NOT relevant.
Focus ONLY on the task description provided."""

    try:
        result = subprocess.run(
            [claude_cmd, "--print", "--dangerously-skip-permissions", "--model", "opus",
             "--append-system-prompt", isolation_prompt],
            input=prompt,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,  # Reduced to 1 minute for analysis
            shell=(sys.platform == "win32"),
            encoding='utf-8',
            errors='replace'
        )

        output = result.stdout.strip()
        return _parse_analysis(output)

    except subprocess.TimeoutExpired:
        logger.error("Analysis timed out")
        return AnalysisResult(
            task_type=TaskType.CLEAR,
            confidence=0.5,
            reasoning="Fallback: timeout",
            model_recommendation="sonnet"
        )
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return AnalysisResult(
            task_type=TaskType.CLEAR,
            confidence=0.5,
            reasoning=f"Fallback: {e}",
            model_recommendation="sonnet"
        )


def _parse_analysis(output: str) -> AnalysisResult:
    """Parse Opus analysis output."""
    # Extract JSON from output
    if "```" in output:
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', output, re.DOTALL)
        if match:
            output = match.group(1)

    # Find raw JSON
    start = output.find("{")
    end = output.rfind("}") + 1

    if start >= 0 and end > start:
        try:
            data = json.loads(output[start:end])

            task_type = TaskType(data.get("task_type", "clear"))

            # Determine model based on task type
            if task_type == TaskType.SIMPLE:
                model = "sonnet"
            elif task_type == TaskType.CLEAR:
                model = "sonnet"
            elif task_type == TaskType.COMPLEX:
                model = "sonnet"  # Execution still Sonnet, but with subtasks
            else:
                model = "sonnet"

            return AnalysisResult(
                task_type=task_type,
                confidence=float(data.get("confidence", 0.7)),
                reasoning=data.get("reasoning", ""),
                feedback=data.get("feedback"),
                subtasks=data.get("subtasks"),
                context_needed=data.get("context_files"),
                model_recommendation=model
            )

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse analysis: {e}")

    # Fallback
    return AnalysisResult(
        task_type=TaskType.CLEAR,
        confidence=0.5,
        reasoning="Could not parse analysis output",
        model_recommendation="sonnet"
    )


# Module test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test cases
    test_tasks = [
        "исправить опечатку в conf.lua",
        "добавить кнопку паузы",
        "добавить еще один уровень с парком. есть скамейка, дерево, урна. хомяк спит в урне под газетой",
        "сделай лучше"
    ]

    for task in test_tasks:
        print(f"\nTask: {task}")
        result = analyze_task(
            project="hamster",
            description=task,
            project_path="./workspace/hamster"
        )
        print(f"  Type: {result.task_type.value}")
        print(f"  Confidence: {result.confidence}")
        print(f"  Reasoning: {result.reasoning}")
        if result.subtasks:
            print(f"  Subtasks: {result.subtasks}")
        if result.feedback:
            print(f"  Feedback: {result.feedback}")
