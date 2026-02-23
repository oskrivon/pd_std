#!/usr/bin/env python3
"""
Ptero Dactyl Studio CLI

AI-driven game development studio.

Usage:
    ptero-studio projects              # List all projects
    ptero-studio tasks [project]       # Show task queue
    ptero-studio add <project> "task"  # Add a task
    ptero-studio run [--once]          # Execute tasks
    ptero-studio new <name> [--engine] # Create new project
    ptero-studio status                # Show overall status
"""

import argparse
import os
import sys
from pathlib import Path

# Add studio to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.orchestrator import Orchestrator
from core.project import Project, Engine, discover_projects
from core.task_db import TaskDB, Task, TaskStatus, TaskPriority, get_task_db


def safe_print(text: str):
    """Print with fallback for encoding issues."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', errors='replace').decode('ascii'))


def cmd_projects(args, orch: Orchestrator):
    """List all projects."""
    projects = orch.projects

    if not projects:
        print("No projects found")
        return 0

    print(f"Projects ({len(projects)}):\n")
    for p in projects:
        # Skip description to avoid encoding issues
        safe_print(f"  {p.name:<20} {p.engine.value:<8}")

    return 0


def cmd_tasks(args, orch: Orchestrator):
    """Show task queue."""
    db = get_task_db(Path(args.workspace) / "studio" / "tasks.db")
    project = args.project if hasattr(args, 'project') else None

    if project:
        tasks = db.tasks_by_project(project)
    else:
        tasks = db.all_tasks()

    if not tasks:
        print("No tasks")
        return 0

    # Group by status
    pending = [t for t in tasks if t.status == TaskStatus.PENDING]
    in_progress = [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]
    completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
    failed = [t for t in tasks if t.status == TaskStatus.FAILED]

    if in_progress:
        print("In Progress:")
        for t in in_progress:
            safe_print(f"  [{t.id}] {t.project}: {t.description[:60]}")
        print()

    if pending:
        print("Pending:")
        for t in sorted(pending, key=lambda x: -x.priority.value):
            prio = t.priority.name[0]  # First letter
            safe_print(f"  [{t.id}] ({prio}) {t.project}: {t.description[:60]}")
        print()

    if failed:
        print("Failed:")
        for t in failed:
            safe_print(f"  [{t.id}] {t.project}: {t.description[:60]}")
            if t.error:
                safe_print(f"         Error: {t.error[:60]}")
        print()

    if args.all and completed:
        print(f"Completed ({len(completed)}):")
        for t in completed[-5:]:  # Last 5
            safe_print(f"  [{t.id}] {t.project}: {t.description[:60]}")

    stats = db.stats()
    print(f"\nTotal: {stats['total']} (pending: {stats['pending']}, completed: {stats['completed']})")

    return 0


def cmd_add(args, orch: Orchestrator):
    """Add a task."""
    db = get_task_db(Path(args.workspace) / "studio" / "tasks.db")
    projects = {p.name: p for p in discover_projects(Path(args.workspace))}

    if args.project not in projects:
        print(f"Error: Project not found: {args.project}", file=sys.stderr)
        print(f"Available: {list(projects.keys())}", file=sys.stderr)
        return 1

    priority_map = {
        "critical": TaskPriority.CRITICAL,
        "high": TaskPriority.HIGH,
        "normal": TaskPriority.NORMAL,
        "low": TaskPriority.LOW
    }

    priority = priority_map.get(args.priority, TaskPriority.NORMAL)

    task = Task(
        project=args.project,
        description=args.task,
        priority=priority
    )
    db.add(task)

    print(f"Added task [{task.id}]: {task.description}")
    return 0


def cmd_run(args, orch: Orchestrator):
    """Execute tasks."""
    analyze = not getattr(args, 'no_analyze', False)

    if args.once:
        task = orch.run_once(validate=not args.no_validate, analyze=analyze)
        if task:
            status = task.status.value
            print(f"[{status.upper()}] {task.project}: {task.description}")
            if task.error:
                print(f"Error: {task.error}")
        else:
            print("No pending tasks")
    else:
        max_tasks = args.max or 10
        tasks = orch.run_all(max_tasks, analyze=analyze)
        print(f"Executed {len(tasks)} tasks")
        for t in tasks:
            status = "OK" if t.status.value == "completed" else "FAIL"
            print(f"  [{status}] {t.project}: {t.description[:50]}")

    return 0


def cmd_new(args, orch: Orchestrator):
    """Create new project."""
    engine = Engine(args.engine) if args.engine else Engine.LOVE

    try:
        project = Project.scaffold(args.name, engine=engine, workspace=orch.workspace)
        print(f"Created project: {project.path}")
        orch.reload_projects()
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_status(args, orch: Orchestrator):
    """Show overall status."""
    # Show project statuses if requested
    if getattr(args, 'projects', False):
        from core.project_status import print_all_statuses
        safe_print(print_all_statuses(args.workspace))
        return 0

    status = orch.status()

    print("Ptero Dactyl Studio")
    print(f"Workspace: {status['workspace']}")
    print(f"Projects: {status['projects']}")
    print()
    print("Tasks:")
    for key, value in status['tasks'].items():
        if value > 0:
            print(f"  {key}: {value}")

    return 0


def cmd_validate(args, orch: Orchestrator):
    """Validate a project (run game, screenshot, check)."""
    from tools import run_game, capture
    from core.project import Engine

    project = orch.get_project(args.project)
    if not project:
        print(f"Project not found: {args.project}", file=sys.stderr)
        return 1

    print(f"Validating {project.name}...")

    validation_dir = orch.studio_path / "validation"
    validation_dir.mkdir(exist_ok=True)

    # Handle different engines
    if project.engine == Engine.UNREAL:
        # Unreal: try to capture existing window (editor or PIE must be open)
        print("  Unreal project - attempting window capture...")
        print("  (Make sure Unreal Editor or PIE is running)")

        # Try common window titles
        for title in [project.name, "CardGame", "Unreal Editor"]:
            screenshot = capture(window=title, output=str(validation_dir / f"{project.name}.png"))
            if screenshot:
                print(f"  Screenshot: {screenshot}")
                print("  PASS: Window captured")
                return 0

        print("  SKIP: No Unreal window found")
        print("  To validate: run PIE in Unreal Editor, then run this command")
        return 0  # Not a failure, just skipped

    # LÖVE: start game, capture, kill
    print("  Starting game...")
    process = run_game(project=str(project.path), engine=project.engine.value, wait=3)

    if not process or not process.is_running():
        print("  FAIL: Could not start game")
        return 1

    # Capture to validation folder
    print("  Capturing screenshot...")
    screenshot = capture(window=project.name, output=str(validation_dir / f"{project.name}.png"))

    process.kill()

    if not screenshot:
        print("  FAIL: Could not capture screenshot")
        return 1

    print(f"  Screenshot: {screenshot}")
    print("  PASS: Game runs and screenshot captured")
    print()
    print(f"  To check visually: open {screenshot}")

    return 0


def cmd_budget(args, orch: Orchestrator):
    """Show budget status."""
    print(orch.budget.report())
    return 0


def cmd_idea(args, orch: Orchestrator):
    """Decompose an idea into tasks."""
    from core.decomposer import decompose_idea

    project = orch.get_project(args.project)
    if not project:
        print(f"Project not found: {args.project}", file=sys.stderr)
        return 1

    print(f"Decomposing idea for {project.name}...")
    print(f"  \"{args.idea}\"")
    print()

    tasks = decompose_idea(
        project=project.name,
        idea=args.idea,
        project_path=project.path,
        max_tasks=args.max_tasks
    )

    print(f"Generated {len(tasks)} tasks:")
    for i, desc in enumerate(tasks, 1):
        print(f"  {i}. {desc}")

    if not args.dry_run:
        print()
        for desc in tasks:
            task = orch.add_task(project.name, desc)
            print(f"  Added [{task.id}]: {desc[:50]}")

    return 0


def cmd_test(args, orch: Orchestrator):
    """Run tests."""
    import subprocess

    cmd = ["python", "-m", "pytest"]

    # Add markers
    if args.unit:
        cmd.extend(["-m", "not integration and not e2e"])
    elif args.integration:
        cmd.extend(["-m", "integration"])
    elif args.e2e:
        cmd.extend(["-m", "e2e"])

    # Add verbosity
    if args.verbose:
        cmd.append("-v")

    # Coverage
    if args.coverage:
        cmd.extend(["--cov=core", "--cov-report=term-missing"])

    # Specific test file or pattern
    if args.pattern:
        cmd.append(args.pattern)

    print(f"Running: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=orch.studio_path
    )

    return result.returncode


def cmd_web(args, orch: Orchestrator):
    """Start web dashboard."""
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn fastapi jinja2 python-multipart")
        return 1

    os.environ["PTERO_WORKSPACE"] = args.workspace

    print(f"Starting dashboard at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop")

    uvicorn.run(
        "web.app:app",
        host=args.host,
        port=args.port,
        reload=True,
        log_level="info"
    )
    return 0


def cmd_inbox(args, orch: Orchestrator):
    """Import tasks from markdown files or create new template."""
    from core.md_tasks import import_tasks_from_inbox, create_task_template, parse_task_md

    inbox_path = Path(args.workspace) / "studio" / args.path

    # Create new template
    if args.new:
        template_path = create_task_template(inbox_path, args.new, args.project)
        print(f"Created: {template_path}")
        print(f"Edit the file and run 'ptero-studio inbox' to import")
        return 0

    # Import tasks from inbox
    if not inbox_path.exists():
        print(f"Inbox folder not found: {inbox_path}")
        print(f"Create it or use --new to create a task template")
        return 1

    md_files = list(inbox_path.glob("*.md"))
    if not md_files:
        print(f"No .md files in {inbox_path}")
        return 0

    print(f"Found {len(md_files)} task file(s)")

    imported = 0
    for md_file in md_files:
        if md_file.name.startswith("_"):
            continue

        task = parse_task_md(md_file)
        if not task:
            print(f"  [SKIP] {md_file.name}: parse error")
            continue

        # Add to queue
        prompt = task.to_prompt()
        priority = {
            "critical": "critical",
            "high": "high",
            "normal": "normal",
            "low": "low"
        }.get(task.priority, "normal")

        prio_enum = TaskPriority[priority.upper()]

        db = get_task_db(Path(args.workspace) / "studio" / "tasks.db")
        new_task = Task(
            project=task.project,
            description=prompt,
            priority=prio_enum
        )
        db.add(new_task)

        print(f"  [OK] {task.title} -> {new_task.id}")
        imported += 1

        # Archive
        if not args.no_archive:
            archive_path = inbox_path / "archive"
            archive_path.mkdir(exist_ok=True)
            md_file.rename(archive_path / md_file.name)

    print(f"\nImported: {imported} task(s)")
    return 0


def cmd_daemon(args, orch: Orchestrator):
    """Run daemon mode (continuous execution)."""
    from core.daemon import Daemon

    daemon = Daemon(
        workspace=args.workspace,
        poll_interval=args.interval,
        validate=not args.no_validate,
        analyze=not getattr(args, 'no_analyze', False),
        max_consecutive_failures=args.max_failures,
        log_to_file=not getattr(args, 'no_log', False),
        workers=getattr(args, 'workers', 1)
    )

    daemon.run(max_tasks=args.max)
    return 0


def cmd_migrate(args, orch: Orchestrator):
    """Migrate from JSON to SQLite."""
    workspace = Path(args.workspace)
    json_path = workspace / "studio" / "tasks.json"
    db_path = workspace / "studio" / "tasks.db"

    if not json_path.exists():
        print(f"No JSON file found: {json_path}")
        return 0

    if db_path.exists() and not args.force:
        print(f"SQLite database already exists: {db_path}")
        print("Use --force to overwrite")
        return 1

    if db_path.exists():
        db_path.unlink()

    print(f"Migrating from {json_path} to {db_path}...")
    db = TaskDB.from_json(json_path, db_path)

    stats = db.stats()
    print(f"Done! Migrated {stats['total']} tasks")
    print(f"  Pending: {stats['pending']}")
    print(f"  Completed: {stats['completed']}")
    print(f"  Failed: {stats['failed']}")

    if args.archive:
        archive_path = json_path.with_suffix(".json.bak")
        json_path.rename(archive_path)
        print(f"Archived JSON to: {archive_path}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="ptero-studio",
        description="AI-driven game development studio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ptero-studio projects
  ptero-studio add backpack_hero "Add pause menu"
  ptero-studio tasks
  ptero-studio run --once
  ptero-studio new my_game --engine love
        """
    )

    parser.add_argument(
        "--workspace", "-w",
        default="C:/Ptero Dactyl Games",
        help="Workspace path"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # projects
    subparsers.add_parser("projects", help="List all projects")

    # tasks
    tasks_parser = subparsers.add_parser("tasks", help="Show task queue")
    tasks_parser.add_argument("project", nargs="?", help="Filter by project")
    tasks_parser.add_argument("--all", "-a", action="store_true", help="Show completed tasks")

    # add
    add_parser = subparsers.add_parser("add", help="Add a task")
    add_parser.add_argument("project", help="Project name")
    add_parser.add_argument("task", help="Task description")
    add_parser.add_argument(
        "--priority", "-p",
        choices=["critical", "high", "normal", "low"],
        default="normal"
    )

    # run
    run_parser = subparsers.add_parser("run", help="Execute tasks")
    run_parser.add_argument("--once", action="store_true", help="Execute one task")
    run_parser.add_argument("--max", type=int, help="Max tasks to execute")
    run_parser.add_argument("--no-validate", action="store_true", help="Skip validation")
    run_parser.add_argument("--no-analyze", action="store_true", help="Skip Opus analysis")

    # new
    new_parser = subparsers.add_parser("new", help="Create new project")
    new_parser.add_argument("name", help="Project name")
    new_parser.add_argument("--engine", "-e", choices=["love", "unreal"], default="love")

    # status
    status_parser = subparsers.add_parser("status", help="Show overall status")
    status_parser.add_argument("--projects", "-p", action="store_true", help="Show all project statuses")

    # validate
    validate_parser = subparsers.add_parser("validate", help="Validate a project")
    validate_parser.add_argument("project", help="Project name")

    # budget
    subparsers.add_parser("budget", help="Show budget status")

    # idea
    idea_parser = subparsers.add_parser("idea", help="Decompose idea into tasks")
    idea_parser.add_argument("project", help="Project name")
    idea_parser.add_argument("idea", help="High-level idea to decompose")
    idea_parser.add_argument("--max-tasks", type=int, default=5, help="Max tasks to generate")
    idea_parser.add_argument("--dry-run", action="store_true", help="Show tasks without adding")

    # test
    test_parser = subparsers.add_parser("test", help="Run tests")
    test_parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    test_parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    test_parser.add_argument("--e2e", action="store_true", help="Run e2e tests only")
    test_parser.add_argument("--coverage", "-c", action="store_true", help="Run with coverage")
    test_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    test_parser.add_argument("pattern", nargs="?", help="Test file or pattern")

    # daemon
    daemon_parser = subparsers.add_parser("daemon", help="Run continuous mode")
    daemon_parser.add_argument("--max", type=int, help="Max tasks before stopping")
    daemon_parser.add_argument("--interval", type=int, default=10, help="Poll interval (seconds)")
    daemon_parser.add_argument("--no-validate", action="store_true", help="Skip validation")
    daemon_parser.add_argument("--no-analyze", action="store_true", help="Skip Opus analysis")
    daemon_parser.add_argument("--max-failures", type=int, default=3, help="Stop after N consecutive failures")
    daemon_parser.add_argument("--no-log", action="store_true", help="Disable file logging")
    daemon_parser.add_argument("--workers", "-w", type=int, default=1, help="Parallel workers (1-4, default 1)")

    # web - dashboard
    web_parser = subparsers.add_parser("web", help="Start web dashboard")
    web_parser.add_argument("--port", type=int, default=8000, help="Port (default 8000)")
    web_parser.add_argument("--host", default="127.0.0.1", help="Host (default 127.0.0.1)")

    # inbox - markdown task import
    inbox_parser = subparsers.add_parser("inbox", help="Import tasks from markdown files")
    inbox_parser.add_argument("--path", default="tasks_inbox", help="Inbox folder path")
    inbox_parser.add_argument("--no-archive", action="store_true", help="Don't move processed files to archive")
    inbox_parser.add_argument("--new", metavar="TITLE", help="Create new task template")
    inbox_parser.add_argument("--project", default="backpack_hero", help="Project for new template")

    # migrate - JSON to SQLite migration
    migrate_parser = subparsers.add_parser("migrate", help="Migrate tasks from JSON to SQLite")
    migrate_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing database")
    migrate_parser.add_argument("--archive", "-a", action="store_true", help="Archive JSON file after migration")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Initialize orchestrator
    orch = Orchestrator(workspace=args.workspace)

    # Dispatch command
    commands = {
        "projects": cmd_projects,
        "tasks": cmd_tasks,
        "add": cmd_add,
        "run": cmd_run,
        "new": cmd_new,
        "status": cmd_status,
        "validate": cmd_validate,
        "budget": cmd_budget,
        "idea": cmd_idea,
        "test": cmd_test,
        "daemon": cmd_daemon,
        "inbox": cmd_inbox,
        "web": cmd_web,
        "migrate": cmd_migrate
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args, orch)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
