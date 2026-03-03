"""
Sprite Animation Module

AI-powered sprite animation for pixel art.
Uses PixelLab API to generate frame-by-frame animations.

NOT for 3D model animation - this is 2D sprite/pixel art only.
"""

import base64
import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import requests
from PIL import Image


PIXELLAB_API = "https://api.pixellab.ai/v1"

# Animation presets
ANIMATION_PRESETS = {
    "idle": {
        "action": "idle breathing",
        "n_frames": 4,
        "loop": True,
        "ping_pong": True
    },
    "walk": {
        "action": "walk cycle",
        "n_frames": 4,
        "loop": True,
        "ping_pong": True
    },
    "run": {
        "action": "run cycle",
        "n_frames": 4,
        "loop": True,
        "ping_pong": False
    },
    "attack": {
        "action": "attack swing",
        "n_frames": 4,
        "loop": False,
        "ping_pong": False
    },
    "attack_sword": {
        "action": "sword attack swing",
        "n_frames": 4,
        "loop": False,
        "ping_pong": False
    },
    "attack_magic": {
        "action": "cast magic spell",
        "n_frames": 4,
        "loop": False,
        "ping_pong": False
    },
    "jump": {
        "action": "jump up and land",
        "n_frames": 4,
        "loop": False,
        "ping_pong": False
    },
    "hurt": {
        "action": "take damage hit reaction",
        "n_frames": 4,
        "loop": False,
        "ping_pong": False
    },
    "death": {
        "action": "death fall down",
        "n_frames": 4,
        "loop": False,
        "ping_pong": False
    },
    "item_use": {
        "action": "use item interact",
        "n_frames": 4,
        "loop": False,
        "ping_pong": False
    }
}

ViewType = Literal["side", "low top-down", "high top-down"]
DirectionType = Literal["north", "northeast", "east", "southeast",
                        "south", "southwest", "west", "northwest"]


@dataclass
class SpriteAnimationConfig:
    """Configuration for sprite animation generation."""
    description: str              # What the sprite is (e.g., "knight in armor")
    action: str                   # What it does (e.g., "walk cycle")
    n_frames: int = 4             # Number of frames (API returns max 4)
    view: ViewType = "side"       # Camera view
    direction: DirectionType = "east"  # Facing direction
    size: int = 64                # Sprite size (64x64)
    loop: bool = True             # Is animation looping
    ping_pong: bool = False       # Ping-pong loop (0-1-2-3-2-1-0)
    frame_duration_ms: int = 120  # Frame duration for GIF


@dataclass
class SpriteAnimationResult:
    """Result of sprite animation generation."""
    success: bool
    frames: list[Image.Image] = field(default_factory=list)
    error: Optional[str] = None
    config: Optional[SpriteAnimationConfig] = None


def get_api_key() -> str:
    """Get PixelLab API key."""
    key = os.environ.get("PIXELLAB_API_KEY", "")
    if key:
        return key

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


def image_to_base64(image: Image.Image) -> str:
    """Convert PIL Image to base64."""
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def animate_sprite(
    reference_image: Image.Image | str,
    config: SpriteAnimationConfig
) -> SpriteAnimationResult:
    """
    Generate sprite animation frames using PixelLab API.

    Args:
        reference_image: Base sprite (PIL Image or path)
        config: Animation configuration

    Returns:
        SpriteAnimationResult with frames
    """
    api_key = get_api_key()
    if not api_key:
        return SpriteAnimationResult(
            success=False,
            error="PIXELLAB_API_KEY not found"
        )

    # Load image if path
    if isinstance(reference_image, str):
        reference_image = Image.open(reference_image)

    # Resize to target size
    reference_image = reference_image.convert("RGBA")
    reference_image = reference_image.resize(
        (config.size, config.size),
        Image.Resampling.LANCZOS
    )

    # Prepare request
    payload = {
        "reference_image": {
            "type": "base64",
            "base64": image_to_base64(reference_image)
        },
        "image_size": {"width": config.size, "height": config.size},
        "description": config.description,
        "action": config.action,
        "n_frames": config.n_frames,
        "view": config.view,
        "direction": config.direction
    }

    try:
        response = requests.post(
            f"{PIXELLAB_API}/animate-with-text",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=300
        )

        if response.status_code == 200:
            data = response.json()
            frames = []
            for img_data in data.get("images", []):
                img_bytes = base64.b64decode(img_data["base64"])
                img = Image.open(io.BytesIO(img_bytes))
                frames.append(img)

            return SpriteAnimationResult(
                success=True,
                frames=frames,
                config=config
            )
        else:
            return SpriteAnimationResult(
                success=False,
                error=f"HTTP {response.status_code}: {response.text[:200]}"
            )

    except Exception as e:
        return SpriteAnimationResult(success=False, error=str(e))


def animate_sprite_preset(
    reference_image: Image.Image | str,
    description: str,
    preset: str,
    view: ViewType = "side",
    direction: DirectionType = "east",
    size: int = 64
) -> SpriteAnimationResult:
    """
    Generate sprite animation using preset.

    Args:
        reference_image: Base sprite
        description: What the sprite is
        preset: Animation preset name (idle, walk, run, attack, etc.)
        view: Camera view
        direction: Facing direction
        size: Sprite size

    Returns:
        SpriteAnimationResult
    """
    if preset not in ANIMATION_PRESETS:
        return SpriteAnimationResult(
            success=False,
            error=f"Unknown preset: {preset}. Available: {list(ANIMATION_PRESETS.keys())}"
        )

    preset_config = ANIMATION_PRESETS[preset]
    config = SpriteAnimationConfig(
        description=description,
        action=preset_config["action"],
        n_frames=preset_config["n_frames"],
        view=view,
        direction=direction,
        size=size,
        loop=preset_config["loop"],
        ping_pong=preset_config["ping_pong"]
    )

    return animate_sprite(reference_image, config)


