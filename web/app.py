"""
Ptero Studio Dashboard

FastAPI + HTMX web interface for task management.

Usage:
    cd studio && uvicorn web.app:app --reload --port 8000
    # or
    ptero-studio web
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.orchestrator import Orchestrator
from core.task_queue import TaskPriority, TaskStatus
from core.project import Project

# Globals
WORKSPACE = os.environ.get("PTERO_WORKSPACE", "C:/Ptero Dactyl Games")
orch: Optional[Orchestrator] = None
daemon_process = None  # subprocess.Popen handle
log_subscribers: List[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize orchestrator on startup."""
    global orch
    orch = Orchestrator(workspace=WORKSPACE)
    yield
    # Cleanup
    if daemon_task and not daemon_task.done():
        daemon_task.cancel()


app = FastAPI(title="Ptero Studio", lifespan=lifespan)

# Static files and templates
web_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=web_dir / "static"), name="static")
templates = Jinja2Templates(directory=web_dir / "templates")


# ============ Pages ============

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard."""
    orch.tasks.reload()  # Reload from file to see daemon changes
    projects = orch.projects
    tasks = orch.tasks.all_tasks()

    pending = [t for t in tasks if t.status == TaskStatus.PENDING]
    in_progress = [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]
    completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
    failed = [t for t in tasks if t.status == TaskStatus.FAILED]

    return templates.TemplateResponse("index.html", {
        "request": request,
        "projects": projects,
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed[-10:],  # Last 10
        "failed": failed[-5:],
        "stats": {
            "pending": len(pending),
            "in_progress": len(in_progress),
            "completed": len(completed),
            "failed": len(failed),
            "total": len(tasks)
        },
        "daemon_running": daemon_process is not None and daemon_process.poll() is None
    })


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request, project: Optional[str] = None):
    """Tasks list page."""
    orch.tasks.reload()
    tasks = orch.tasks.all_tasks(project)
    projects = orch.projects

    return templates.TemplateResponse("tasks.html", {
        "request": request,
        "tasks": sorted(tasks, key=lambda t: (t.status.value, -t.priority.value)),
        "projects": projects,
        "selected_project": project
    })


@app.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request):
    """Projects list."""
    return templates.TemplateResponse("projects.html", {
        "request": request,
        "projects": orch.projects
    })


# ============ HTMX Partials ============

@app.get("/partials/tasks-list", response_class=HTMLResponse)
async def tasks_list_partial(request: Request, project: Optional[str] = None):
    """Tasks list partial for HTMX updates."""
    orch.tasks.reload()
    tasks = orch.tasks.all_tasks(project)
    pending = [t for t in tasks if t.status == TaskStatus.PENDING]

    return templates.TemplateResponse("partials/tasks_list.html", {
        "request": request,
        "tasks": sorted(pending, key=lambda t: -t.priority.value)
    })


@app.get("/partials/stats", response_class=HTMLResponse)
async def stats_partial(request: Request):
    """Stats partial for polling updates."""
    orch.tasks.reload()
    tasks = orch.tasks.all_tasks()

    return templates.TemplateResponse("partials/stats.html", {
        "request": request,
        "stats": {
            "pending": len([t for t in tasks if t.status == TaskStatus.PENDING]),
            "in_progress": len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS]),
            "completed": len([t for t in tasks if t.status == TaskStatus.COMPLETED]),
            "failed": len([t for t in tasks if t.status == TaskStatus.FAILED])
        },
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
        refs_dir = Path(WORKSPACE) / "studio" / "tasks_inbox" / "refs"
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
    from core.task_queue import Task
    prio = TaskPriority[priority.upper()]
    task = Task(
        project=project,
        description=full_desc,
        priority=prio
    )
    orch.tasks.add(task)
    orch.tasks.save()

    # Return updated task list
    return await tasks_list_partial(request, project=None)


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(request: Request, task_id: str):
    """Cancel a pending task."""
    task = orch.tasks.get(task_id)
    if task and task.status == TaskStatus.PENDING:
        orch.tasks.remove(task_id)
        orch.tasks.save()
    # Return empty HTML to remove the element via HTMX
    return HTMLResponse("")


@app.post("/daemon/start")
async def start_daemon(request: Request, workers: int = Form(1)):
    """Start daemon in background."""
    global daemon_process

    # Check if already running
    if daemon_process and daemon_process.poll() is None:
        return HTMLResponse('<span class="text-yellow-500">Already running</span>')

    # Start daemon as detached subprocess
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
    import signal

    if daemon_process and daemon_process.poll() is None:
        # Send SIGTERM (or equivalent on Windows)
        daemon_process.terminate()
        try:
            daemon_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            daemon_process.kill()
        daemon_process = None

    return HTMLResponse('<span class="text-gray-500">Stopped</span>')


@app.post("/tasks/run-once")
async def run_single_task(request: Request):
    """Run a single task."""
    import concurrent.futures

    def execute():
        result = orch.run_next(analyze=False, validate=False)
        return result

    with concurrent.futures.ThreadPoolExecutor() as pool:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(pool, execute)

    # Return updated stats
    return await stats_partial(request)


# ============ WebSocket for live logs ============

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for live log streaming."""
    await websocket.accept()
    log_subscribers.append(websocket)

    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_subscribers.remove(websocket)


async def broadcast_log(message: str):
    """Send log message to all subscribers."""
    for ws in log_subscribers:
        try:
            await ws.send_text(message)
        except:
            pass


# ============ API ============

@app.get("/api/tasks")
async def api_tasks(project: Optional[str] = None):
    """JSON API for tasks."""
    orch.tasks.reload()
    tasks = orch.tasks.all_tasks(project)
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
    orch.tasks.reload()
    tasks = orch.tasks.all_tasks()
    return {
        "pending": len([t for t in tasks if t.status == TaskStatus.PENDING]),
        "in_progress": len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS]),
        "completed": len([t for t in tasks if t.status == TaskStatus.COMPLETED]),
        "failed": len([t for t in tasks if t.status == TaskStatus.FAILED]),
        "daemon_running": daemon_process is not None and daemon_process.poll() is None
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
