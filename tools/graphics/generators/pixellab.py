"""
PixelLab API Wrapper

Unified interface for PixelLab pixel art generation API.
"""

import base64
import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal

import requests
from PIL import Image


PIXELLAB_API = "https://api.pixellab.ai/v1"


def get_api_key() -> str:
    """Get API key from environment or config."""
    key = os.environ.get("PIXELLAB_API_KEY", "")
    if key:
        return key

    # Try config/.env
    env_paths = [
        Path(__file__).parent.parent.parent.parent / "config" / ".env",
        Path.cwd() / "config" / ".env",
        Path.cwd() / ".env"
    ]
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.startswith("PIXELLAB_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"\'')
    return ""


def image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """Convert PIL Image to base64 string."""
    buf = io.BytesIO()
    image.save(buf, format=format)
    return base64.b64encode(buf.getvalue()).decode()


def base64_to_image(b64: str) -> Image.Image:
    """Convert base64 string to PIL Image."""
    return Image.open(io.BytesIO(base64.b64decode(b64)))


def load_image(path: str, size: Optional[tuple[int, int]] = None) -> Image.Image:
    """Load image from path, optionally resize."""
    img = Image.open(path).convert("RGBA")
    if size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    return img


@dataclass
class PixelLabResult:
    """Result from PixelLab API call."""
    success: bool
    image: Optional[Image.Image] = None
    error: Optional[str] = None
    usage: Optional[dict] = None


