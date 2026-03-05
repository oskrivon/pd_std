"""
Ptero Studio Dashboard

FastAPI + HTMX web interface for task management.

Usage:
    cd studio && uvicorn web.app:app --reload --port 8000
    # or
    ptero-studio web
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.task_db import TaskDB, Task, TaskStatus, TaskPriority, get_task_db
from core.project import discover_projects

# Globals
WORKSPACE = Path(os.environ.get("PTERO_WORKSPACE", "C:/Ptero Dactyl Games"))
db: Optional[TaskDB] = None
projects: dict = {}
daemon_process = None
log_subscribers: List[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup."""
    global db, projects

    # Initialize shared TaskDB
    db = get_task_db(WORKSPACE / "studio" / "tasks.db")

    # Load projects
    projects = {p.name: p for p in discover_projects(WORKSPACE)}

    yield

    # Cleanup
    pass


app = FastAPI(title="Ptero Studio", lifespan=lifespan)

# Static files and templates
web_dir = Path(__file__).parent
# app.mount("/static", StaticFiles(directory=web_dir / "static"), name="static")
templates = Jinja2Templates(directory=web_dir / "templates")


# ============ Pages ============

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard."""
    from datetime import datetime

    tasks = db.all_tasks()
    stats = db.stats()

    pending = [t for t in tasks if t.status == TaskStatus.PENDING]
    in_progress = [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]
    completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
    failed = [t for t in tasks if t.status == TaskStatus.FAILED]

    # Calculate elapsed time for in-progress tasks
    now = datetime.now()
    for task in in_progress:
        if task.started_at:
            try:
                started = datetime.fromisoformat(task.started_at)
                task.elapsed_seconds = (now - started).total_seconds()
            except:
                task.elapsed_seconds = 0
        else:
            task.elapsed_seconds = 0

    return templates.TemplateResponse("index.html", {
        "request": request,
        "projects": list(projects.values()),
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed[-10:],
        "failed": failed[-5:],
        "stats": stats,
        "daemon_running": daemon_process is not None and daemon_process.poll() is None
    })


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request, project: Optional[str] = None):
    """Tasks list page."""
    if project:
        tasks = db.tasks_by_project(project)
    else:
        tasks = db.all_tasks()

    return templates.TemplateResponse("tasks.html", {
        "request": request,
        "tasks": sorted(tasks, key=lambda t: (t.status.value, -t.priority.value)),
        "projects": list(projects.values()),
        "selected_project": project
    })


@app.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request):
    """Projects list."""
    return templates.TemplateResponse("projects.html", {
        "request": request,
        "projects": list(projects.values())
    })


# ============ HTMX Partials ============

@app.get("/partials/tasks-list", response_class=HTMLResponse)
async def tasks_list_partial(request: Request, project: Optional[str] = None):
    """Tasks list partial for HTMX updates."""
    tasks = db.pending_tasks()
    if project:
        tasks = [t for t in tasks if t.project == project]

    return templates.TemplateResponse("partials/tasks_list.html", {
        "request": request,
        "tasks": sorted(tasks, key=lambda t: -t.priority.value)
    })


@app.get("/partials/stats", response_class=HTMLResponse)
async def stats_partial(request: Request):
    """Stats partial for polling updates."""
    stats = db.stats()

    return templates.TemplateResponse("partials/stats.html", {
        "request": request,
        "stats": stats,
        "daemon_running": daemon_process is not None and daemon_process.poll() is None
    })


@app.get("/partials/in-progress", response_class=HTMLResponse)
async def in_progress_partial(request: Request):
    """In-progress tasks partial for polling updates."""
    from datetime import datetime

    tasks = db.all_tasks()
    in_progress = [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]

    # Calculate elapsed time for each task
    now = datetime.now()
    for task in in_progress:
        if task.started_at:
            try:
                started = datetime.fromisoformat(task.started_at)
                task.elapsed_seconds = (now - started).total_seconds()
            except:
                task.elapsed_seconds = 0
        else:
            task.elapsed_seconds = 0

    return templates.TemplateResponse("partials/in_progress.html", {
        "request": request,
        "in_progress": in_progress
    })


# ============ Actions ============

@app.post("/tasks/add", response_class=HTMLResponse)
async def add_task(
    request: Request,
    project: str = Form(...),
    description: str = Form(...),
    priority: str = Form("normal"),
    refs: List[UploadFile] = File(default=[])
):
    """Add a new task."""
    # Handle file uploads
    ref_paths = []
    if refs and refs[0].filename:
        refs_dir = WORKSPACE / "studio" / "tasks_inbox" / "refs"
        refs_dir.mkdir(parents=True, exist_ok=True)

        for ref in refs:
            if ref.filename:
                ref_path = refs_dir / ref.filename
                content = await ref.read()
                ref_path.write_bytes(content)
                ref_paths.append(str(ref_path))

    # Build description with refs
    full_desc = description
    if ref_paths:
        full_desc += "\n\nРЕФЕРЕНСЫ:\n" + "\n".join(f"  - {p}" for p in ref_paths)

    # Add task
    prio = TaskPriority[priority.upper()]
    task = Task(
        project=project,
        description=full_desc,
        priority=prio
    )
    db.add(task)

    # Return updated task list
    return await tasks_list_partial(request, project=None)


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(request: Request, task_id: str):
    """Cancel a pending task."""
    task = db.get(task_id)
    if task and task.status == TaskStatus.PENDING:
        db.remove(task_id)

    return HTMLResponse("")


@app.post("/daemon/start")
async def start_daemon(request: Request, workers: int = Form(1)):
    """Start daemon in background."""
    global daemon_process

    if daemon_process and daemon_process.poll() is None:
        return HTMLResponse('<span class="text-yellow-500">Already running</span>')

    studio_dir = Path(__file__).parent.parent
    cmd = [
        sys.executable, "cli.py", "daemon",
        "--workers", str(workers),
        "--no-analyze",
        "--no-reset"
    ]

    daemon_process = subprocess.Popen(
        cmd,
        cwd=str(studio_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )

    return HTMLResponse(f'<span class="text-green-500">Started (PID: {daemon_process.pid})</span>')


@app.post("/daemon/stop")
async def stop_daemon():
    """Stop daemon."""
    global daemon_process

    if daemon_process and daemon_process.poll() is None:
        daemon_process.terminate()
        try:
            daemon_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            daemon_process.kill()
        daemon_process = None

    return HTMLResponse('<span class="text-gray-500">Stopped</span>')


# ============ WebSocket for live logs ============

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for live log streaming."""
    await websocket.accept()
    log_subscribers.append(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_subscribers.remove(websocket)


# ============ API ============

@app.get("/api/tasks")
async def api_tasks(project: Optional[str] = None):
    """JSON API for tasks."""
    if project:
        tasks = db.tasks_by_project(project)
    else:
        tasks = db.all_tasks()

    return [
        {
            "id": t.id,
            "project": t.project,
            "description": t.description[:100],
            "status": t.status.value,
            "priority": t.priority.name
        }
        for t in tasks
    ]


@app.get("/api/stats")
async def api_stats():
    """JSON API for stats."""
    stats = db.stats()
    stats["daemon_running"] = daemon_process is not None and daemon_process.poll() is None
    return stats


@app.get("/api/test-plan/{project}")
async def api_test_plan(project: str, commits: int = 5):
    """Generate test plan for a project."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.test_planner import generate_test_plan

    if project not in projects:
        return {"error": f"Project not found: {project}"}

    plan = generate_test_plan(
        project=project,
        commits=commits,
        workspace=WORKSPACE
    )

    return {"project": project, "commits": commits, "plan": plan}


@app.get("/test-plan/{project}", response_class=HTMLResponse)
async def test_plan_page(request: Request, project: str, commits: int = 5):
    """Test plan page - shows loading then redirects to file."""
    if project not in projects:
        return HTMLResponse(f"Project not found: {project}", status_code=404)

    # Show loading page that triggers generation
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Generating Test Plan - {project}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    </head>
    <body class="bg-gray-900 text-gray-100 p-8">
        <div class="max-w-2xl mx-auto text-center">
            <h1 class="text-2xl font-bold mb-6">Generating Test Plan</h1>
            <div class="bg-gray-800 rounded-lg p-8">
                <div id="status" hx-get="/test-plan/{project}/generate?commits={commits}" hx-trigger="load" hx-swap="innerHTML">
                    <div class="animate-pulse">
                        <div class="text-6xl mb-4">🤖</div>
                        <p class="text-lg text-purple-400">Claude is analyzing {commits} commits...</p>
                        <p class="text-sm text-gray-500 mt-2">This may take 1-2 minutes</p>
                        <div class="mt-6 flex justify-center">
                            <div class="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
                        </div>
                    </div>
                </div>
            </div>
            <a href="/" class="text-blue-400 hover:underline mt-6 inline-block">Cancel and return to Dashboard</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


@app.get("/test-plan/{project}/generate", response_class=HTMLResponse)
async def test_plan_generate(project: str, commits: int = 5):
    """Actually generate the test plan (called by HTMX)."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.test_planner import generate_test_plan

    plan = generate_test_plan(
        project=project,
        commits=commits,
        workspace=WORKSPACE
    )

    if plan.startswith("Error:"):
        return HTMLResponse(f"""
            <div class="text-red-400">
                <div class="text-6xl mb-4">❌</div>
                <p class="text-lg">Generation failed</p>
                <p class="text-sm mt-2">{plan}</p>
                <a href="/" class="text-blue-400 hover:underline mt-4 inline-block">Back to Dashboard</a>
            </div>
        """)

    # Check if file was created
    test_plan_path = WORKSPACE / project / "docs" / "TEST_PLAN.md"
    if test_plan_path.exists():
        return HTMLResponse(f"""
            <div class="text-green-400">
                <div class="text-6xl mb-4">✅</div>
                <p class="text-lg">Test Plan Generated!</p>
                <p class="text-sm text-gray-400 mt-2">Saved to: docs/TEST_PLAN.md</p>
                <div class="mt-6 space-x-4">
                    <a href="/test-plan/{project}/view" class="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg inline-block">View Plan</a>
                    <a href="/" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg inline-block">Back to Dashboard</a>
                </div>
            </div>
        """)
    else:
        # Plan returned in stdout
        return HTMLResponse(f"""
            <div class="text-green-400">
                <div class="text-6xl mb-4">✅</div>
                <p class="text-lg">Test Plan Generated!</p>
                <div class="mt-6">
                    <a href="/" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg inline-block">Back to Dashboard</a>
                </div>
                <div class="mt-6 text-left bg-gray-700 rounded p-4 max-h-96 overflow-y-auto">
                    <pre class="text-xs text-gray-300 whitespace-pre-wrap">{plan[:2000]}...</pre>
                </div>
            </div>
        """)


@app.get("/test-plan/{project}/view", response_class=HTMLResponse)
async def test_plan_view(request: Request, project: str):
    """View existing test plan file."""
    test_plan_path = WORKSPACE / project / "docs" / "TEST_PLAN.md"

    if not test_plan_path.exists():
        return HTMLResponse(f"Test plan not found. <a href='/test-plan/{project}'>Generate one</a>", status_code=404)

    content = test_plan_path.read_text(encoding='utf-8')

    # Try to use markdown module, fallback to pre
    try:
        import markdown
        plan_html = markdown.markdown(content, extensions=['tables', 'fenced_code', 'toc'])
    except ImportError:
        # Simple markdown-like conversion for tables
        import html
        escaped = html.escape(content)
        plan_html = f"<pre style='white-space: pre-wrap;'>{escaped}</pre>"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Plan - {project}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .prose table {{ width: 100%; border-collapse: collapse; }}
            .prose th, .prose td {{ border: 1px solid #374151; padding: 8px; text-align: left; }}
            .prose th {{ background: #1f2937; }}
            .prose h2 {{ margin-top: 2rem; color: #a78bfa; }}
            .prose h3 {{ margin-top: 1.5rem; color: #60a5fa; }}
            .prose code {{ background: #374151; padding: 2px 6px; border-radius: 4px; }}
            .prose pre {{ background: #1f2937; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
        </style>
    </head>
    <body class="bg-gray-900 text-gray-100 p-8">
        <div class="max-w-5xl mx-auto">
            <div class="flex justify-between items-center mb-6">
                <h1 class="text-2xl font-bold">Test Plan: {project}</h1>
                <div class="space-x-3">
                    <a href="/test-plan/{project}" class="px-3 py-1 bg-purple-600 hover:bg-purple-700 rounded text-sm">Regenerate</a>
                    <a href="/" class="text-blue-400 hover:underline">Dashboard</a>
                </div>
            </div>
            <div class="bg-gray-800 rounded-lg p-6 prose prose-invert max-w-none">
                {plan_html}
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


# ============ Asset Review ============

# Issue labels for the review form
ISSUE_LABELS = {
    # Colors
    "too_dark": "Слишком тёмное",
    "too_bright": "Слишком яркое",
    "too_gloomy": "Слишком мрачное",
    "wrong_palette": "Неправильная палитра",
    "low_contrast": "Низкий контраст",
    "colors_dont_match": "Цвета не сочетаются",
    # Composition
    "too_empty": "Слишком пусто",
    "too_cluttered": "Слишком загромождено",
    "need_more_elements": "Нужно больше элементов",
    "wrong_focus": "Неправильный фокус",
    "bad_balance": "Плохой баланс",
    # Style
    "not_pixel_art": "Не пиксельарт",
    "too_detailed": "Слишком детализировано",
    "not_detailed_enough": "Недостаточно деталей",
    "wrong_style": "Неподходящий стиль",
    "inconsistent": "Несогласованный стиль",
    # Details
    "add_objects": "Добавить объекты",
    "remove_objects": "Убрать лишнее",
    "wrong_proportions": "Неправильные пропорции",
    "missing_elements": "Отсутствуют элементы",
}

COLOR_ISSUES = ["too_dark", "too_bright", "too_gloomy", "wrong_palette", "low_contrast"]
COMPOSITION_ISSUES = ["too_empty", "too_cluttered", "need_more_elements", "wrong_focus"]
STYLE_ISSUES = ["not_pixel_art", "too_detailed", "not_detailed_enough", "wrong_style"]
DETAIL_ISSUES = ["add_objects", "remove_objects", "wrong_proportions", "missing_elements"]


def get_pending_assets():
    """Get all assets pending review from all projects."""
    from core.asset_feedback import AssetHistoryManager
    from core.asset_scanner import AssetScanner, AssetStatus

    pending = []

    for project_name, project in projects.items():
        project_path = project.path

        # Check .generations folder for pending_review
        history_mgr = AssetHistoryManager(project_path)
        for history in history_mgr.list_pending_review():
            latest = history.get_latest()
            pending.append({
                "asset_id": history.asset_id,
                "project": project_name,
                "category": history.spec.get("category", "misc"),
                "version": history.current_version,
                "preview_path": latest.result_path if latest else None,
                "history": history
            })

        # Also check manifest for pending_review status
        scanner = AssetScanner(project_path)
        for asset in scanner.scan_for_review():
            # Check if not already in list
            if not any(p["asset_id"] == asset.asset_id for p in pending):
                pending.append({
                    "asset_id": asset.asset_id,
                    "project": project_name,
                    "category": asset.category,
                    "version": 1,
                    "preview_path": asset.path,
                    "history": None
                })

    return pending


@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    """Asset review page - list all pending."""
    assets = get_pending_assets()

    return templates.TemplateResponse("review.html", {
        "request": request,
        "assets": assets,
        "current_asset": None,
        "pending_count": len(assets),
        "color_issues": [{"value": v, "label": ISSUE_LABELS[v]} for v in COLOR_ISSUES],
        "composition_issues": [{"value": v, "label": ISSUE_LABELS[v]} for v in COMPOSITION_ISSUES],
        "style_issues": [{"value": v, "label": ISSUE_LABELS[v]} for v in STYLE_ISSUES],
        "detail_issues": [{"value": v, "label": ISSUE_LABELS[v]} for v in DETAIL_ISSUES],
    })


@app.get("/review/{project}/{category}/{asset_id}", response_class=HTMLResponse)
async def review_asset(request: Request, project: str, category: str, asset_id: str,
                       v: Optional[int] = None):
    """Review specific asset."""
    from core.asset_feedback import AssetHistoryManager

    if project not in projects:
        return HTMLResponse(f"Project not found: {project}", status_code=404)

    project_path = projects[project].path
    history_mgr = AssetHistoryManager(project_path)
    history = history_mgr.load_history(asset_id)

    assets = get_pending_assets()
    current_version = v or history.current_version

    # Find current image
    current_image = None
    if history.generations:
        for gen in history.generations:
            if gen.version == current_version:
                current_image = f"v{gen.version}/result.png"
                break
        if not current_image:
            current_image = f"v{history.current_version}/result.png"

    current_asset = {
        "asset_id": asset_id,
        "project": project,
        "category": category,
        "version": current_version
    }

    return templates.TemplateResponse("review.html", {
        "request": request,
        "assets": assets,
        "current_asset": current_asset,
        "current_image": current_image,
        "current_version": current_version,
        "history": history,
        "pending_count": len(assets),
        "color_issues": [{"value": v, "label": ISSUE_LABELS[v]} for v in COLOR_ISSUES],
        "composition_issues": [{"value": v, "label": ISSUE_LABELS[v]} for v in COMPOSITION_ISSUES],
        "style_issues": [{"value": v, "label": ISSUE_LABELS[v]} for v in STYLE_ISSUES],
        "detail_issues": [{"value": v, "label": ISSUE_LABELS[v]} for v in DETAIL_ISSUES],
    })


@app.post("/review/{project}/{category}/{asset_id}/feedback")
async def submit_feedback(request: Request, project: str, category: str, asset_id: str,
                          decision: str = Form(...),
                          issues: List[str] = Form(default=[]),
                          free_text: str = Form(default=""),
                          intensity: str = Form(default="moderate")):
    """Submit feedback for an asset."""
    from core.asset_feedback import (
        AssetHistoryManager, AssetFeedback, FeedbackIssue,
        ChangeIntensity, ReviewDecision
    )
    from core.asset_scanner import AssetScanner, AssetStatus

    if project not in projects:
        return HTMLResponse(f"Project not found: {project}", status_code=404)

    project_path = projects[project].path
    history_mgr = AssetHistoryManager(project_path)
    history = history_mgr.load_history(asset_id)

    # Map decision string to enum
    decision_map = {
        "approved": ReviewDecision.APPROVED,
        "rejected": ReviewDecision.REJECTED,
        "revision_requested": ReviewDecision.REVISION_REQUESTED
    }
    decision_enum = decision_map.get(decision, ReviewDecision.REVISION_REQUESTED)

    # Map intensity
    intensity_map = {
        "minimal": ChangeIntensity.MINIMAL,
        "moderate": ChangeIntensity.MODERATE,
        "major": ChangeIntensity.MAJOR
    }
    intensity_enum = intensity_map.get(intensity, ChangeIntensity.MODERATE)

    # Map issues
    issue_enums = []
    for issue in issues:
        try:
            issue_enums.append(FeedbackIssue(issue))
        except ValueError:
            pass

    # Create feedback
    feedback = AssetFeedback(
        version=history.current_version,
        asset_id=asset_id,
        reviewer="web_user",
        decision=decision_enum,
        issues=issue_enums,
        free_text=free_text,
        change_intensity=intensity_enum
    )

    # Submit feedback
    history_mgr.submit_feedback(asset_id, feedback)

    # Update manifest status
    scanner = AssetScanner(project_path)
    if decision_enum == ReviewDecision.APPROVED:
        # Copy to final location and update manifest
        target_path = project_path / "assets" / category / f"{asset_id}.png"
        history_mgr.approve_asset(asset_id, target_path)
        scanner.update_status(asset_id, category, AssetStatus.READY, path=str(target_path))
    elif decision_enum == ReviewDecision.REJECTED:
        scanner.update_status(asset_id, category, AssetStatus.REJECTED, feedback=free_text)
    else:
        # Revision requested - status goes back to planned for regeneration
        scanner.update_status(asset_id, category, AssetStatus.PLANNED, feedback=free_text)

    # Redirect back to review page
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/review", status_code=303)


@app.get("/generations/{project}/{asset_id}/{path:path}")
async def serve_generation(project: str, asset_id: str, path: str):
    """Serve generated asset images."""
    from fastapi.responses import FileResponse

    if project not in projects:
        return HTMLResponse("Not found", status_code=404)

    project_path = projects[project].path
    file_path = project_path / "assets" / ".generations" / asset_id / path

    if not file_path.exists():
        return HTMLResponse("Not found", status_code=404)

    return FileResponse(file_path)


@app.get("/assets/{project}/{path:path}")
async def serve_asset(project: str, path: str):
    """Serve project assets."""
    from fastapi.responses import FileResponse

    if project not in projects:
        return HTMLResponse("Not found", status_code=404)

    project_path = projects[project].path
    file_path = project_path / "assets" / path

    if not file_path.exists():
        return HTMLResponse("Not found", status_code=404)

    return FileResponse(file_path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
