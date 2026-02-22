"""
Daemon Mode

Continuous task execution for Ptero Dactyl Studio.
Runs until no tasks left or interrupted.

Usage:
    from core.daemon import Daemon

    daemon = Daemon(workspace="C:/Ptero Dactyl Games")
    daemon.run()  # Runs until empty or Ctrl+C

Logs are written to:
    - Console (always)
    - studio/logs/daemon.log (daily rotation)
    - studio/logs/tasks.log (task details)
"""

import signal
import sys
import time
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from .orchestrator import Orchestrator
from .logging_config import setup_logging, TaskLogger, get_logger

logger = get_logger("daemon")


class Daemon:
    """
    Continuous task executor.
    """

    def __init__(
        self,
        workspace: str | Path = "C:/Ptero Dactyl Games",
        poll_interval: int = 10,  # seconds between checks when idle
        validate: bool = True,
        analyze: bool = True,  # Use Opus to analyze tasks first
        max_consecutive_failures: int = 3,
        log_to_file: bool = True,
        workers: int = 1  # Number of parallel workers (1 = sequential)
    ):
        self.workspace = Path(workspace)
        self.poll_interval = poll_interval
        self.validate = validate
        self.analyze = analyze
        self.max_consecutive_failures = max_consecutive_failures
        self.workers = workers

        # Setup logging
        self.log_dir = self.workspace / "studio" / "logs"
        if log_to_file:
            setup_logging(log_dir=self.log_dir)
            self.task_logger = TaskLogger(self.log_dir)
        else:
            setup_logging()
            self.task_logger = None

        self.orch = Orchestrator(workspace=workspace)
        self._running = False
        self._consecutive_failures = 0

        # Stats
        self.stats = {
            "started_at": None,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_runtime": 0
        }

    def run(self, max_tasks: Optional[int] = None) -> dict:
        """
        Run daemon until:
        - No more tasks
        - max_tasks reached
        - Interrupted (Ctrl+C)
        - Too many consecutive failures

        Returns stats dict.
        """
        self._running = True
        self._setup_signal_handlers()

        self.stats["started_at"] = datetime.now().isoformat()
        tasks_executed = 0

        logger.info(f"Daemon started at {self.stats['started_at']}")
        logger.info(f"Workspace: {self.workspace}")
        logger.info(f"Workers: {self.workers}")
        print(f"Daemon started at {self.stats['started_at']}")

        # Use parallel execution if workers > 1
        if self.workers > 1:
            return self._run_parallel(max_tasks)
        print(f"Workspace: {self.workspace}")
        print(f"Press Ctrl+C to stop\n")

        try:
            while self._running:
                # Check task queue
                pending = self.orch.tasks.stats()["pending"]

                if pending == 0:
                    print(f"[{self._timestamp()}] No pending tasks, waiting {self.poll_interval}s...")
                    time.sleep(self.poll_interval)

                    # Reload to check for new tasks
                    self.orch.tasks.reload()
                    continue

                # Execute one task
                print(f"[{self._timestamp()}] {pending} pending tasks, executing...")
                task = self.orch.run_once(validate=self.validate, analyze=self.analyze)

                if task:
                    tasks_executed += 1
                    task_duration = time.time() - time.time()  # Will be calculated properly

                    if task.status.value == "completed":
                        self.stats["tasks_completed"] += 1
                        self._consecutive_failures = 0
                        logger.info(f"[OK] {task.project}: {task.description[:50]}")
                        print(f"  [OK] {task.project}: {task.description[:50]}")

                        # Log to task file
                        if self.task_logger:
                            self.task_logger.log_task(
                                task_id=task.id,
                                project=task.project,
                                description=task.description,
                                status="completed",
                                duration=0,  # TODO: get actual duration from orchestrator
                                output=task.result
                            )
                    else:
                        self.stats["tasks_failed"] += 1
                        self._consecutive_failures += 1
                        logger.warning(f"[FAIL] {task.project}: {task.description[:50]} - {task.error}")
                        print(f"  [FAIL] {task.project}: {task.description[:50]}")
                        if task.error:
                            print(f"         Error: {task.error[:80]}")

                        # Log failure to task file
                        if self.task_logger:
                            self.task_logger.log_task(
                                task_id=task.id,
                                project=task.project,
                                description=task.description,
                                status="failed",
                                duration=0,
                                error=task.error
                            )

                        # Check failure threshold
                        if self._consecutive_failures >= self.max_consecutive_failures:
                            print(f"\n[STOP] {self.max_consecutive_failures} consecutive failures, stopping")
                            break

                # Check max_tasks limit
                if max_tasks and tasks_executed >= max_tasks:
                    print(f"\n[STOP] Reached max_tasks limit ({max_tasks})")
                    break

        except KeyboardInterrupt:
            print("\n[STOP] Interrupted by user")
        finally:
            self._running = False
            self.stats["total_runtime"] = tasks_executed

        return self._print_summary()

    def stop(self):
        """Stop the daemon gracefully."""
        self._running = False

    def _setup_signal_handlers(self):
        """Setup graceful shutdown on signals."""
        def handler(signum, frame):
            print(f"\nReceived signal {signum}, shutting down...")
            self.stop()

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def _run_parallel(self, max_tasks: Optional[int] = None) -> dict:
        """Run with parallel workers."""
        from .parallel import ParallelExecutor

        print(f"Workspace: {self.workspace}")
        print(f"Workers: {self.workers}")
        print(f"Press Ctrl+C to stop\n")

        try:
            executor = ParallelExecutor(
                workspace=self.workspace,
                workers=self.workers,
                analyze=self.analyze,
                validate=self.validate
            )

            while self._running:
                # Check for pending tasks
                pending = self.orch.tasks.stats()["pending"]

                if pending == 0:
                    print(f"[{self._timestamp()}] No pending tasks, waiting {self.poll_interval}s...")
                    time.sleep(self.poll_interval)
                    self.orch.tasks.reload()
                    continue

                # Run batch of tasks
                batch_size = min(pending, max_tasks or 100)
                results = executor.run(max_tasks=batch_size)

                for r in results:
                    if r.success:
                        self.stats["tasks_completed"] += 1
                    else:
                        self.stats["tasks_failed"] += 1

                # Check if done
                if max_tasks:
                    total = self.stats["tasks_completed"] + self.stats["tasks_failed"]
                    if total >= max_tasks:
                        break

        except KeyboardInterrupt:
            print("\n[STOP] Interrupted by user")
        finally:
            self._running = False

        return self._print_summary()

    def _timestamp(self) -> str:
        """Current timestamp for logging."""
        return datetime.now().strftime("%H:%M:%S")

    def _print_summary(self) -> dict:
        """Print and return summary stats."""
        print("\n" + "="*50)
        print("Daemon Summary")
        print("="*50)
        print(f"Started: {self.stats['started_at']}")
        print(f"Completed: {self.stats['tasks_completed']}")
        print(f"Failed: {self.stats['tasks_failed']}")
        print(f"Total: {self.stats['tasks_completed'] + self.stats['tasks_failed']}")
        print("="*50)

        return self.stats


# CLI entry point
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    daemon = Daemon()
    daemon.run()
