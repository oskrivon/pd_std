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
    tasks = db.all_tasks()
    stats = db.stats()

    pending = [t for t in tasks if t.status == TaskStatus.PENDING]
    in_progress = [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]
    completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
    failed = [t for t in tasks if t.status == TaskStatus.FAILED]

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
        "--no-analyze"
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
