"""
Deceiver Style Transfer

Преобразование изображений в стиль Dmitry Karimov (Deceiver) / Loop Hero.

Характеристики стиля:
- Приглушённая "ржавая" палитра (коричневые, бордовые, тёмно-зелёные)
- Ограниченное количество цветов (16-32)
- Ordered dithering для текстурности
- Тёмный, мрачный фон
- Низкая насыщенность

Использование:
    python deceiver_style.py input.png output.png [--palette 16] [--dither]
"""

import colorsys
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
    import numpy as np
except ImportError:
    print("Требуется: pip install pillow numpy")
    sys.exit(1)


# ============================================================================
# ПАЛИТРА LOOP HERO / DECEIVER
# Извлечена из скриншотов игры
# ============================================================================

DECEIVER_PALETTE = [
    # Тёмные базовые
    (15, 15, 23),      # Почти чёрный
    (31, 28, 36),      # Тёмно-серый
    (51, 44, 52),      # Серо-фиолетовый
    (71, 63, 68),      # Тёплый серый

    # Коричневые / ржавые
    (92, 67, 55),      # Тёмно-коричневый
    (130, 87, 64),     # Коричневый
    (166, 111, 76),    # Светло-коричневый
    (189, 143, 100),   # Песочный

    # Красные / бордовые
    (103, 46, 48),     # Тёмно-бордовый
    (139, 64, 61),     # Бордовый
    (175, 90, 77),     # Красно-коричневый
    (199, 125, 100),   # Бледно-красный

    # Зелёные (приглушённые)
    (45, 55, 45),      # Тёмно-зелёный
    (67, 82, 61),      # Болотный
    (95, 115, 82),     # Приглушённый зелёный
    (130, 150, 110),   # Светло-болотный

    # Синие / серо-синие
    (40, 48, 62),      # Тёмно-синий
    (58, 72, 92),      # Серо-синий
    (82, 102, 128),    # Стальной
    (115, 140, 160),   # Светло-стальной

    # Жёлтые / золотые (акценты)
    (140, 110, 50),    # Тёмное золото
    (180, 145, 65),    # Золотой
    (215, 180, 90),    # Светлое золото
    (240, 215, 140),   # Бледно-жёлтый

    # Пурпурные (магия)
    (65, 45, 75),      # Тёмно-пурпурный
    (95, 65, 105),     # Пурпурный
    (130, 90, 140),    # Светло-пурпурный
    (165, 125, 175),   # Бледно-пурпурный

    # Светлые акценты
    (180, 170, 160),   # Светло-серый тёплый
    (210, 200, 185),   # Почти белый тёплый
    (235, 225, 210),   # Кремовый
    (250, 245, 235),   # Белый тёплый
]

# Ordered dithering matrix (Bayer 4x4)
BAYER_4X4 = np.array([
    [ 0,  8,  2, 10],
    [12,  4, 14,  6],
    [ 3, 11,  1,  9],
    [15,  7, 13,  5]
], dtype=np.float32) / 16.0


@dataclass
class StyleConfig:
    """Настройки стилизации."""
    palette_size: int = 32          # Количество цветов в палитре
    saturation: float = 0.55        # Множитель насыщенности (0-1)
    brightness: float = 0.85        # Множитель яркости
    contrast: float = 1.15          # Множитель контраста
    hue_shift: float = 15           # Сдвиг hue в сторону коричневого (градусы)
    dithering: bool = True          # Применять dithering
    dither_strength: float = 0.5    # Сила dithering (0-1)
    use_deceiver_palette: bool = True  # Использовать палитру Deceiver
    downscale: float = 1.0          # Коэффициент уменьшения для пиксельности


def rgb_to_hsv(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """RGB (0-255) -> HSV (0-360, 0-1, 0-1)."""
    return colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)


