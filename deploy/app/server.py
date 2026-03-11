"""
Ptero Studio Remote Server

Combined server for Asset Review and Tester Feedback.
Deploys to VPS, connects to local workers via WebSocket.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Set, Optional, Any, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import base64

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Ptero Studio Remote")

# Templates
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Data storage (JSON files in /app/data)
DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(exist_ok=True)

# Screenshots storage - create BEFORE mounting
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# Mount screenshots for viewing (after directory is created)
app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOTS_DIR)), name="screenshots")


# ============ WebSocket Protocol ============

class MessageType(str, Enum):
    # Worker registration
    WORKER_CONNECT = "worker_connect"
    WORKER_DISCONNECT = "worker_disconnect"
    WORKER_HEARTBEAT = "worker_heartbeat"

    # Asset commands
    CMD_SCAN_ASSETS = "cmd_scan_assets"
    CMD_GET_ASSET = "cmd_get_asset"
    CMD_GET_IMAGE = "cmd_get_image"
    CMD_SUBMIT_FEEDBACK = "cmd_submit_feedback"
    CMD_REGENERATE = "cmd_regenerate"
    CMD_APPROVE = "cmd_approve"

    # Tester feedback commands
    CMD_SUBMIT_TESTER_FEEDBACK = "cmd_submit_tester_feedback"
    CMD_LIST_TESTER_FEEDBACKS = "cmd_list_tester_feedbacks"
    CMD_GET_PROJECTS = "cmd_get_projects"

    # Responses
    RESP_ASSETS_LIST = "resp_assets_list"
    RESP_ASSET_DETAIL = "resp_asset_detail"
    RESP_IMAGE_DATA = "resp_image_data"
    RESP_FEEDBACK_SAVED = "resp_feedback_saved"
    RESP_GENERATION_STARTED = "resp_generation_started"
    RESP_GENERATION_COMPLETE = "resp_generation_complete"
    RESP_APPROVED = "resp_approved"
    RESP_TESTER_FEEDBACK_SAVED = "resp_tester_feedback_saved"
    RESP_TESTER_FEEDBACKS_LIST = "resp_tester_feedbacks_list"
    RESP_PROJECTS_LIST = "resp_projects_list"
    RESP_ERROR = "resp_error"

    # Status updates
    STATUS_WORKER_ONLINE = "status_worker_online"
    STATUS_WORKER_OFFLINE = "status_worker_offline"


@dataclass
class WSMessage:
    type: MessageType
    request_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "payload": self.payload
        })

    @classmethod
    def from_json(cls, data: str) -> "WSMessage":
        d = json.loads(data)
        return cls(
            type=MessageType(d["type"]),
            request_id=d.get("request_id", ""),
            timestamp=d.get("timestamp", ""),
            payload=d.get("payload", {})
        )


# ============ Connection Manager ============

@dataclass
class ConnectedWorker:
    worker_id: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)


@dataclass
class PendingRequest:
    request_id: str
    ui_websocket: WebSocket
    created_at: datetime = field(default_factory=datetime.now)


class ConnectionManager:
    def __init__(self):
        self.workers: Dict[str, ConnectedWorker] = {}
        self.ui_clients: Set[WebSocket] = set()
        self.pending_requests: Dict[str, PendingRequest] = {}
        self._lock = asyncio.Lock()

    async def connect_worker(self, websocket: WebSocket, worker_id: str):
        async with self._lock:
            self.workers[worker_id] = ConnectedWorker(
                worker_id=worker_id,
                websocket=websocket
            )
            logger.info(f"Worker connected: {worker_id}")
            await self._broadcast_to_ui({
                "type": MessageType.STATUS_WORKER_ONLINE.value,
                "worker_id": worker_id
            })

    async def disconnect_worker(self, worker_id: str):
        async with self._lock:
            if worker_id in self.workers:
                del self.workers[worker_id]
                logger.info(f"Worker disconnected: {worker_id}")
                await self._broadcast_to_ui({
                    "type": MessageType.STATUS_WORKER_OFFLINE.value,
                    "worker_id": worker_id
                })

    async def connect_ui(self, websocket: WebSocket):
        async with self._lock:
            self.ui_clients.add(websocket)
            logger.info(f"UI client connected. Total: {len(self.ui_clients)}")

    async def disconnect_ui(self, websocket: WebSocket):
        async with self._lock:
            self.ui_clients.discard(websocket)
            logger.info(f"UI client disconnected. Total: {len(self.ui_clients)}")

    def get_active_worker(self) -> Optional[ConnectedWorker]:
        if self.workers:
            return list(self.workers.values())[0]
        return None

    async def send_to_worker(self, msg: WSMessage, ui_ws: WebSocket) -> bool:
        worker = self.get_active_worker()
        if not worker:
            return False

        self.pending_requests[msg.request_id] = PendingRequest(
            request_id=msg.request_id,
            ui_websocket=ui_ws
        )

        try:
            await worker.websocket.send_text(msg.to_json())
            return True
        except Exception as e:
            logger.error(f"Failed to send to worker: {e}")
            del self.pending_requests[msg.request_id]
            return False

    async def send_to_worker_nowait(self, msg: WSMessage) -> bool:
        """Send to worker without tracking response."""
        worker = self.get_active_worker()
        if not worker:
            return False
        try:
            await worker.websocket.send_text(msg.to_json())
            return True
        except Exception as e:
            logger.error(f"Failed to send to worker: {e}")
            return False

    async def handle_worker_response(self, msg: WSMessage):
        request_id = msg.request_id
        if request_id in self.pending_requests:
            pending = self.pending_requests[request_id]
            try:
                await pending.ui_websocket.send_text(msg.to_json())
            except Exception as e:
                logger.error(f"Failed to send to UI: {e}")
            finally:
                del self.pending_requests[request_id]
        else:
            await self._broadcast_to_ui(json.loads(msg.to_json()))

    async def _broadcast_to_ui(self, data: dict):
        message = json.dumps(data)
        disconnected = []
        for ws in self.ui_clients:
            try:
                await ws.send_text(message)
            except:
                disconnected.append(ws)
        for ws in disconnected:
            self.ui_clients.discard(ws)

    def get_status(self) -> dict:
        return {
            "workers": [
                {
                    "worker_id": w.worker_id,
                    "connected_at": w.connected_at.isoformat(),
                    "last_heartbeat": w.last_heartbeat.isoformat()
                }
                for w in self.workers.values()
            ],
            "ui_clients": len(self.ui_clients),
            "pending_requests": len(self.pending_requests)
        }


manager = ConnectionManager()


# ============ Tester Feedback Storage (server-side) ============

class TesterFeedbackType(str, Enum):
    GAME_BUG = "game_bug"
    BALANCE = "balance"
    AI_GENERATION = "ai_generation"


class BugSeverity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    COSMETIC = "cosmetic"


FEEDBACKS_FILE = DATA_DIR / "tester_feedbacks.json"


def load_feedbacks() -> List[dict]:
    if FEEDBACKS_FILE.exists():
        with open(FEEDBACKS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_feedbacks(feedbacks: List[dict]):
    with open(FEEDBACKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(feedbacks, f, ensure_ascii=False, indent=2)


def add_feedback(feedback: dict) -> dict:
    feedbacks = load_feedbacks()
    feedback["id"] = f"tf_{uuid.uuid4().hex[:8]}"
    feedback["submitted_at"] = datetime.now().isoformat()
    feedback["status"] = "new"
    feedbacks.insert(0, feedback)
    save_feedbacks(feedbacks)
    return feedback


# ============ HTTP Routes ============

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "status": manager.get_status()
    })


@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    return templates.TemplateResponse("review.html", {
        "request": request,
        "worker_online": len(manager.workers) > 0
    })


@app.get("/tester/feedback", response_class=HTMLResponse)
async def tester_feedback_form(request: Request):
    return templates.TemplateResponse("tester/feedback_form.html", {
        "request": request,
        "worker_online": len(manager.workers) > 0
    })


@app.post("/tester/feedback/submit", response_class=HTMLResponse)
async def submit_tester_feedback(
    request: Request,
    project: str = Form(...),
    feedback_type: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    tester_name: str = Form(default=""),
    tester_email: str = Form(default=""),
    steps_to_reproduce: str = Form(default=""),
    expected_behavior: str = Form(default=""),
    actual_behavior: str = Form(default=""),
    bug_severity: str = Form(default=""),
    balance_area: str = Form(default=""),
    ai_issues: List[str] = Form(default=[]),
    asset_id: str = Form(default=""),
    screenshots: List[UploadFile] = File(default=[])
):
    """Submit tester feedback - saves locally and forwards to worker."""
    # Generate feedback ID first for screenshot naming
    feedback_id = f"tf_{uuid.uuid4().hex[:8]}"

    # Process screenshots
    screenshot_data = []
    if screenshots and screenshots[0].filename:
        feedback_screenshots_dir = SCREENSHOTS_DIR / feedback_id
        feedback_screenshots_dir.mkdir(exist_ok=True)

        for i, screenshot in enumerate(screenshots):
            if screenshot.filename and screenshot.size > 0:
                # Save file
                ext = Path(screenshot.filename).suffix or ".png"
                filename = f"screenshot_{i+1}{ext}"
                file_path = feedback_screenshots_dir / filename

                content = await screenshot.read()
                file_path.write_bytes(content)

                # Store as base64 for sending to worker
                screenshot_data.append({
                    "filename": filename,
                    "path": str(file_path),
                    "base64": base64.b64encode(content).decode('utf-8'),
                    "content_type": screenshot.content_type or "image/png"
                })

                logger.info(f"Saved screenshot: {file_path} ({len(content)} bytes)")

    feedback = {
        "id": feedback_id,
        "project": project,
        "feedback_type": feedback_type,
        "title": title,
        "description": description,
        "tester_name": tester_name,
        "tester_email": tester_email,
        "steps_to_reproduce": steps_to_reproduce,
        "expected_behavior": expected_behavior,
        "actual_behavior": actual_behavior,
        "bug_severity": bug_severity if bug_severity else None,
        "balance_area": balance_area if balance_area else None,
        "ai_issues": ai_issues if ai_issues else [],
        "asset_id": asset_id,
        "screenshots": screenshot_data
    }

    # Save locally on server (without base64 to save space)
    feedback_to_save = {**feedback, "screenshots": [
        {"filename": s["filename"], "path": s["path"]} for s in screenshot_data
    ]}
    feedback_to_save["submitted_at"] = datetime.now().isoformat()
    feedback_to_save["status"] = "new"

    feedbacks = load_feedbacks()
    feedbacks.insert(0, feedback_to_save)
    save_feedbacks(feedbacks)

    # Forward to worker if connected (with base64 images)
    logger.info(f"Workers connected: {len(manager.workers)}")
    if manager.workers:
        msg = WSMessage(
            type=MessageType.CMD_SUBMIT_TESTER_FEEDBACK,
            request_id=feedback_id,
            payload=feedback
        )
        sent = await manager.send_to_worker_nowait(msg)
        logger.info(f"Sent feedback {feedback_id} to worker: {sent}")

    return templates.TemplateResponse("tester/feedback_success.html", {
        "request": request,
        "feedback": feedback_to_save
    })


@app.get("/tester/feedback/list", response_class=HTMLResponse)
async def list_tester_feedbacks(request: Request, project: str = None, status: str = None):
    feedbacks = load_feedbacks()

    if project:
        feedbacks = [f for f in feedbacks if f.get("project") == project]
    if status:
        feedbacks = [f for f in feedbacks if f.get("status") == status]

    stats = {
        "total": len(load_feedbacks()),
        "new": len([f for f in load_feedbacks() if f.get("status") == "new"]),
        "resolved": len([f for f in load_feedbacks() if f.get("status") == "resolved"])
    }

    return templates.TemplateResponse("tester/feedback_list.html", {
        "request": request,
        "feedbacks": feedbacks,
        "selected_project": project,
        "selected_status": status,
        "stats": stats
    })


@app.get("/status")
async def status():
    return manager.get_status()


# ============ WebSocket Routes ============

@app.websocket("/ws/worker")
async def worker_websocket(websocket: WebSocket):
    await websocket.accept()
    worker_id = None

    try:
        raw = await websocket.receive_text()
        msg = WSMessage.from_json(raw)

        if msg.type == MessageType.WORKER_CONNECT:
            worker_id = msg.payload.get("worker_id", str(uuid.uuid4())[:8])
            await manager.connect_worker(websocket, worker_id)

            while True:
                raw = await websocket.receive_text()
                msg = WSMessage.from_json(raw)

                if msg.type == MessageType.WORKER_HEARTBEAT:
                    if worker_id in manager.workers:
                        manager.workers[worker_id].last_heartbeat = datetime.now()
                elif msg.type == MessageType.WORKER_DISCONNECT:
                    break
                else:
                    await manager.handle_worker_response(msg)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Worker websocket error: {e}")
    finally:
        if worker_id:
            await manager.disconnect_worker(worker_id)


@app.websocket("/ws/ui")
async def ui_websocket(websocket: WebSocket):
    await websocket.accept()
    await manager.connect_ui(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            msg_type = MessageType(data.get("type", "cmd_scan_assets"))
            request_id = data.get("request_id", str(uuid.uuid4())[:8])

            msg = WSMessage(
                type=msg_type,
                request_id=request_id,
                payload=data.get("payload", {})
            )

            success = await manager.send_to_worker(msg, websocket)

            if not success:
                error = WSMessage(
                    type=MessageType.RESP_ERROR,
                    request_id=request_id,
                    payload={"error": "No worker available"}
                )
                await websocket.send_text(error.to_json())

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"UI websocket error: {e}")
    finally:
        await manager.disconnect_ui(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
