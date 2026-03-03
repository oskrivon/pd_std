"""
PixelLab + Deceiver Style Pipeline

Генерация пиксель-арта через PixelLab API с постобработкой в стиле Deceiver.

Использование:
    python pixellab_deceiver.py generate "dark mage with hood" output.png
    python pixellab_deceiver.py generate "warrior knight" output.png --ref style_ref.png
    python pixellab_deceiver.py postprocess input.png output.png
"""

import argparse
import base64
import io
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import requests
from PIL import Image, ImageEnhance

# PixelLab API
PIXELLAB_API = "https://api.pixellab.ai/v1"
API_KEY = os.environ.get("PIXELLAB_API_KEY", "")


def get_api_key() -> str:
    """Получить API ключ."""
    if API_KEY:
        return API_KEY

    # Попробовать из .env
    env_paths = [
        Path(__file__).parent.parent.parent / "config" / ".env",
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
    """Конвертировать PIL Image в base64."""
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def load_and_resize(path: str, size: tuple[int, int]) -> str:
    """Загрузить изображение, ресайзнуть и вернуть base64."""
    img = Image.open(path).convert('RGB')
    img = img.resize(size, Image.Resampling.LANCZOS)
    return image_to_base64(img)


def generate_pixellab(
    description: str,
    width: int = 400,
    height: int = 400,
    init_image_path: Optional[str] = None,
    init_strength: int = 70,
    no_background: bool = True
) -> Optional[Image.Image]:
    """
    Сгенерировать изображение через PixelLab.

    Args:
        description: Текстовое описание
        width, height: Размер (max 400x400 для pixflux)
        init_image_path: Путь к референсу (опционально)
        init_strength: Сила влияния референса (0-100)
        no_background: Прозрачный фон

    Returns:
        PIL Image или None при ошибке
    """
    api_key = get_api_key()
    if not api_key:
        print("Error: PIXELLAB_API_KEY не найден")
        return None

    payload = {
        "description": description,
        "image_size": {"width": width, "height": height},
        "no_background": no_background
    }

    if init_image_path:
        payload["init_image"] = {
            "type": "base64",
            "base64": load_and_resize(init_image_path, (width, height))
        }
        payload["init_image_strength"] = init_strength

    try:
        response = requests.post(
            f"{PIXELLAB_API}/generate-image-pixflux",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=180
        )

        if response.status_code == 200:
            data = response.json()
            img_data = base64.b64decode(data["image"]["base64"])
            return Image.open(io.BytesIO(img_data))
        else:
            print(f"Error {response.status_code}: {response.text[:200]}")
            return None

    except Exception as e:
        print(f"Request error: {e}")
        return None


def postprocess_deceiver(
    image: Image.Image,
    pixelate_factor: float = 0.5,
    colors: int = 24,
    dither_strength: float = 25,
    saturation: float = 0.75,
    brightness: float = 0.92
) -> Image.Image:
    """
    Применить постобработку в стиле Deceiver.

    Args:
        image: Входное изображение
        pixelate_factor: Коэффициент пикселизации (0.5 = 50% размера)
        colors: Количество цветов после квантизации
        dither_strength: Сила ordered dithering
        saturation: Насыщенность (0-1)
        brightness: Яркость (0-1)

    Returns:
        Обработанное изображение
    """
    img = image.convert('RGB')
    original_size = img.size

    # 1. Пикселизация
    if pixelate_factor < 1.0:
        small_size = (
            int(original_size[0] * pixelate_factor),
            int(original_size[1] * pixelate_factor)
        )
        img = img.resize(small_size, Image.Resampling.BILINEAR)
        img = img.resize(original_size, Image.Resampling.NEAREST)

    # 2. Квантизация
    img = img.quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert('RGB')

    # 3. Ordered dithering (Bayer 4x4)
    arr = np.array(img, dtype=np.float32)
    bayer = np.array([
        [ 0,  8,  2, 10],
        [12,  4, 14,  6],
        [ 3, 11,  1,  9],
        [15,  7, 13,  5]
    ], dtype=np.float32) / 16.0 - 0.5

    h, w = arr.shape[:2]
    threshold = np.tile(bayer, (h // 4 + 1, w // 4 + 1))[:h, :w]
    threshold = np.stack([threshold] * 3, axis=-1) * dither_strength

    arr = np.clip(arr + threshold, 0, 255).astype(np.uint8)

    # 4. Повторная квантизация для чёткости
    img = Image.fromarray(arr)
    img = img.quantize(colors=colors + 8).convert('RGB')

    # 5. Цветокоррекция
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(brightness)

    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(saturation)

    return img


def generate_deceiver_style(
    description: str,
    output_path: str,
    ref_image_path: Optional[str] = None,
    width: int = 400,
    height: int = 400,
    init_strength: int = 70,
    apply_postprocess: bool = True
) -> bool:
    """
    Полный пайплайн: PixelLab + постобработка Deceiver.

    Args:
        description: Описание персонажа/сцены
        output_path: Путь для сохранения
        ref_image_path: Референс стиля (рекомендуется картинка Deceiver)
        width, height: Размер
        init_strength: Сила влияния референса
        apply_postprocess: Применять постобработку

    Returns:
        True если успешно
    """
    print(f"Generating: {description[:50]}...")

    # Генерация через PixelLab
    img = generate_pixellab(
        description=description,
        width=width,
        height=height,
        init_image_path=ref_image_path,
        init_strength=init_strength
    )

    if img is None:
        return False

    print("PixelLab done")

    # Постобработка
    if apply_postprocess:
        print("Applying Deceiver postprocess...")
        img = postprocess_deceiver(img)

    # Сохранение
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    print(f"Saved: {output_path}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="PixelLab + Deceiver Style Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Генерация с постобработкой
  python pixellab_deceiver.py generate "old wizard with staff" wizard.png

  # Генерация с референсом стиля
  python pixellab_deceiver.py generate "dark knight" knight.png --ref Warrior4.webp

  # Только постобработка существующего изображения
  python pixellab_deceiver.py postprocess input.png output.png
        """
    )

    subparsers = parser.add_subparsers(dest="command")

    # generate
    gen_parser = subparsers.add_parser("generate", help="Генерация через PixelLab + постобработка")
    gen_parser.add_argument("description", help="Описание для генерации")
    gen_parser.add_argument("output", help="Путь для сохранения")
    gen_parser.add_argument("--ref", help="Референс стиля (рекомендуется)")
    gen_parser.add_argument("--width", type=int, default=400, help="Ширина (max 400)")
    gen_parser.add_argument("--height", type=int, default=400, help="Высота (max 400)")
    gen_parser.add_argument("--strength", type=int, default=70, help="Сила референса (0-100)")
    gen_parser.add_argument("--no-postprocess", action="store_true", help="Без постобработки")

    # postprocess
    post_parser = subparsers.add_parser("postprocess", help="Только постобработка")
    post_parser.add_argument("input", help="Входное изображение")
    post_parser.add_argument("output", help="Выходное изображение")
    post_parser.add_argument("--pixelate", type=float, default=0.5, help="Фактор пикселизации")
    post_parser.add_argument("--colors", type=int, default=24, help="Количество цветов")
    post_parser.add_argument("--dither", type=float, default=25, help="Сила dithering")

    args = parser.parse_args()

    if args.command == "generate":
        success = generate_deceiver_style(
            description=args.description,
            output_path=args.output,
            ref_image_path=args.ref,
            width=min(args.width, 400),
            height=min(args.height, 400),
            init_strength=args.strength,
            apply_postprocess=not args.no_postprocess
        )
        return 0 if success else 1

    elif args.command == "postprocess":
        img = Image.open(args.input)
        result = postprocess_deceiver(
            img,
            pixelate_factor=args.pixelate,
            colors=args.colors,
            dither_strength=args.dither
        )
        result.save(args.output)
        print(f"Saved: {args.output}")
        return 0

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