def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
    """HSV (0-1, 0-1, 0-1) -> RGB (0-255)."""
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def color_distance(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    """Евклидово расстояние между цветами в RGB."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def find_nearest_color(
    color: Tuple[int, int, int],
    palette: List[Tuple[int, int, int]]
) -> Tuple[int, int, int]:
    """Найти ближайший цвет из палитры."""
    return min(palette, key=lambda c: color_distance(color, c))


def extract_palette(image: Image.Image, num_colors: int = 32) -> List[Tuple[int, int, int]]:
    """Извлечь доминирующие цвета из изображения."""
    # Уменьшаем для скорости
    small = image.copy()
    small.thumbnail((150, 150))

    # Квантизация
    quantized = small.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT)
    palette_data = quantized.getpalette()

    colors = []
    for i in range(num_colors):
        r = palette_data[i * 3]
        g = palette_data[i * 3 + 1]
        b = palette_data[i * 3 + 2]
        colors.append((r, g, b))

    return colors


def shift_hue_to_warm(
    image: Image.Image,
    shift_degrees: float = 15
) -> Image.Image:
    """Сдвинуть оттенок в сторону тёплых тонов."""
    if image.mode != 'RGB':
        image = image.convert('RGB')

    pixels = np.array(image, dtype=np.float32) / 255.0

    # Конвертация в HSV
    r, g, b = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]

    max_c = np.maximum(np.maximum(r, g), b)
    min_c = np.minimum(np.minimum(r, g), b)
    diff = max_c - min_c

    # Hue
    h = np.zeros_like(max_c)
    mask = diff != 0

    r_mask = (max_c == r) & mask
    g_mask = (max_c == g) & mask
    b_mask = (max_c == b) & mask

    h[r_mask] = (60 * ((g[r_mask] - b[r_mask]) / diff[r_mask]) + 360) % 360
    h[g_mask] = (60 * ((b[g_mask] - r[g_mask]) / diff[g_mask]) + 120) % 360
    h[b_mask] = (60 * ((r[b_mask] - g[b_mask]) / diff[b_mask]) + 240) % 360

    # Сдвиг hue к тёплым (оранжевый ~30 градусов)
    # Сдвигаем холодные цвета (180-300) в сторону тёплых
    cold_mask = (h > 150) & (h < 300)
    h[cold_mask] = h[cold_mask] - shift_degrees
    h = h % 360

    # Обратная конвертация
    h_norm = h / 360.0

    c = diff
    x = c * (1 - np.abs((h / 60) % 2 - 1))
    m = min_c

    result = np.zeros_like(pixels)

    for i, (h_low, h_high, rgb_order) in enumerate([
        (0, 60, (0, 1, 2)),     # r, g, b mapping for c, x, 0
        (60, 120, (1, 0, 2)),
        (120, 180, (2, 0, 1)),
        (180, 240, (2, 1, 0)),
        (240, 300, (1, 2, 0)),
        (300, 360, (0, 2, 1)),
    ]):
        mask = (h >= h_low) & (h < h_high)
        vals = [c, x, np.zeros_like(c)]
        result[mask, 0] = vals[rgb_order.index(0)][mask] + m[mask]
        result[mask, 1] = vals[rgb_order.index(1)][mask] + m[mask]
        result[mask, 2] = vals[rgb_order.index(2)][mask] + m[mask]

    result = np.clip(result * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(result)


def apply_ordered_dithering(
    image: Image.Image,
    palette: List[Tuple[int, int, int]],
    strength: float = 0.5
) -> Image.Image:
    """Применить ordered dithering (Bayer)."""
    if image.mode != 'RGB':
        image = image.convert('RGB')

    pixels = np.array(image, dtype=np.float32)
    height, width = pixels.shape[:2]

    # Создаём тайловый threshold map
    threshold = np.tile(
        BAYER_4X4,
        (height // 4 + 1, width // 4 + 1)
    )[:height, :width]

    # Применяем threshold
    threshold = (threshold - 0.5) * strength * 64  # Масштаб для 8-bit

    result = np.zeros_like(pixels, dtype=np.uint8)

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[y, x]

            # Добавляем threshold
            r = int(np.clip(r + threshold[y, x], 0, 255))
            g = int(np.clip(g + threshold[y, x], 0, 255))
            b = int(np.clip(b + threshold[y, x], 0, 255))

            # Находим ближайший цвет
            nearest = find_nearest_color((r, g, b), palette)
            result[y, x] = nearest

    return Image.fromarray(result)


def apply_palette_fast(
    image: Image.Image,
    palette: List[Tuple[int, int, int]]
) -> Image.Image:
    """Быстрое применение палитры через квантизацию PIL."""
    if image.mode != 'RGB':
        image = image.convert('RGB')

    # Создаём палитру для PIL
    pal_image = Image.new('P', (1, 1))
    flat_palette = []
    for r, g, b in palette:
        flat_palette.extend([r, g, b])

    # Дополняем до 256 цветов
    while len(flat_palette) < 768:
        flat_palette.extend([0, 0, 0])

    pal_image.putpalette(flat_palette)

    # Квантизируем
    quantized = image.quantize(palette=pal_image, dither=Image.Dither.NONE)
    return quantized.convert('RGB')


def deceiver_stylize(
    input_path: str,
    output_path: str,
    config: Optional[StyleConfig] = None
) -> dict:
    """
    Применить стиль Deceiver к изображению.

    Args:
        input_path: Путь к входному изображению
        output_path: Путь для сохранения результата
        config: Настройки стилизации

    Returns:
        dict с информацией о результате
    """
    if config is None:
        config = StyleConfig()

    # Загрузка
    image = Image.open(input_path)
    original_size = image.size

    if image.mode != 'RGB':
        image = image.convert('RGB')

    # 1. Даунскейл для пиксельности (опционально)
    if config.downscale < 1.0:
        new_size = (
            int(image.width * config.downscale),
            int(image.height * config.downscale)
        )
        image = image.resize(new_size, Image.Resampling.NEAREST)

    # 2. Коррекция контраста
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(config.contrast)

    # 3. Коррекция яркости
    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(config.brightness)

    # 4. Снижение насыщенности
    enhancer = ImageEnhance.Color(image)
    image = enhancer.enhance(config.saturation)

    # 5. Сдвиг hue к тёплым тонам
    if config.hue_shift > 0:
        image = shift_hue_to_warm(image, config.hue_shift)

    # 6. Выбор палитры
    if config.use_deceiver_palette:
        palette = DECEIVER_PALETTE[:config.palette_size]
    else:
        palette = extract_palette(image, config.palette_size)

    # 7. Применение палитры с/без dithering
    if config.dithering:
        image = apply_ordered_dithering(image, palette, config.dither_strength)
    else:
        image = apply_palette_fast(image, palette)

    # 8. Апскейл обратно (если был даунскейл)
    if config.downscale < 1.0:
        image = image.resize(original_size, Image.Resampling.NEAREST)

    # Сохранение
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)

    return {
        "success": True,
        "input": input_path,
        "output": output_path,
        "original_size": original_size,
        "palette_size": len(palette),
        "config": {
            "saturation": config.saturation,
            "brightness": config.brightness,
            "contrast": config.contrast,
            "dithering": config.dithering,
            "downscale": config.downscale
        }
    }


def batch_stylize(
    input_dir: str,
    output_dir: str,
    config: Optional[StyleConfig] = None
) -> List[dict]:
    """Обработать все изображения в папке."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    image_exts = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
    results = []

    for img_file in input_path.iterdir():
        if img_file.suffix.lower() in image_exts:
            out_file = output_path / f"{img_file.stem}_deceiver.png"
            print(f"Processing: {img_file.name}")

            try:
                result = deceiver_stylize(str(img_file), str(out_file), config)
                results.append(result)
            except Exception as e:
                results.append({
                    "success": False,
                    "input": str(img_file),
                    "error": str(e)
                })

    return results


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Стилизация изображений в стиле Deceiver / Loop Hero",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s input.png output.png
  %(prog)s input.png output.png --palette 16 --dither
  %(prog)s input.png output.png --no-dither --saturation 0.4
  %(prog)s --batch input_dir/ output_dir/
        """
    )

    parser.add_argument("input", nargs='?', help="Входное изображение")
    parser.add_argument("output", nargs='?', help="Выходное изображение")

    parser.add_argument("--batch", action="store_true", help="Пакетная обработка папки")
    parser.add_argument("--palette", type=int, default=32, help="Размер палитры (default: 32)")
    parser.add_argument("--saturation", type=float, default=0.55, help="Насыщенность 0-1 (default: 0.55)")
    parser.add_argument("--brightness", type=float, default=0.85, help="Яркость (default: 0.85)")
    parser.add_argument("--contrast", type=float, default=1.15, help="Контраст (default: 1.15)")
    parser.add_argument("--hue-shift", type=float, default=15, help="Сдвиг оттенка (default: 15)")
    parser.add_argument("--dither", dest='dither', action="store_true", default=True, help="Включить dithering")
    parser.add_argument("--no-dither", dest='dither', action="store_false", help="Отключить dithering")
    parser.add_argument("--dither-strength", type=float, default=0.5, help="Сила dithering 0-1 (default: 0.5)")
    parser.add_argument("--downscale", type=float, default=1.0, help="Коэффициент уменьшения для пиксельности")
    parser.add_argument("--extract-palette", action="store_true", help="Извлечь палитру вместо использования Deceiver")
    parser.add_argument("--json", action="store_true", help="JSON вывод")

    args = parser.parse_args()

    if not args.input:
        parser.print_help()
        return 1

    config = StyleConfig(
        palette_size=args.palette,
        saturation=args.saturation,
        brightness=args.brightness,
        contrast=args.contrast,
        hue_shift=args.hue_shift,
        dithering=args.dither,
        dither_strength=args.dither_strength,
        use_deceiver_palette=not args.extract_palette,
        downscale=args.downscale
    )

    if args.batch:
        results = batch_stylize(args.input, args.output, config)

        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            success = sum(1 for r in results if r.get("success"))
            print(f"\nГотово: {success}/{len(results)}")
            for r in results:
                if r.get("success"):
                    print(f"  [OK] {r['output']}")
                else:
                    print(f"  [FAIL] {r.get('error', 'Unknown error')}")
    else:
        if not args.output:
            # Генерируем имя выхода
            inp = Path(args.input)
            args.output = str(inp.parent / f"{inp.stem}_deceiver.png")

        result = deceiver_stylize(args.input, args.output, config)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if result.get("success"):
                print(f"Готово: {result['output']}")
                print(f"Палитра: {result['palette_size']} цветов")
            else:
                print(f"Ошибка: {result.get('error', 'Unknown')}")
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
