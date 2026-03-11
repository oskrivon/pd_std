"""
WebSocket Protocol for Remote UI <-> Local Worker communication.

Defines message types and schemas for the split architecture.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import json


class MessageType(str, Enum):
    """Message types for WebSocket communication."""

    # Worker -> Server (registration)
    WORKER_CONNECT = "worker_connect"
    WORKER_DISCONNECT = "worker_disconnect"
    WORKER_HEARTBEAT = "worker_heartbeat"

    # Server -> Worker (commands)
    CMD_SCAN_ASSETS = "cmd_scan_assets"
    CMD_GET_ASSET = "cmd_get_asset"
    CMD_GET_IMAGE = "cmd_get_image"
    CMD_SUBMIT_FEEDBACK = "cmd_submit_feedback"
    CMD_REGENERATE = "cmd_regenerate"
    CMD_APPROVE = "cmd_approve"
    CMD_SUBMIT_TESTER_FEEDBACK = "cmd_submit_tester_feedback"

    # Worker -> Server (responses)
    RESP_ASSETS_LIST = "resp_assets_list"
    RESP_ASSET_DETAIL = "resp_asset_detail"
    RESP_IMAGE_DATA = "resp_image_data"
    RESP_FEEDBACK_SAVED = "resp_feedback_saved"
    RESP_GENERATION_STARTED = "resp_generation_started"
    RESP_GENERATION_COMPLETE = "resp_generation_complete"
    RESP_APPROVED = "resp_approved"
    RESP_TESTER_FEEDBACK_SAVED = "resp_tester_feedback_saved"
    RESP_ERROR = "resp_error"

    # Server -> UI (status updates)
    STATUS_WORKER_ONLINE = "status_worker_online"
    STATUS_WORKER_OFFLINE = "status_worker_offline"
    STATUS_GENERATION_PROGRESS = "status_generation_progress"


@dataclass
class WSMessage:
    """Base WebSocket message."""
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


# Command payloads

@dataclass
class ScanAssetsPayload:
    """Payload for CMD_SCAN_ASSETS."""
    project: Optional[str] = None  # None = all projects

    def to_dict(self) -> dict:
        return {"project": self.project}


@dataclass
class GetAssetPayload:
    """Payload for CMD_GET_ASSET."""
    project: str
    category: str
    asset_id: str

    def to_dict(self) -> dict:
        return {"project": self.project, "category": self.category, "asset_id": self.asset_id}


@dataclass
class GetImagePayload:
    """Payload for CMD_GET_IMAGE."""
    path: str  # Relative path from generations folder

    def to_dict(self) -> dict:
        return {"path": self.path}


@dataclass
class SubmitFeedbackPayload:
    """Payload for CMD_SUBMIT_FEEDBACK."""
    project: str
    category: str
    asset_id: str
    decision: str  # approved, revision_requested, rejected
    issues: List[str] = field(default_factory=list)
    free_text: str = ""
    specific_requests: List[Dict] = field(default_factory=list)
    change_intensity: str = "moderate"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RegeneratePayload:
    """Payload for CMD_REGENERATE."""
    project: str
    category: str
    asset_id: str

    def to_dict(self) -> dict:
        return {"project": self.project, "category": self.category, "asset_id": self.asset_id}


@dataclass
class ApprovePayload:
    """Payload for CMD_APPROVE."""
    project: str
    category: str
    asset_id: str

    def to_dict(self) -> dict:
        return {"project": self.project, "category": self.category, "asset_id": self.asset_id}


# Response payloads

@dataclass
class AssetInfo:
    """Asset information for list responses."""
    asset_id: str
    project: str
    category: str
    status: str
    current_version: int
    spec: Dict[str, Any]
    latest_image: Optional[str] = None  # Base64 or URL

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AssetInfo":
        return cls(**d)


@dataclass
class GenerationInfo:
    """Generation record information."""
    version: int
    timestamp: str
    prompt: str
    image_data: Optional[str] = None  # Base64 encoded
    feedback: Optional[Dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AssetDetailPayload:
    """Full asset detail with history."""
    asset_id: str
    project: str
    category: str
    status: str
    spec: Dict[str, Any]
    generations: List[GenerationInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "project": self.project,
            "category": self.category,
            "status": self.status,
            "spec": self.spec,
            "generations": [g.to_dict() for g in self.generations]
        }


# Helper functions

def create_command(msg_type: MessageType, payload: dict, request_id: str = "") -> WSMessage:
    """Create a command message."""
    import uuid
    return WSMessage(
        type=msg_type,
        request_id=request_id or str(uuid.uuid4())[:8],
        payload=payload
    )


def create_response(msg_type: MessageType, payload: dict, request_id: str) -> WSMessage:
    """Create a response message."""
    return WSMessage(
        type=msg_type,
        request_id=request_id,
        payload=payload
    )


def create_error(error: str, request_id: str = "") -> WSMessage:
    """Create an error response."""
    return WSMessage(
        type=MessageType.RESP_ERROR,
        request_id=request_id,
        payload={"error": error}
    )