class PixelLabClient:
    """PixelLab API client."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_api_key()
        if not self.api_key:
            raise ValueError("PIXELLAB_API_KEY not found")

    def _request(self, endpoint: str, payload: dict, timeout: int = 180) -> PixelLabResult:
        """Make API request."""
        try:
            response = requests.post(
                f"{PIXELLAB_API}/{endpoint}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=timeout
            )

            if response.status_code == 200:
                data = response.json()
                image = base64_to_image(data["image"]["base64"])
                return PixelLabResult(
                    success=True,
                    image=image,
                    usage=data.get("usage")
                )
            else:
                return PixelLabResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            return PixelLabResult(success=False, error=str(e))

    def get_balance(self) -> dict:
        """Get account balance."""
        response = requests.get(
            f"{PIXELLAB_API}/balance",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30
        )
        return response.json()

    def generate_pixflux(
        self,
        description: str,
        width: int = 64,
        height: int = 64,
        init_image: Optional[Image.Image] = None,
        init_strength: int = 70,
        no_background: bool = True
    ) -> PixelLabResult:
        """
        Generate image using Pixflux model.

        Args:
            description: Text description of what to generate
            width, height: Output size (max 400x400)
            init_image: Optional reference image for img2img
            init_strength: How much to preserve init_image (0-100)
            no_background: Generate with transparent background

        Returns:
            PixelLabResult with generated image
        """
        width = min(width, 400)
        height = min(height, 400)

        payload = {
            "description": description,
            "image_size": {"width": width, "height": height},
            "no_background": no_background
        }

        if init_image:
            resized = init_image.resize((width, height), Image.Resampling.LANCZOS)
            payload["init_image"] = {
                "type": "base64",
                "base64": image_to_base64(resized.convert("RGB"))
            }
            payload["init_image_strength"] = init_strength

        return self._request("generate-image-pixflux", payload)

    def generate_bitforge(
        self,
        description: str,
        width: int = 64,
        height: int = 64,
        style_image: Optional[Image.Image] = None,
        style_strength: int = 50,
        no_background: bool = True,
        outline: str = "single color black outline",
        shading: str = "detailed shading",
        detail: str = "highly detailed"
    ) -> PixelLabResult:
        """
        Generate image using Bitforge model.

        Args:
            description: Text description
            width, height: Output size (max 200x200)
            style_image: Style reference image
            style_strength: Style influence (0-100)
            no_background: Transparent background
            outline, shading, detail: Style parameters

        Returns:
            PixelLabResult with generated image
        """
        width = min(width, 200)
        height = min(height, 200)

        payload = {
            "description": description,
            "image_size": {"width": width, "height": height},
            "no_background": no_background,
            "outline": outline,
            "shading": shading,
            "detail": detail
        }

        if style_image:
            resized = style_image.resize((width, height), Image.Resampling.LANCZOS)
            payload["style_image"] = {
                "type": "base64",
                "base64": image_to_base64(resized.convert("RGB"))
            }
            payload["style_strength"] = style_strength

        return self._request("generate-image-bitforge", payload)

    def rotate(
        self,
        image: Image.Image,
        rotation: int,
        width: int = 64,
        height: int = 64
    ) -> PixelLabResult:
        """
        Generate rotated version of sprite.

        Args:
            image: Source sprite image
            rotation: Rotation angle in degrees (0, 45, 90, ...)
            width, height: Output size

        Returns:
            PixelLabResult with rotated image
        """
        width = min(width, 200)
        height = min(height, 200)

        resized = image.resize((width, height), Image.Resampling.LANCZOS)

        payload = {
            "from_image": {
                "type": "base64",
                "base64": image_to_base64(resized)
            },
            "image_size": {"width": width, "height": height},
            "rotation": rotation
        }

        return self._request("rotate", payload)

    def rotate_all(
        self,
        image: Image.Image,
        width: int = 64,
        height: int = 64,
        angles: int = 8
    ) -> list[PixelLabResult]:
        """
        Generate all rotations of sprite.

        Args:
            image: Source sprite
            width, height: Output size
            angles: Number of directions (4 or 8)

        Returns:
            List of PixelLabResult for each rotation
        """
        step = 360 // angles
        results = []

        for i in range(angles):
            rotation = i * step
            result = self.rotate(image, rotation, width, height)
            results.append(result)

        return results

    def animate_skeleton(
        self,
        image: Image.Image,
        animation: Literal["idle", "walk", "run", "jump", "attack"] = "idle",
        frames: int = 8,
        width: int = 64,
        height: int = 64
    ) -> PixelLabResult:
        """
        Generate animation using skeleton-based method.

        Args:
            image: Reference sprite
            animation: Animation type
            frames: Number of frames
            width, height: Output size

        Returns:
            PixelLabResult with animated sprite sheet
        """
        resized = image.resize((width, height), Image.Resampling.LANCZOS)

        payload = {
            "reference_image": {
                "type": "base64",
                "base64": image_to_base64(resized)
            },
            "image_size": {"width": width, "height": height},
            "animation": animation,
            "frames": frames
        }

        return self._request("animate-with-skeleton", payload, timeout=300)

    def animate_text(
        self,
        image: Image.Image,
        description: str,
        frames: int = 8,
        width: int = 64,
        height: int = 64
    ) -> PixelLabResult:
        """
        Generate animation using text description.

        Args:
            image: Reference sprite
            description: Animation description (e.g., "character walking forward")
            frames: Number of frames
            width, height: Output size

        Returns:
            PixelLabResult with animated sprite sheet
        """
        resized = image.resize((width, height), Image.Resampling.LANCZOS)

        payload = {
            "reference_image": {
                "type": "base64",
                "base64": image_to_base64(resized)
            },
            "image_size": {"width": width, "height": height},
            "description": description,
            "frames": frames
        }

        return self._request("animate-with-text", payload, timeout=300)


# Convenience functions
_client: Optional[PixelLabClient] = None

def get_client() -> PixelLabClient:
    """Get or create singleton client."""
    global _client
    if _client is None:
        _client = PixelLabClient()
    return _client


def generate(
    description: str,
    size: int = 64,
    ref_image: Optional[str] = None,
    ref_strength: int = 70,
    no_background: bool = True
) -> Optional[Image.Image]:
    """
    Quick generate function.

    Args:
        description: What to generate
        size: Output size (square)
        ref_image: Path to reference image
        ref_strength: Reference influence (0-100)
        no_background: Transparent background

    Returns:
        Generated PIL Image or None on error
    """
    client = get_client()

    init_img = None
    if ref_image:
        init_img = load_image(ref_image, (size, size))

    result = client.generate_pixflux(
        description=description,
        width=size,
        height=size,
        init_image=init_img,
        init_strength=ref_strength,
        no_background=no_background
    )

    return result.image if result.success else None


def rotate(
    image_path: str,
    output_dir: str,
    size: int = 64,
    angles: int = 8
) -> list[str]:
    """
    Generate rotations and save to directory.

    Args:
        image_path: Source sprite path
        output_dir: Output directory
        size: Output size
        angles: Number of directions

    Returns:
        List of saved file paths
    """
    client = get_client()
    image = load_image(image_path, (size, size))

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = client.rotate_all(image, size, size, angles)

    saved = []
    step = 360 // angles
    for i, result in enumerate(results):
        if result.success and result.image:
            angle = i * step
            path = output_path / f"rot_{angle:03d}.png"
            result.image.save(path)
            saved.append(str(path))

    return saved
