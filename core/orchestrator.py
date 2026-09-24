"""
Orchestrator

Main coordinator for the studio.
Manages projects, task queue, and dispatches work to workers.

Usage:
    from core.orchestrator import Orchestrator

    orch = Orchestrator("./workspace")
    orch.add_task("backpack_hero", "Add pause menu")
    orch.run_once()  # Execute one task
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

from .project import Project, discover_projects, Engine
from .task_queue import TaskQueue, Task, TaskStatus, TaskPriority
from .budget import Budget
from .analyzer import analyze_task, TaskType, AnalysisResult
from .project_status import ProjectStatus
from .isolation import (
    IsolationConfig,
    IsolationViolation,
    validate_changes,
    rollback_changes,
    build_isolation_prompt,
    log_violation
)

logger = logging.getLogger("studio.orchestrator")

# Check for anthropic SDK
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class Orchestrator:
    """
    Main coordinator for the AI game development studio.
    """

    def __init__(
        self,
        workspace: str | Path = "./workspace",
        tasks_file: str = "tasks.json",
        budget_file: str = "budget.json"
    ):
        self.workspace = Path(workspace)
        self.studio_path = self.workspace / "studio"

        # Load projects
        self._projects: Dict[str, Project] = {}
        self._load_projects()

        # Load task queue
        self.tasks = TaskQueue.load(self.studio_path / tasks_file)

        # Load budget tracker
        self.budget = Budget.load(self.studio_path / budget_file)

    def _load_projects(self) -> None:
        """Discover and load all projects."""
        projects = discover_projects(self.workspace)
        self._projects = {p.name: p for p in projects}
        logger.info(f"Loaded {len(self._projects)} projects")

    def reload_projects(self) -> None:
        """Reload project list."""
        self._load_projects()

    @property
    def projects(self) -> List[Project]:
        """Get all projects."""
        return list(self._projects.values())

    def get_project(self, name: str) -> Optional[Project]:
        """Get project by name."""
        return self._projects.get(name)

    def add_task(
        self,
        project: str,
        description: str,
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> Task:
        """
        Add a task to the queue.
        """
        if project not in self._projects:
            raise ValueError(f"Unknown project: {project}")

        task = Task(
            project=project,
            description=description,
            priority=priority
        )

        self.tasks.add(task)
        self.tasks.save()

        logger.info(f"Added task for {project}: {description[:50]}")
        return task

    def run_once(self, validate: bool = True, analyze: bool = True) -> Optional[Task]:
        """
        Execute one task from the queue.

        Args:
            validate: Run validation after task completion
            analyze: Use Opus to analyze task first (recommended)

        Returns:
            Completed task or None if queue empty
        """
        task = self.tasks.pop_best()
        if not task:
            logger.info("No pending tasks")
            return None

        project = self.get_project(task.project)
        if not project:
            self.tasks.fail(task.id, f"Project not found: {task.project}")
            self.tasks.save()
            return task

        # Analyze task with Opus first
        analysis = None
        if analyze:
            logger.info(f"Analyzing: [{task.project}] {task.description[:50]}...")
            analysis = analyze_task(
                project=project.name,
                description=task.description,
                project_path=project.path,
                project_engine=project.engine.value
            )
            logger.info(f"Analysis: {analysis.task_type.value} (confidence: {analysis.confidence})")

            # Handle UNCLEAR tasks
            if analysis.task_type == TaskType.UNCLEAR:
                feedback = analysis.feedback or "Задача сформулирована неоднозначно"
                self.tasks.fail(task.id, f"UNCLEAR: {feedback}")
                self.tasks.save()
                return task

            # Handle COMPLEX tasks - create subtasks
            if analysis.task_type == TaskType.COMPLEX and analysis.subtasks:
                logger.info(f"Decomposing into {len(analysis.subtasks)} subtasks")
                for i, subtask_desc in enumerate(analysis.subtasks):
                    subtask = Task(
                        project=task.project,
                        description=subtask_desc,
                        priority=task.priority,
                        parent_id=task.id
                    )
                    self.tasks.add(subtask)
                    logger.info(f"  Subtask {i+1}: {subtask_desc[:50]}")

                # Mark original as completed (decomposed)
                self.tasks.complete(task.id, f"Decomposed into {len(analysis.subtasks)} subtasks")
                self.tasks.save()
                return task

        logger.info(f"Executing: [{task.project}] {task.description}")

        import time
        start_time = time.time()
        success = False

        # Update project status: working
        project_status = ProjectStatus.load(project.path)
        project_status.set_working(task.description[:50])
        project_status.save()

        try:
            model = analysis.model_recommendation if analysis else "sonnet"
            context_files = analysis.context_needed if analysis else None
            result = self._execute_task(task, project, model=model, context_files=context_files)

            if result.get("success"):
                self.tasks.complete(task.id, result.get("output", ""))
                success = True
                # Update project status: completed
                project_status.set_completed(task.description[:50])
                project_status.save()
            else:
                error = result.get("error", "Unknown error")
                self.tasks.fail(task.id, error)
                # Update project status: failed
                project_status.set_failed(task.description[:50], error[:100])
                project_status.save()

        except Exception as e:
            logger.exception(f"Task execution failed: {e}")
            self.tasks.fail(task.id, str(e))
            # Update project status: error
            project_status.set_failed(task.description[:50], str(e)[:100])
            project_status.save()

        # Track budget
        duration = time.time() - start_time
        output_len = len(task.result or task.error or "")
        self.budget.record_task(
            task_id=task.id,
            project=task.project,
            description=task.description,
            output_length=output_len,
            duration_seconds=duration,
            success=success
        )
        self.budget.save()

        self.tasks.save()
        return task

    def _kill_process_tree(self, pid: int):
        """Kill a process and all its children."""
        if sys.platform == "win32":
            # Use taskkill with /T to kill process tree
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=10
                )
            except Exception as e:
                logger.warning(f"Failed to kill process tree {pid}: {e}")
        else:
            # On Unix, use process groups
            import signal
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except Exception as e:
                logger.warning(f"Failed to kill process group {pid}: {e}")

    def _execute_task(
        self,
        task: Task,
        project: Project,
        model: str = "sonnet",
        context_files: Optional[List[str]] = None,
        enforce_isolation: bool = True
    ) -> Dict[str, Any]:
        """
        Execute task using Claude Code.

        Args:
            task: Task to execute
            project: Project context
            model: Model to use (sonnet, opus, haiku)
            context_files: Suggested files to read first
            enforce_isolation: Check boundaries after execution
        """
        # Load isolation config
        isolation_config = IsolationConfig.load(project.path)

        # Build prompt with context hints
        context_hint = ""
        if context_files:
            context_hint = f"\nRECOMMENDED FILES TO READ: {', '.join(context_files)}\n"

        # Build isolation rules
        isolation_rules = build_isolation_prompt(project.path, isolation_config)

        prompt = f"""You are working on the "{project.name}" project ({project.engine.value} engine).
{isolation_rules}

