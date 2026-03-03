"""
Style Transfer / Stylization Module

Apply various pixel art styles (Deceiver, Loop Hero, etc.)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal

import numpy as np
from PIL import Image, ImageEnhance


@dataclass
class StyleConfig:
    """Configuration for stylization."""
    name: str
    pixelate_factor: float = 0.5      # 1.0 = no pixelation, 0.25 = very pixelated
    colors: int = 24                   # Number of colors after quantization
    dither_strength: float = 15.0      # Ordered dithering strength
    saturation: float = 0.75           # Color saturation (1.0 = original)
    brightness: float = 0.92           # Brightness (1.0 = original)
    contrast: float = 1.0              # Contrast (1.0 = original)
    use_palette: bool = False          # Use fixed palette
    palette: Optional[list] = None     # RGB tuples for fixed palette


# Predefined styles
STYLES = {
    "deceiver": StyleConfig(
        name="deceiver",
        pixelate_factor=0.5,
        colors=24,
        dither_strength=25,
        saturation=0.75,
        brightness=0.92
    ),
    "deceiver_rough": StyleConfig(
        name="deceiver_rough",
        pixelate_factor=0.35,
        colors=24,
        dither_strength=30,
        saturation=0.70,
        brightness=0.88
    ),
    "loop_hero": StyleConfig(
        name="loop_hero",
        pixelate_factor=0.3,
        colors=16,
        dither_strength=35,
        saturation=0.65,
        brightness=0.85
    ),
    "clean": StyleConfig(
        name="clean",
        pixelate_factor=0.5,
        colors=48,
        dither_strength=8,
        saturation=0.85,
        brightness=0.95
    ),
    "retro": StyleConfig(
        name="retro",
        pixelate_factor=0.25,
        colors=16,
        dither_strength=40,
        saturation=0.60,
        brightness=0.80
    ),
    "game_ui": StyleConfig(
        name="game_ui",
        pixelate_factor=0.55,
        colors=32,
        dither_strength=12,
        saturation=0.90,
        brightness=0.95
    )
}


# Bayer dithering matrix (4x4)
BAYER_4X4 = np.array([
    [ 0,  8,  2, 10],
    [12,  4, 14,  6],
    [ 3, 11,  1,  9],
    [15,  7, 13,  5]
], dtype=np.float32) / 16.0 - 0.5


def apply_ordered_dithering(image: np.ndarray, strength: float = 15.0) -> np.ndarray:
    """Apply Bayer ordered dithering to image array."""
    h, w = image.shape[:2]

    # Tile the Bayer matrix to match image size
    threshold = np.tile(BAYER_4X4, (h // 4 + 1, w // 4 + 1))[:h, :w]

    # Apply to all channels
    if len(image.shape) == 3:
        threshold = np.stack([threshold] * image.shape[2], axis=-1)

    # Add threshold noise
    result = image.astype(np.float32) + threshold * strength
    return np.clip(result, 0, 255).astype(np.uint8)


def pixelate(image: Image.Image, factor: float) -> Image.Image:
    """
    Pixelate image by downscaling and upscaling with nearest neighbor.

    Args:
        image: Input image
        factor: Scale factor (0.5 = half size intermediate)

    Returns:
        Pixelated image at original size
    """
    if factor >= 1.0:
        return image

    original_size = image.size

    # Downscale
    small_size = (
        max(1, int(original_size[0] * factor)),
        max(1, int(original_size[1] * factor))
    )
    small = image.resize(small_size, Image.Resampling.BILINEAR)

    # Upscale with nearest neighbor
    return small.resize(original_size, Image.Resampling.NEAREST)


def quantize_colors(image: Image.Image, colors: int) -> Image.Image:
    """
    Reduce image to limited color palette.

    Args:
        image: Input image (RGB)
        colors: Number of colors

    Returns:
        Quantized image
    """
    rgb = image.convert("RGB")
    return rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert("RGB")


def adjust_colors(
    image: Image.Image,
    saturation: float = 1.0,
    brightness: float = 1.0,
    contrast: float = 1.0
) -> Image.Image:
    """Apply color adjustments."""
    result = image

    if saturation != 1.0:
        enhancer = ImageEnhance.Color(result)
        result = enhancer.enhance(saturation)

    if brightness != 1.0:
        enhancer = ImageEnhance.Brightness(result)
        result = enhancer.enhance(brightness)

    if contrast != 1.0:
        enhancer = ImageEnhance.Contrast(result)
        result = enhancer.enhance(contrast)

    return result


def stylize(
    image: Image.Image,
    style: str | StyleConfig = "deceiver"
) -> Image.Image:
    """
    Apply style to image.

    Args:
        image: Input image
        style: Style name or StyleConfig

    Returns:
        Stylized image
    """
    # Get config
    if isinstance(style, str):
        if style not in STYLES:
            raise ValueError(f"Unknown style: {style}. Available: {list(STYLES.keys())}")
        config = STYLES[style]
    else:
        config = style

    # Ensure RGB
    img = image.convert("RGB")
    original_size = img.size

    # 1. Pixelation
    if config.pixelate_factor < 1.0:
        img = pixelate(img, config.pixelate_factor)

    # 2. Color quantization
    img = quantize_colors(img, config.colors)

    # 3. Ordered dithering
    if config.dither_strength > 0:
        arr = np.array(img)
        arr = apply_ordered_dithering(arr, config.dither_strength)
        img = Image.fromarray(arr)

        # Re-quantize for cleaner result
        img = quantize_colors(img, config.colors + 8)

    # 4. Color adjustments
    img = adjust_colors(
        img,
        saturation=config.saturation,
        brightness=config.brightness,
        contrast=config.contrast
    )

    return img


def stylize_file(
    input_path: str,
    output_path: str,
    style: str = "deceiver"
) -> str:
    """
    Stylize image file.

    Args:
        input_path: Input image path
        output_path: Output image path
        style: Style name

    Returns:
        Output path
    """
    image = Image.open(input_path)
    result = stylize(image, style)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path)

    return output_path


def stylize_batch(
    input_dir: str,
    output_dir: str,
    style: str = "deceiver",
    extensions: tuple = (".png", ".jpg", ".jpeg", ".webp")
) -> list[str]:
    """
    Stylize all images in directory.

    Args:
        input_dir: Input directory
        output_dir: Output directory
        style: Style name
        extensions: File extensions to process

    Returns:
        List of output paths
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    outputs = []
    for file in input_path.iterdir():
        if file.suffix.lower() in extensions:
            out_file = output_path / f"{file.stem}_styled.png"
            stylize_file(str(file), str(out_file), style)
            outputs.append(str(out_file))

    return outputs


def list_styles() -> list[str]:
    """Get list of available style names."""
    return list(STYLES.keys())


def get_style_config(name: str) -> StyleConfig:
    """Get style configuration by name."""
    if name not in STYLES:
        raise ValueError(f"Unknown style: {name}")
    return STYLES[name]
