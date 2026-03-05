"""
Remote UI Server - deployable to VPS for remote access.

Serves the review UI and bridges WebSocket connections between
UI clients (browsers) and local workers (machines with Claude Code).

Architecture:
  [Browser] <--WS--> [Remote Server] <--WS--> [Local Worker]
                           |
                      [Static UI]
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Set, Optional, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ws_protocol import WSMessage, MessageType, create_command, create_error

logger = logging.getLogger(__name__)

app = FastAPI(title="Ptero Studio Remote UI")

# Templates
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@dataclass
class ConnectedWorker:
    """Represents a connected local worker."""
    worker_id: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)


@dataclass
class PendingRequest:
    """Request waiting for worker response."""
    request_id: str
    ui_websocket: WebSocket
    created_at: datetime = field(default_factory=datetime.now)


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.workers: Dict[str, ConnectedWorker] = {}
        self.ui_clients: Set[WebSocket] = set()
        self.pending_requests: Dict[str, PendingRequest] = {}
        self._lock = asyncio.Lock()

    async def connect_worker(self, websocket: WebSocket, worker_id: str):
        """Register a worker connection."""
        async with self._lock:
            self.workers[worker_id] = ConnectedWorker(
                worker_id=worker_id,
                websocket=websocket
            )
            logger.info(f"Worker connected: {worker_id}")

            # Notify UI clients
            await self._broadcast_to_ui({
                "type": MessageType.STATUS_WORKER_ONLINE.value,
                "worker_id": worker_id
            })

    async def disconnect_worker(self, worker_id: str):
        """Remove a worker connection."""
        async with self._lock:
            if worker_id in self.workers:
                del self.workers[worker_id]
                logger.info(f"Worker disconnected: {worker_id}")

                # Notify UI clients
                await self._broadcast_to_ui({
                    "type": MessageType.STATUS_WORKER_OFFLINE.value,
                    "worker_id": worker_id
                })

    async def connect_ui(self, websocket: WebSocket):
        """Register a UI client connection."""
        async with self._lock:
            self.ui_clients.add(websocket)
            logger.info(f"UI client connected. Total: {len(self.ui_clients)}")

    async def disconnect_ui(self, websocket: WebSocket):
        """Remove a UI client connection."""
        async with self._lock:
            self.ui_clients.discard(websocket)
            logger.info(f"UI client disconnected. Total: {len(self.ui_clients)}")

    def get_active_worker(self) -> Optional[ConnectedWorker]:
        """Get an active worker (first available)."""
        if self.workers:
            return list(self.workers.values())[0]
        return None

    async def send_to_worker(self, msg: WSMessage, ui_ws: WebSocket) -> bool:
        """Send command to worker, track pending request."""
        worker = self.get_active_worker()
        if not worker:
            return False

        # Track pending request
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

    async def handle_worker_response(self, msg: WSMessage):
        """Handle response from worker, route to UI."""
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
            # Broadcast status updates to all UI clients
            await self._broadcast_to_ui(json.loads(msg.to_json()))

    async def _broadcast_to_ui(self, data: dict):
        """Broadcast message to all UI clients."""
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
        """Get connection status."""
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


# HTTP Routes

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page - redirects to review."""
    return templates.TemplateResponse("remote_index.html", {
        "request": request,
        "status": manager.get_status()
    })


@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    """Review UI page."""
    return templates.TemplateResponse("remote_review.html", {
        "request": request,
        "worker_online": len(manager.workers) > 0
    })


@app.get("/status")
async def status():
    """Get server status."""
    return manager.get_status()


# WebSocket Routes

@app.websocket("/ws/worker")
async def worker_websocket(websocket: WebSocket):
    """WebSocket endpoint for local workers."""
    await websocket.accept()
    worker_id = None

    try:
        # Wait for registration message
        raw = await websocket.receive_text()
        msg = WSMessage.from_json(raw)

        if msg.type == MessageType.WORKER_CONNECT:
            worker_id = msg.payload.get("worker_id", str(uuid.uuid4())[:8])
            await manager.connect_worker(websocket, worker_id)

            # Process messages
            while True:
                raw = await websocket.receive_text()
                msg = WSMessage.from_json(raw)

                if msg.type == MessageType.WORKER_HEARTBEAT:
                    if worker_id in manager.workers:
                        manager.workers[worker_id].last_heartbeat = datetime.now()
                elif msg.type == MessageType.WORKER_DISCONNECT:
                    break
                else:
                    # Response from worker - route to UI
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
    """WebSocket endpoint for UI clients (browsers)."""
    await websocket.accept()
    await manager.connect_ui(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            # Create command message
            msg_type = MessageType(data.get("type", "cmd_scan_assets"))
            request_id = data.get("request_id", str(uuid.uuid4())[:8])

            msg = WSMessage(
                type=msg_type,
                request_id=request_id,
                payload=data.get("payload", {})
            )

            # Send to worker
            success = await manager.send_to_worker(msg, websocket)

            if not success:
                error = create_error("No worker available", request_id)
                await websocket.send_text(error.to_json())

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"UI websocket error: {e}")
    finally:
        await manager.disconnect_ui(websocket)


def run_server(host: str = "0.0.0.0", port: int = 8081):
    """Run the remote server."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Remote UI Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", "-p", type=int, default=8081, help="Port")

    args = parser.parse_args()
    run_server(args.host, args.port)
