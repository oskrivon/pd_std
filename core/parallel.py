"""
Parallel Worker Execution

Runs multiple Claude Code workers simultaneously.
Each worker handles tasks from different projects to avoid conflicts.

Usage:
    from core.parallel import ParallelExecutor

    executor = ParallelExecutor(workspace="./workspace", workers=3)
    results = executor.run(max_tasks=10)
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from .orchestrator import Orchestrator
from .task_queue import Task, TaskStatus
from .logging_config import get_logger, TaskLogger

logger = get_logger("parallel")


@dataclass
class WorkerResult:
    """Result from a worker execution."""
    task_id: str
    project: str
    description: str
    success: bool
    duration: float
    error: Optional[str] = None


class ParallelExecutor:
    """
    Execute tasks using multiple parallel workers.
    Each worker processes tasks from different projects.
    """

    def __init__(
        self,
        workspace: str | Path = "./workspace",
        workers: int = 2,
        analyze: bool = True,
        validate: bool = False
    ):
        self.workspace = Path(workspace)
        self.workers = min(workers, 4)  # Cap at 4 to avoid rate limits
        self.analyze = analyze
        self.validate = validate

        self.orch = Orchestrator(workspace=workspace)
        self.task_logger = TaskLogger(self.workspace / "studio" / "logs")

        # Stats
        self.stats = {
            "started_at": None,
            "completed": 0,
            "failed": 0,
            "total_duration": 0
        }

    def run(self, max_tasks: Optional[int] = None) -> List[WorkerResult]:
        """
        Run parallel execution.

        Args:
            max_tasks: Maximum total tasks to execute

        Returns:
            List of WorkerResult
        """
        self.stats["started_at"] = datetime.now().isoformat()
        results: List[WorkerResult] = []
        tasks_executed = 0

        logger.info(f"Starting parallel execution with {self.workers} workers")
        print(f"Parallel execution: {self.workers} workers")

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {}

            while True:
                # Submit new tasks up to worker count
                while len(futures) < self.workers:
                    if max_tasks and tasks_executed >= max_tasks:
                        break

                    task = self.orch.tasks.pop_for_parallel()
                    if not task:
                        break

                    future = executor.submit(self._execute_task, task)
                    futures[future] = task
                    tasks_executed += 1
                    logger.info(f"[Worker] Started: {task.project}/{task.description[:30]}")

                if not futures:
                    # No running tasks and no more tasks to submit
                    break

                # Wait for any task to complete (no timeout exception)
                done, _ = wait(futures.keys(), timeout=5, return_when=FIRST_COMPLETED)
                done_futures = list(done)

                # Process completed tasks
                for future in done_futures:
                    task = futures.pop(future)
                    try:
                        result = future.result()
                        results.append(result)

                        if result.success:
                            self.stats["completed"] += 1
                            print(f"  [OK] {result.project}: {result.description[:40]}")
                        else:
                            self.stats["failed"] += 1
                            print(f"  [FAIL] {result.project}: {result.description[:40]}")

                        self.stats["total_duration"] += result.duration

                    except Exception as e:
                        logger.exception(f"Worker failed: {e}")
                        self.stats["failed"] += 1

                # Check if we should stop
                if max_tasks and tasks_executed >= max_tasks and not futures:
                    break

        self._print_summary()
        return results

    def _execute_task(self, task: Task) -> WorkerResult:
        """Execute a single task (runs in worker thread)."""
        start_time = time.time()
        project = self.orch.get_project(task.project)

        if not project:
            self.orch.tasks.fail(task.id, f"Project not found: {task.project}")
            self.orch.tasks.save()
            return WorkerResult(
                task_id=task.id,
                project=task.project,
                description=task.description,
                success=False,
                duration=time.time() - start_time,
                error="Project not found"
            )

        try:
            # Use orchestrator's execute method
            result = self.orch._execute_task(task, project)
            duration = time.time() - start_time

            if result.get("success"):
                self.orch.tasks.complete(task.id, result.get("output", ""))
                self.orch.tasks.save()

                self.task_logger.log_task(
                    task_id=task.id,
                    project=task.project,
                    description=task.description,
                    status="completed",
                    duration=duration,
                    output=result.get("output")
                )

                return WorkerResult(
                    task_id=task.id,
                    project=task.project,
                    description=task.description,
                    success=True,
                    duration=duration
                )
            else:
                error = result.get("error", "Unknown error")
                self.orch.tasks.fail(task.id, error)
                self.orch.tasks.save()

                self.task_logger.log_task(
                    task_id=task.id,
                    project=task.project,
                    description=task.description,
                    status="failed",
                    duration=duration,
                    error=error
                )

                return WorkerResult(
                    task_id=task.id,
                    project=task.project,
                    description=task.description,
                    success=False,
                    duration=duration,
                    error=error
                )

        except Exception as e:
            duration = time.time() - start_time
            error = str(e)
            self.orch.tasks.fail(task.id, error)
            self.orch.tasks.save()

            logger.exception(f"Task execution failed: {e}")

            return WorkerResult(
                task_id=task.id,
                project=task.project,
                description=task.description,
                success=False,
                duration=duration,
                error=error
            )

    def _print_summary(self):
        """Print execution summary."""
        print("\n" + "=" * 50)
        print("Parallel Execution Summary")
        print("=" * 50)
        print(f"Workers: {self.workers}")
        print(f"Completed: {self.stats['completed']}")
        print(f"Failed: {self.stats['failed']}")
        print(f"Total duration: {self.stats['total_duration']:.1f}s")
        if self.stats['completed'] + self.stats['failed'] > 0:
            avg = self.stats['total_duration'] / (self.stats['completed'] + self.stats['failed'])
            print(f"Avg per task: {avg:.1f}s")
        print("=" * 50)


# CLI entry point
if __name__ == "__main__":
    from .logging_config import setup_logging
    setup_logging()

    executor = ParallelExecutor(workers=2)
    executor.run(max_tasks=5)
