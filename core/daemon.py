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
import time
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from .task_db import TaskDB, Task, TaskStatus, TaskPriority, get_task_db
from .project import discover_projects, Project
from .logging_config import setup_logging, TaskLogger, get_logger
from .analyzer import analyze_task, TaskType

logger = get_logger("daemon")


class Daemon:
    """
    Continuous task executor.

    Uses SQLite-based TaskDB for thread-safe task management.
    No more reload() needed - all workers share the same DB.
    """

    def __init__(
        self,
        workspace: str | Path = "C:/Ptero Dactyl Games",
        poll_interval: int = 10,
        validate: bool = True,
        analyze: bool = True,
        max_consecutive_failures: int = 3,
        log_to_file: bool = True,
        workers: int = 1,
        reset_stuck: bool = True
    ):
        self.workspace = Path(workspace)
        self.poll_interval = poll_interval
        self.validate = validate
        self.analyze = analyze
        self.max_consecutive_failures = max_consecutive_failures
        self.workers = min(workers, 4)  # Cap at 4
        self.reset_stuck_on_start = reset_stuck

        # Setup logging
        self.log_dir = self.workspace / "studio" / "logs"
        if log_to_file:
            setup_logging(log_dir=self.log_dir)
            self.task_logger = TaskLogger(self.log_dir)
        else:
            setup_logging()
            self.task_logger = None

        # Shared TaskDB (SQLite)
        self.db = get_task_db(self.workspace / "studio" / "tasks.db")

        # Load projects
        self._projects = {p.name: p for p in discover_projects(self.workspace)}

        self._running = False
        self._consecutive_failures = 0

        # Stats
        self.stats = {
            "started_at": None,
            "tasks_completed": 0,
            "tasks_failed": 0,
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

        # Reset stuck tasks from previous crashed runs (optional)
        if self.reset_stuck_on_start:
            self.db.reset_stuck()

        self.stats["started_at"] = datetime.now().isoformat()
        tasks_executed = 0

        logger.info(f"Daemon started at {self.stats['started_at']}")
        logger.info(f"Workspace: {self.workspace}")
        logger.info(f"Workers: {self.workers}")
        logger.info(f"Projects: {list(self._projects.keys())}")

        print(f"Daemon started at {self.stats['started_at']}")
        print(f"Workspace: {self.workspace}")
        print(f"Workers: {self.workers}")
        print(f"Press Ctrl+C to stop\n")

        try:
            if self.workers > 1:
                return self._run_parallel(max_tasks)
            else:
                return self._run_sequential(max_tasks)

        except KeyboardInterrupt:
            print("\n[STOP] Interrupted by user")
        finally:
            self._running = False

        return self._print_summary()

    def _run_sequential(self, max_tasks: Optional[int] = None) -> dict:
        """Run tasks one at a time."""
        tasks_executed = 0

        while self._running:
            stats = self.db.stats()

            if stats["pending"] == 0:
                print(f"[{self._timestamp()}] No pending tasks, waiting {self.poll_interval}s...")
                time.sleep(self.poll_interval)
                continue

            # Pop and execute one task
            task = self.db.pop()
            if not task:
                continue

            print(f"[{self._timestamp()}] Executing: [{task.project}] {task.description[:50]}")
            success = self._execute_task(task)
            tasks_executed += 1

            if success:
                self.stats["tasks_completed"] += 1
                self._consecutive_failures = 0
                print(f"  [OK] {task.project}: {task.description[:50]}")
            else:
                self.stats["tasks_failed"] += 1
                self._consecutive_failures += 1
                print(f"  [FAIL] {task.project}: {task.description[:50]}")

                if self._consecutive_failures >= self.max_consecutive_failures:
                    print(f"\n[STOP] {self.max_consecutive_failures} consecutive failures")
                    break

            if max_tasks and tasks_executed >= max_tasks:
                print(f"\n[STOP] Reached max_tasks limit ({max_tasks})")
                break

        return self._print_summary()

    def _run_parallel(self, max_tasks: Optional[int] = None) -> dict:
        """Run tasks in parallel across multiple workers."""
        tasks_executed = 0
        active_projects = set()  # Track which projects are being worked on

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {}

            while self._running:
                # Submit new tasks up to worker count
                while len(futures) < self.workers:
                    if max_tasks and tasks_executed >= max_tasks:
                        break

                    # Pop task, excluding active projects
                    task = self.db.pop(exclude_projects=active_projects)
                    if not task:
                        break

                    active_projects.add(task.project)
                    future = executor.submit(self._execute_task, task)
                    futures[future] = task
                    tasks_executed += 1

                    logger.info(f"[Worker] Started: {task.project}/{task.description[:30]}")
                    print(f"[{self._timestamp()}] Started: [{task.project}] {task.description[:40]}")

                # If no tasks running and none to submit, check for more
                if not futures:
                    stats = self.db.stats()
                    if stats["pending"] == 0:
                        print(f"[{self._timestamp()}] No pending tasks, waiting {self.poll_interval}s...")
                        time.sleep(self.poll_interval)
                        continue
                    else:
                        # There are pending tasks but all projects are locked
                        # Wait for a task to complete
                        time.sleep(1)
                        continue

                # Wait for any task to complete
                for future in as_completed(futures, timeout=5):
                    task = futures.pop(future)
                    active_projects.discard(task.project)

                    try:
                        success = future.result()
                        if success:
                            self.stats["tasks_completed"] += 1
                            print(f"  [OK] {task.project}: {task.description[:40]}")
                        else:
                            self.stats["tasks_failed"] += 1
                            print(f"  [FAIL] {task.project}: {task.description[:40]}")
                    except Exception as e:
                        self.stats["tasks_failed"] += 1
                        logger.exception(f"Worker error: {e}")
                        print(f"  [ERROR] {task.project}: {e}")

                    break  # Process one at a time to allow new submissions

                # Check completion
                if max_tasks and tasks_executed >= max_tasks and not futures:
                    break

        return self._print_summary()

    def _execute_task(self, task: Task) -> bool:
        """
        Execute a single task.

        Returns True on success, False on failure.
        """
        project = self._projects.get(task.project)
        if not project:
            self.db.fail(task.id, f"Project not found: {task.project}")
            return False

        # Analyze task if enabled
        if self.analyze:
            analysis_result = self._analyze_and_route(task, project)
            if analysis_result is not None:
                # Task was handled by analyzer (decomposed or rejected)
                return analysis_result

        start_time = time.time()

        try:
            result = self._run_claude_code(task, project)
            duration = time.time() - start_time

            if result.get("success"):
                self.db.complete(task.id, result.get("output", ""))

                if self.task_logger:
                    self.task_logger.log_task(
                        task_id=task.id,
                        project=task.project,
                        description=task.description,
                        status="completed",
                        duration=duration,
                        output=result.get("output")
                    )
                return True
            else:
                error = result.get("error", "Unknown error")
                self.db.fail(task.id, error)

                if self.task_logger:
                    self.task_logger.log_task(
                        task_id=task.id,
                        project=task.project,
                        description=task.description,
                        status="failed",
                        duration=duration,
                        error=error
                    )
                return False

        except Exception as e:
            duration = time.time() - start_time
            error = str(e)
            self.db.fail(task.id, error)
            logger.exception(f"Task execution failed: {e}")

            if self.task_logger:
                self.task_logger.log_task(
                    task_id=task.id,
                    project=task.project,
                    description=task.description,
                    status="failed",
                    duration=duration,
                    error=error
                )
            return False

    def _analyze_and_route(self, task: Task, project: Project) -> Optional[bool]:
        """
        Analyze task and route appropriately.

        Returns:
            None - task should be executed normally
            True - task was handled (decomposed into subtasks)
            False - task was rejected (UNCLEAR)
        """
        try:
            logger.info(f"Analyzing task {task.id}: {task.description[:50]}...")
            print(f"  [ANALYZE] {task.description[:50]}...")

            result = analyze_task(
                project=task.project,
                description=task.description,
                project_path=project.path,
                project_engine=project.engine.value
            )

            logger.info(f"Analysis result: {result.task_type.value} (confidence: {result.confidence})")

            if result.task_type == TaskType.UNCLEAR:
                # Reject task - needs clarification
                feedback = result.feedback or "Task is unclear, please provide more details"
                self.db.fail(task.id, f"UNCLEAR: {feedback}")
                print(f"  [REJECT] {feedback}")
                return False

            elif result.task_type == TaskType.COMPLEX and result.subtasks:
                # Decompose into subtasks
                print(f"  [DECOMPOSE] Breaking into {len(result.subtasks)} subtasks:")

                for i, subtask_desc in enumerate(result.subtasks, 1):
                    subtask = Task(
                        project=task.project,
                        description=subtask_desc,
                        priority=task.priority,
                        parent_id=task.id
                    )
                    self.db.add(subtask)
                    print(f"    {i}. {subtask_desc[:60]}...")

                # Mark parent as completed (subtasks will be executed)
                self.db.complete(task.id, f"Decomposed into {len(result.subtasks)} subtasks")
                return True

            else:
                # SIMPLE or CLEAR - execute normally
                logger.info(f"Task {task.id} classified as {result.task_type.value}, executing...")
                return None

        except Exception as e:
            logger.warning(f"Analysis failed for task {task.id}: {e}, executing without analysis")
            print(f"  [WARN] Analysis failed: {e}, executing directly")
            return None

    def _run_claude_code(self, task: Task, project: Project) -> dict:
        """Run Claude Code to execute the task with idle timeout."""
        import subprocess
        import shutil
        import sys
        import threading
        from queue import Queue, Empty

        claude_cmd = shutil.which("claude") or shutil.which("claude.cmd")
        if not claude_cmd:
            return {"success": False, "error": "Claude CLI not found"}

        # Build prompt
        prompt = f"""You are working on the "{project.name}" project ({project.engine.value} engine).

## IMPORTANT: Read documentation first

BEFORE starting, read:
1. `CLAUDE.md` - project instructions and architecture
2. `docs/RUNBOOK.md` - known issues and solutions
3. `docs/PROGRESS.md` - what was already done

## If something doesn't work

When encountering problems:
1. FIRST check docs/ for existing solutions
2. If found - apply it
3. If not found - solve and DOCUMENT the solution

## TASK

{task.description}

## INSTRUCTIONS

1. Read documentation first
2. Make minimal, focused changes
3. Commit with descriptive message
4. Document new solutions in docs/PROGRESS.md

DO NOT ask for clarification - make reasonable assumptions and proceed.
"""

        cmd = [claude_cmd, "--print", "--dangerously-skip-permissions"]
        logger.info(f"Claude command: {cmd}")
        logger.info(f"Working dir: {project.path}")

        # Timeout settings
        idle_timeout = 300  # Kill if no output for 5 minutes (Claude needs time for complex tasks)
        max_timeout = 1200  # Absolute max 20 minutes

        def reader_thread(pipe, queue, name):
            """Read from pipe and put lines into queue."""
            logger.info(f"Reader thread {name} started")
            try:
                for line in iter(pipe.readline, ''):
                    if line:
                        logger.debug(f"Reader {name}: {line[:50]}...")
                        queue.put((name, line))
                pipe.close()
                logger.info(f"Reader thread {name} finished")
            except Exception as e:
                logger.error(f"Reader thread {name} error: {e}")
                queue.put(('error', str(e)))

        try:
            # Use CREATE_NEW_PROCESS_GROUP on Windows for proper killing
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

            logger.info(f"Starting subprocess with creationflags={creationflags}")
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
            logger.info(f"Process started with PID: {proc.pid}")

            # Send prompt and close stdin
            logger.info(f"Sending prompt ({len(prompt)} chars)...")
            proc.stdin.write(prompt)
            proc.stdin.close()
            logger.info("Prompt sent, stdin closed")

            # Start reader threads
            output_queue = Queue()
            stdout_thread = threading.Thread(
                target=reader_thread,
                args=(proc.stdout, output_queue, 'stdout'),
                daemon=True
            )
            stderr_thread = threading.Thread(
                target=reader_thread,
                args=(proc.stderr, output_queue, 'stderr'),
                daemon=True
            )
            stdout_thread.start()
            stderr_thread.start()

            # Collect output with idle timeout
            stdout_lines = []
            stderr_lines = []
            start_time = time.time()
            last_activity = time.time()

            while proc.poll() is None:
                elapsed = time.time() - start_time
                idle_time = time.time() - last_activity

                # Check absolute max timeout
                if elapsed > max_timeout:
                    self._kill_process_tree(proc.pid)
                    proc.kill()
                    return {"success": False, "error": f"Task timed out (max {max_timeout // 60} minutes)"}

                # Check idle timeout
                if idle_time > idle_timeout:
                    self._kill_process_tree(proc.pid)
                    proc.kill()
                    return {"success": False, "error": f"Task idle timeout ({idle_timeout}s no output)"}

                # Read available output
                try:
                    source, line = output_queue.get(timeout=1.0)
                    last_activity = time.time()
                    if source == 'stdout':
                        stdout_lines.append(line)
                    elif source == 'stderr':
                        stderr_lines.append(line)
                except Empty:
                    continue

            # Process finished, drain remaining output
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)

            while not output_queue.empty():
                try:
                    source, line = output_queue.get_nowait()
                    if source == 'stdout':
                        stdout_lines.append(line)
                    elif source == 'stderr':
                        stderr_lines.append(line)
                except Empty:
                    break

            stdout = ''.join(stdout_lines)
            stderr = ''.join(stderr_lines)

            if proc.returncode == 0:
                return {"success": True, "output": stdout}
            else:
                return {"success": False, "error": stderr or "Non-zero exit code"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _kill_process_tree(self, pid: int):
        """Kill a process and all its children."""
        import subprocess
        import sys

        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=10
                )
            except Exception as e:
                logger.warning(f"Failed to kill process tree {pid}: {e}")
        else:
            import os
            import signal as sig
            try:
                os.killpg(os.getpgid(pid), sig.SIGTERM)
            except Exception as e:
                logger.warning(f"Failed to kill process group {pid}: {e}")

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

    def _timestamp(self) -> str:
        """Current timestamp for logging."""
        return datetime.now().strftime("%H:%M:%S")

    def _print_summary(self) -> dict:
        """Print and return summary stats."""
        print("\n" + "=" * 50)
        print("Daemon Summary")
        print("=" * 50)
        print(f"Started: {self.stats['started_at']}")
        print(f"Completed: {self.stats['tasks_completed']}")
        print(f"Failed: {self.stats['tasks_failed']}")
        print(f"Total: {self.stats['tasks_completed'] + self.stats['tasks_failed']}")
        print("=" * 50)

        return self.stats


# CLI entry point
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    daemon = Daemon()
    daemon.run()
