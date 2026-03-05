"""
Local Worker - connects to remote UI server and executes commands locally.

Runs on the machine with Claude Code and API keys.
Handles asset scanning, generation, and approval.
"""

import asyncio
import base64
import logging
from pathlib import Path
from typing import Optional, Callable
import json

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    websockets = None

from .ws_protocol import (
    WSMessage, MessageType,
    create_response, create_error,
    AssetInfo, AssetDetailPayload, GenerationInfo
)
from .asset_feedback import AssetHistoryManager, AssetFeedback, ReviewDecision, FeedbackIssue, ChangeIntensity, SpecificRequest
from .asset_scanner import AssetScanner
from .feedback_processor import FeedbackProcessor

logger = logging.getLogger(__name__)


class LocalWorker:
    """
    Local worker that connects to remote UI server.

    Executes commands locally:
    - Scan manifest for assets
    - Get asset details and images
    - Submit feedback
    - Trigger regeneration
    - Approve assets
    """

    def __init__(
        self,
        workspace_path: Path,
        remote_url: str = "ws://localhost:8081/ws/worker",
        worker_id: str = "local-1",
        on_regenerate: Optional[Callable] = None
    ):
        self.workspace = Path(workspace_path)
        self.studio_path = self.workspace / "studio"
        self.remote_url = remote_url
        self.worker_id = worker_id
        self.on_regenerate = on_regenerate  # Callback for regeneration

        self._ws: Optional[WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_delay = 5

    async def connect(self) -> bool:
        """Connect to remote server."""
        if websockets is None:
            logger.error("websockets library not installed. Run: pip install websockets")
            return False

        try:
            self._ws = await websockets.connect(self.remote_url)

            # Send registration
            msg = WSMessage(
                type=MessageType.WORKER_CONNECT,
                payload={"worker_id": self.worker_id}
            )
            await self._ws.send(msg.to_json())

            logger.info(f"Connected to remote server: {self.remote_url}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False

    async def disconnect(self):
        """Disconnect from server."""
        if self._ws:
            msg = WSMessage(
                type=MessageType.WORKER_DISCONNECT,
                payload={"worker_id": self.worker_id}
            )
            try:
                await self._ws.send(msg.to_json())
                await self._ws.close()
            except:
                pass
            self._ws = None

    async def run(self):
        """Main loop - connect and process messages."""
        self._running = True

        while self._running:
            if not self._ws or self._ws.closed:
                if not await self.connect():
                    logger.info(f"Reconnecting in {self._reconnect_delay}s...")
                    await asyncio.sleep(self._reconnect_delay)
                    continue

            try:
                # Start heartbeat task
                heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # Process messages
                async for message in self._ws:
                    await self._handle_message(message)

            except websockets.ConnectionClosed:
                logger.warning("Connection closed, reconnecting...")
            except Exception as e:
                logger.error(f"Error in message loop: {e}")
            finally:
                heartbeat_task.cancel()
                await asyncio.sleep(self._reconnect_delay)

    async def stop(self):
        """Stop the worker."""
        self._running = False
        await self.disconnect()

    async def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        while self._running and self._ws and not self._ws.closed:
            try:
                msg = WSMessage(
                    type=MessageType.WORKER_HEARTBEAT,
                    payload={"worker_id": self.worker_id}
                )
                await self._ws.send(msg.to_json())
                await asyncio.sleep(30)
            except:
                break

    async def _handle_message(self, raw: str):
        """Handle incoming message from server."""
        try:
            msg = WSMessage.from_json(raw)
            logger.debug(f"Received: {msg.type.value}")

            handler = {
                MessageType.CMD_SCAN_ASSETS: self._handle_scan,
                MessageType.CMD_GET_ASSET: self._handle_get_asset,
                MessageType.CMD_GET_IMAGE: self._handle_get_image,
                MessageType.CMD_SUBMIT_FEEDBACK: self._handle_feedback,
                MessageType.CMD_REGENERATE: self._handle_regenerate,
                MessageType.CMD_APPROVE: self._handle_approve,
            }.get(msg.type)

            if handler:
                response = await handler(msg)
                if response and self._ws:
                    await self._ws.send(response.to_json())
            else:
                logger.warning(f"Unknown message type: {msg.type}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            if self._ws:
                error_msg = create_error(str(e), "")
                await self._ws.send(error_msg.to_json())

    async def _handle_scan(self, msg: WSMessage) -> WSMessage:
        """Handle scan assets command."""
        project_filter = msg.payload.get("project")
        assets = []

        # Find all projects
        for project_dir in self.workspace.iterdir():
            if not project_dir.is_dir():
                continue
            if project_dir.name in ["studio", ".git"]:
                continue
            if project_filter and project_dir.name != project_filter:
                continue

            manifest_path = project_dir / "assets" / "manifest.json"
            if not manifest_path.exists():
                continue

            scanner = AssetScanner(project_dir)
            history_mgr = AssetHistoryManager(project_dir, self.studio_path)

            for spec in scanner.scan_all():
                history = history_mgr.load_history(spec.asset_id, spec.to_dict())

                # Get latest image as base64 (thumbnail)
                latest_image = None
                if history.generations:
                    img_path = Path(history.generations[-1].result_path)
                    if img_path.exists():
                        latest_image = self._image_to_base64(img_path, max_size=200)

                assets.append(AssetInfo(
                    asset_id=spec.asset_id,
                    project=project_dir.name,
                    category=spec.category,
                    status=history.status,
                    current_version=history.current_version,
                    spec=spec.to_dict(),
                    latest_image=latest_image
                ).to_dict())

        return create_response(
            MessageType.RESP_ASSETS_LIST,
            {"assets": assets},
            msg.request_id
        )

    async def _handle_get_asset(self, msg: WSMessage) -> WSMessage:
        """Handle get asset detail command."""
        project = msg.payload["project"]
        category = msg.payload["category"]
        asset_id = msg.payload["asset_id"]

        project_path = self.workspace / project
        history_mgr = AssetHistoryManager(project_path, self.studio_path)
        history = history_mgr.load_history(asset_id)

        generations = []
        for gen in history.generations:
            img_data = None
            img_path = Path(gen.result_path)
            if img_path.exists():
                img_data = self._image_to_base64(img_path)

            generations.append(GenerationInfo(
                version=gen.version,
                timestamp=gen.timestamp,
                prompt=gen.prompt,
                image_data=img_data,
                feedback=gen.feedback.to_dict() if gen.feedback else None
            ))

        detail = AssetDetailPayload(
            asset_id=asset_id,
            project=project,
            category=category,
            status=history.status,
            spec=history.spec,
            generations=generations
        )

        return create_response(
            MessageType.RESP_ASSET_DETAIL,
            detail.to_dict(),
            msg.request_id
        )

    async def _handle_get_image(self, msg: WSMessage) -> WSMessage:
        """Handle get image command - returns base64 encoded image."""
        path = msg.payload["path"]

        # Security: ensure path is within generations folder
        full_path = self.studio_path / "generations" / path
        if not full_path.exists():
            return create_error(f"Image not found: {path}", msg.request_id)

        img_data = self._image_to_base64(full_path)

        return create_response(
            MessageType.RESP_IMAGE_DATA,
            {"path": path, "data": img_data},
            msg.request_id
        )

    async def _handle_feedback(self, msg: WSMessage) -> WSMessage:
        """Handle feedback submission."""
        p = msg.payload
        project = p["project"]
        asset_id = p["asset_id"]

        project_path = self.workspace / project
        history_mgr = AssetHistoryManager(project_path, self.studio_path)
        history = history_mgr.load_history(asset_id)

        # Build feedback object
        feedback = AssetFeedback(
            version=history.current_version,
            asset_id=asset_id,
            decision=ReviewDecision(p["decision"]),
            issues=[FeedbackIssue(i) for i in p.get("issues", [])],
            free_text=p.get("free_text", ""),
            specific_requests=[
                SpecificRequest.from_dict(r) for r in p.get("specific_requests", [])
            ],
            change_intensity=ChangeIntensity(p.get("change_intensity", "moderate"))
        )

        history_mgr.submit_feedback(asset_id, feedback)

        return create_response(
            MessageType.RESP_FEEDBACK_SAVED,
            {"asset_id": asset_id, "status": history.status},
            msg.request_id
        )

    async def _handle_regenerate(self, msg: WSMessage) -> WSMessage:
        """Handle regeneration command."""
        project = msg.payload["project"]
        asset_id = msg.payload["asset_id"]

        # Notify that generation started
        start_msg = create_response(
            MessageType.RESP_GENERATION_STARTED,
            {"asset_id": asset_id, "project": project},
            msg.request_id
        )
        if self._ws:
            await self._ws.send(start_msg.to_json())

        try:
            # Execute regeneration
            if self.on_regenerate:
                result = await self.on_regenerate(project, asset_id)
            else:
                result = await self._default_regenerate(project, asset_id)

            return create_response(
                MessageType.RESP_GENERATION_COMPLETE,
                {
                    "asset_id": asset_id,
                    "project": project,
                    "success": result.get("success", False),
                    "new_version": result.get("version"),
                    "image_data": result.get("image_data")
                },
                msg.request_id
            )
        except Exception as e:
            return create_error(f"Regeneration failed: {e}", msg.request_id)

    async def _default_regenerate(self, project: str, asset_id: str) -> dict:
        """Default regeneration using FeedbackProcessor."""
        from .feedback_processor import FeedbackProcessor

        project_path = self.workspace / project
        processor = FeedbackProcessor(project_path, self.studio_path)

        # This is a sync call, run in executor
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: processor.regenerate_from_feedback(asset_id)
        )

        # Get the new image as base64
        history_mgr = AssetHistoryManager(project_path, self.studio_path)
        history = history_mgr.load_history(asset_id)

        image_data = None
        if history.generations:
            img_path = Path(history.generations[-1].result_path)
            if img_path.exists():
                image_data = self._image_to_base64(img_path)

        return {
            "success": result is not None,
            "version": history.current_version,
            "image_data": image_data
        }

    async def _handle_approve(self, msg: WSMessage) -> WSMessage:
        """Handle approval command."""
        project = msg.payload["project"]
        category = msg.payload["category"]
        asset_id = msg.payload["asset_id"]

        project_path = self.workspace / project
        history_mgr = AssetHistoryManager(project_path, self.studio_path)

        # Determine target path from spec
        history = history_mgr.load_history(asset_id)
        spec = history.spec

        # Get output path from spec
        if "output_path" in spec:
            target = project_path / spec["output_path"]
        else:
            # Default: assets/{category}/{asset_id}.png
            target = project_path / "assets" / category / f"{asset_id}.png"

        success = history_mgr.approve_asset(asset_id, target)

        return create_response(
            MessageType.RESP_APPROVED,
            {"asset_id": asset_id, "success": success, "target_path": str(target)},
            msg.request_id
        )

    def _image_to_base64(self, path: Path, max_size: Optional[int] = None) -> str:
        """Convert image to base64, optionally resize."""
        try:
            from PIL import Image
            import io

            img = Image.open(path)

            if max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode('utf-8')

        except ImportError:
            # Fallback without PIL
            with open(path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')


async def run_worker(
    workspace: str,
    remote_url: str = "ws://localhost:8081/ws/worker",
    worker_id: str = "local-1"
):
    """Run the local worker."""
    worker = LocalWorker(
        workspace_path=Path(workspace),
        remote_url=remote_url,
        worker_id=worker_id
    )

    try:
        await worker.run()
    except KeyboardInterrupt:
        await worker.stop()


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Local worker for remote UI")
    parser.add_argument("--workspace", "-w", required=True, help="Workspace path")
    parser.add_argument("--url", "-u", default="ws://localhost:8081/ws/worker", help="Remote server URL")
    parser.add_argument("--id", default="local-1", help="Worker ID")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    asyncio.run(run_worker(args.workspace, args.url, args.id))


if __name__ == "__main__":
    main()