def save_animation_frames(
    result: SpriteAnimationResult,
    output_dir: str,
    prefix: str = "frame"
) -> list[str]:
    """
    Save animation frames to directory.

    Args:
        result: Animation result with frames
        output_dir: Output directory
        prefix: Filename prefix

    Returns:
        List of saved file paths
    """
    if not result.success or not result.frames:
        return []

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved = []
    for i, frame in enumerate(result.frames):
        path = output_path / f"{prefix}_{i:02d}.png"
        frame.save(path)
        saved.append(str(path))

    return saved


def create_sprite_gif(
    result: SpriteAnimationResult,
    output_path: str,
    scale: int = 1,
    duration_ms: Optional[int] = None
) -> Optional[str]:
    """
    Create GIF from animation frames.

    Args:
        result: Animation result with frames
        output_path: Output GIF path
        scale: Upscale factor (use NEAREST for pixel art)
        duration_ms: Frame duration (uses config default if None)

    Returns:
        Output path or None on error
    """
    if not result.success or not result.frames:
        return None

    frames = result.frames
    config = result.config

    # Scale frames
    if scale > 1:
        size = frames[0].size
        new_size = (size[0] * scale, size[1] * scale)
        frames = [
            f.resize(new_size, Image.Resampling.NEAREST)
            for f in frames
        ]

    # Build frame sequence
    if config and config.ping_pong and len(frames) > 2:
        # Ping-pong: 0-1-2-3-2-1
        sequence = frames + frames[-2:0:-1]
    else:
        sequence = frames

    # Duration
    duration = duration_ms
    if duration is None and config:
        duration = config.frame_duration_ms
    if duration is None:
        duration = 120

    # Save GIF
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    sequence[0].save(
        output_path,
        save_all=True,
        append_images=sequence[1:],
        duration=duration,
        loop=0
    )

    return output_path


def create_sprite_sheet(
    result: SpriteAnimationResult,
    output_path: str,
    columns: Optional[int] = None,
    scale: int = 1
) -> Optional[str]:
    """
    Create sprite sheet from animation frames.

    Args:
        result: Animation result with frames
        output_path: Output PNG path
        columns: Number of columns (None = all in one row)
        scale: Upscale factor

    Returns:
        Output path or None on error
    """
    if not result.success or not result.frames:
        return None

    frames = result.frames
    n_frames = len(frames)
    frame_size = frames[0].size

    # Calculate layout
    if columns is None:
        columns = n_frames
    rows = (n_frames + columns - 1) // columns

    # Create sheet
    sheet_width = frame_size[0] * columns * scale
    sheet_height = frame_size[1] * rows * scale
    sheet = Image.new('RGBA', (sheet_width, sheet_height), (0, 0, 0, 0))

    # Paste frames
    for i, frame in enumerate(frames):
        col = i % columns
        row = i // columns
        x = col * frame_size[0] * scale
        y = row * frame_size[1] * scale

        if scale > 1:
            frame = frame.resize(
                (frame_size[0] * scale, frame_size[1] * scale),
                Image.Resampling.NEAREST
            )

        sheet.paste(frame, (x, y))

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)

    return output_path


def generate_character_animations(
    reference_image: Image.Image | str,
    description: str,
    output_dir: str,
    presets: list[str] = ["idle", "walk", "attack"],
    directions: list[DirectionType] = ["east"],
    size: int = 64,
    create_gifs: bool = True,
    create_sheets: bool = True,
    gif_scale: int = 4
) -> dict[str, dict]:
    """
    Generate multiple animations for a character.

    Args:
        reference_image: Base sprite
        description: Character description
        output_dir: Output directory
        presets: List of animation presets
        directions: List of directions
        size: Sprite size
        create_gifs: Create GIF files
        create_sheets: Create sprite sheets
        gif_scale: GIF upscale factor

    Returns:
        Dict mapping preset -> direction -> result info
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {}

    for preset in presets:
        results[preset] = {}

        for direction in directions:
            # Generate animation
            result = animate_sprite_preset(
                reference_image=reference_image,
                description=description,
                preset=preset,
                direction=direction,
                size=size
            )

            dir_suffix = f"_{direction}" if len(directions) > 1 else ""
            anim_name = f"{preset}{dir_suffix}"

            info = {
                "success": result.success,
                "frames": len(result.frames) if result.success else 0,
                "error": result.error
            }

            if result.success:
                # Save frames
                frames_dir = output_path / f"{anim_name}_frames"
                info["frames_dir"] = str(frames_dir)
                save_animation_frames(result, str(frames_dir), prefix=anim_name)

                # Create GIF
                if create_gifs:
                    gif_path = output_path / f"{anim_name}.gif"
                    create_sprite_gif(result, str(gif_path), scale=gif_scale)
                    info["gif"] = str(gif_path)

                # Create sprite sheet
                if create_sheets:
                    sheet_path = output_path / f"{anim_name}_sheet.png"
                    create_sprite_sheet(result, str(sheet_path))
                    info["sheet"] = str(sheet_path)

            results[preset][direction] = info

    return results


def list_presets() -> list[str]:
    """Get list of available animation presets."""
    return list(ANIMATION_PRESETS.keys())


def get_preset_info(preset: str) -> dict:
    """Get preset configuration info."""
    if preset not in ANIMATION_PRESETS:
        raise ValueError(f"Unknown preset: {preset}")
    return ANIMATION_PRESETS[preset].copy()