TASK: {task.description}
{context_hint}

## ОБЯЗАТЕЛЬНО: Сначала изучи документацию

ПЕРЕД началом работы прочитай:
1. `CLAUDE.md` — инструкции проекта, архитектура, важные правила
2. `docs/RUNBOOK.md` — как запускать, известные проблемы и решения
3. `docs/PROGRESS.md` — что уже сделано, какие проблемы были и как решались

## Если что-то не работает

Когда сталкиваешься с проблемой (чёрный экран, краш, ошибка):
1. СНАЧАЛА поищи в `docs/RUNBOOK.md` и `docs/PROGRESS.md` — возможно, это уже решалось
2. Если нашёл решение — примени его
3. Если не нашёл — попробуй решить и ЗАПИШИ решение в документацию

## INSTRUCTIONS

1. Read CLAUDE.md and docs/ to understand the project
2. Read relevant code files
3. Make minimal, focused changes
4. After making changes, commit with descriptive message
5. If you solved a new problem, document it in docs/PROGRESS.md

## IMPORTANT CONTEXT

- In games, "уровень" (level) means a game location/room, NOT a menu screen
- Game objects like trees, benches, enemies are gameplay content
- If task mentions game objects, create actual game content

DO NOT ask for clarification - just do the task based on the description.
If something is unclear, make reasonable assumptions and proceed.
"""

        # Find Claude CLI (handle Windows .cmd)
        import shutil
        claude_cmd = shutil.which("claude") or shutil.which("claude.cmd")
        if not claude_cmd:
            return {
                "success": False,
                "error": "Claude CLI not found. Is it installed?"
            }

        try:
            # Run Claude Code in project directory with specified model
            cmd = [claude_cmd, "--dangerously-skip-permissions"]
            if model and model != "sonnet":  # sonnet is default
                cmd.extend(["--model", model])

            # Add isolation to system prompt to override parent CLAUDE.md context
            isolation_system = (
                f'CRITICAL: You are working ONLY on project "{project.name}". '
                f'IGNORE all context about other projects (backpack_hero, babylon, studio, hamster, etc. - except the one you are working on). '
                f'Focus ONLY on files within {project.path}.'
            )
            cmd.extend(["--append-system-prompt", isolation_system])

            # Use Popen for better process control and proper timeout killing
            timeout_seconds = 300  # 5 minutes

            # On Windows, use CREATE_NEW_PROCESS_GROUP for proper tree killing
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0

            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=project.path,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=creationflags
            )

            try:
                stdout, stderr = proc.communicate(input=prompt, timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                # Kill entire process tree
                self._kill_process_tree(proc.pid)
                proc.kill()
                proc.wait()
                return {
                    "success": False,
                    "error": f"Task timed out ({timeout_seconds // 60} minutes)"
                }

            if proc.returncode == 0:
                # Post-validation: check boundary violations
                if enforce_isolation:
                    violations = validate_changes(project.path, isolation_config)
                    if violations:
                        logger.warning(f"Isolation violations detected: {violations}")
                        log_violation(
                            project=project.name,
                            violations=violations,
                            log_dir=self.studio_path / "logs"
                        )
                        rollback_changes(project.path)
                        return {
                            "success": False,
                            "error": f"ISOLATION_VIOLATION: {', '.join(violations)}"
                        }

                return {
                    "success": True,
                    "output": stdout
                }
            else:
                return {
                    "success": False,
                    "error": stderr or "Non-zero exit code"
                }

        except FileNotFoundError:
            return {
                "success": False,
                "error": "Claude CLI not found. Is it installed?"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _validate_project(self, project: Project) -> Dict[str, Any]:
        """
        Run validation on project (smoke test).
        Uses Claude Code for vision validation (no API key needed).
        """
        if project.engine != Engine.LOVE:
            return {"passed": True, "skipped": True}

        try:
            from tools import run_game, capture

            # Run game
            process = run_game(
                project=str(project.path),
                engine="love",
                wait=2
            )

            if not process:
                return {"passed": False, "issues": ["Failed to start game"]}

            # Capture screenshot
            screenshot_path = self.studio_path / f"validation_{project.name}.png"
            screenshot = capture(
                window=project.name,
                output=str(screenshot_path)
            )
            process.kill()

            if not screenshot:
                return {"passed": False, "issues": ["Failed to capture screenshot"]}

            # Validate with Claude Code (uses vision, no API key needed)
            return self._validate_screenshot(screenshot_path, project)

        except Exception as e:
            logger.exception(f"Validation failed: {e}")
            return {"passed": False, "issues": [str(e)]}

    def _validate_screenshot(self, screenshot_path: Path, project: Project) -> Dict[str, Any]:
        """
        Validate screenshot using Claude Code (has vision capabilities).
        """
        import shutil
        import json

        claude_cmd = shutil.which("claude") or shutil.which("claude.cmd")
        if not claude_cmd:
            return {"passed": False, "issues": ["Claude CLI not found"]}

        prompt = f'''Look at the screenshot {screenshot_path.name} and validate:
1. Is the game "{project.name}" running correctly?
2. Any errors, crashes, or black screens visible?
3. Does the UI look functional?

Respond ONLY with JSON (no markdown):
{{"passed": true/false, "explanation": "brief description", "issues": ["issue1"] or []}}'''

        try:
            result = subprocess.run(
                [claude_cmd, "--dangerously-skip-permissions"],
                input=prompt,
                cwd=self.studio_path,
                capture_output=True,
                text=True,
                timeout=60,
                shell=(sys.platform == "win32")
            )

            output = result.stdout.strip()

            # Parse JSON from response
            # Find JSON in output (may have markdown code blocks)
            if "```" in output:
                # Extract from code block
                import re
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', output, re.DOTALL)
                if match:
                    output = match.group(1)

            # Try to find raw JSON
            start = output.find("{")
            end = output.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = output[start:end]
                data = json.loads(json_str)
                return {
                    "passed": data.get("passed", False),
                    "issues": data.get("issues", []),
                    "explanation": data.get("explanation", "")
                }

            # Fallback
            return {
                "passed": "error" not in output.lower(),
                "issues": [],
                "explanation": output[:200]
            }

        except Exception as e:
            logger.exception(f"Screenshot validation failed: {e}")
            return {"passed": False, "issues": [str(e)]}

    def run_all(self, max_tasks: int = 10, analyze: bool = True) -> List[Task]:
        """
        Execute up to max_tasks from the queue.
        """
        completed = []
        for _ in range(max_tasks):
            task = self.run_once(analyze=analyze)
            if not task:
                break
            completed.append(task)

            # Stop on failure
            if task.status == TaskStatus.FAILED:
                logger.warning("Stopping due to failed task")
                break

        return completed

    def status(self) -> Dict[str, Any]:
        """Get overall status."""
        return {
            "projects": len(self._projects),
            "tasks": self.tasks.stats(),
            "workspace": str(self.workspace)
        }


# Module test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    orch = Orchestrator()

    print("Projects:")
    for p in orch.projects:
        print(f"  {p.name} ({p.engine.value})")

    print("\nStatus:", orch.status())
