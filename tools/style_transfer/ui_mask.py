"""
UI Mask System

Создание масок для раздельной обработки UI и игрового контента.

Подходы:
1. Ручные регионы — задаём прямоугольники UI областей
2. Автодетекция — по краям и контрастным элементам
3. Цветовая детекция — UI часто имеет характерные цвета

Использование:
    # Создать маску
    mask = create_ui_mask(image, regions=[...])

    # Применить стилизацию с маской
    result = apply_with_mask(original, stylized, mask)
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional, Union

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageOps
    import numpy as np
except ImportError:
    print("Требуется: pip install pillow numpy")
    sys.exit(1)


@dataclass
class UIRegion:
    """Определение региона UI."""
    x: int
    y: int
    width: int
    height: int
    name: str = ""
    feather: int = 5  # Размытие краёв для плавного перехода


@dataclass
class UILayout:
    """Пресет расположения UI для типа игры."""
    name: str
    regions: List[UIRegion] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "regions": [
                {"x": r.x, "y": r.y, "width": r.width, "height": r.height,
                 "name": r.name, "feather": r.feather}
                for r in self.regions
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UILayout":
        regions = [
            UIRegion(
                x=r["x"], y=r["y"],
                width=r["width"], height=r["height"],
                name=r.get("name", ""),
                feather=r.get("feather", 5)
            )
            for r in data.get("regions", [])
        ]
        return cls(name=data.get("name", "custom"), regions=regions)


# Пресеты для разных типов игр
UI_PRESETS = {
    # Полная защита UI (инвентарь целиком)
    "backpack_hero": UILayout(
        name="Backpack Hero - Full UI Protection",
        regions=[
            # Левая панель инвентаря целиком
            UIRegion(x=0, y=30, width=420, height=670, name="inventory", feather=8),
            # Верхняя статус-панель
            UIRegion(x=0, y=0, width=1280, height=35, name="top_bar", feather=3),
            # Правая панель статистики
            UIRegion(x=1080, y=50, width=200, height=150, name="stats", feather=5),
            # Легенда внизу справа
            UIRegion(x=1020, y=520, width=260, height=200, name="legend", feather=5),
        ]
    ),

    # Только текст и критичные UI элементы (инвентарь стилизуется!)
    "backpack_hero_text_only": UILayout(
        name="Backpack Hero - Text Only (Inventory Stylized)",
        regions=[
            # Верхняя статус-панель с текстом
            UIRegion(x=0, y=0, width=1280, height=35, name="top_bar", feather=3),
            # Треугольные клетки с текстом в инвентаре (примерные координаты)
            UIRegion(x=95, y=95, width=290, height=200, name="inventory_cells", feather=2),
            # Иконки внизу инвентаря НЕ защищаем - они стилизуются
            # Числа загрузки
            UIRegion(x=320, y=370, width=80, height=30, name="load_numbers", feather=2),
            # Правая панель статистики
            UIRegion(x=1080, y=50, width=200, height=150, name="stats", feather=5),
            # Легенда внизу справа
            UIRegion(x=1020, y=520, width=260, height=200, name="legend", feather=5),
        ]
    ),

    # Минимальная защита - только числа и критичный текст
    "backpack_hero_minimal": UILayout(
        name="Backpack Hero - Minimal (Max Stylization)",
        regions=[
            # Верхняя панель
            UIRegion(x=0, y=0, width=1280, height=35, name="top_bar", feather=3),
            # Правая статистика
            UIRegion(x=1080, y=50, width=200, height=150, name="stats", feather=5),
            # Легенда
            UIRegion(x=1020, y=580, width=260, height=140, name="legend", feather=3),
        ]
    ),

    # Общий пресет для игр с боковыми панелями
    "side_panels": UILayout(
        name="Side Panels",
        regions=[
            UIRegion(x=0, y=0, width=300, height=720, name="left_panel", feather=10),
            UIRegion(x=980, y=0, width=300, height=720, name="right_panel", feather=10),
            UIRegion(x=0, y=0, width=1280, height=40, name="top_bar", feather=5),
            UIRegion(x=0, y=680, width=1280, height=40, name="bottom_bar", feather=5),
        ]
    ),

    # Минимальный UI - только края
    "minimal": UILayout(
        name="Minimal UI",
        regions=[
            UIRegion(x=0, y=0, width=1280, height=40, name="top", feather=5),
            UIRegion(x=0, y=680, width=1280, height=40, name="bottom", feather=5),
        ]
    ),
}


def create_ui_mask(
    image: Union[Image.Image, str],
    regions: Optional[List[UIRegion]] = None,
    preset: Optional[str] = None,
    invert: bool = False,
    feather_global: int = 0
) -> Image.Image:
    """
    Создать маску UI областей.

    Белый = UI (не обрабатывать)
    Чёрный = Game content (обрабатывать)

    Args:
        image: Изображение или путь к нему (для получения размеров)
        regions: Список UIRegion для маскирования
        preset: Имя пресета из UI_PRESETS
        invert: Инвертировать маску (белый = обрабатывать)
        feather_global: Дополнительное размытие всей маски

    Returns:
        Grayscale маска
    """
    # Получаем размеры
    if isinstance(image, str):
        image = Image.open(image)

    width, height = image.size

    # Создаём чёрную маску (всё обрабатывается)
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)

    # Получаем регионы
    if preset and preset in UI_PRESETS:
        regions = UI_PRESETS[preset].regions
    elif regions is None:
        regions = []

    # Масштабируем регионы если размер отличается от 1280x720
    scale_x = width / 1280
    scale_y = height / 720

    # Рисуем белые прямоугольники для UI областей
    for region in regions:
        x1 = int(region.x * scale_x)
        y1 = int(region.y * scale_y)
        x2 = int((region.x + region.width) * scale_x)
        y2 = int((region.y + region.height) * scale_y)

        draw.rectangle([x1, y1, x2, y2], fill=255)

        # Размытие краёв для этого региона
        if region.feather > 0:
            # Создаём отдельную маску для размытия
            region_mask = Image.new("L", (width, height), 0)
            region_draw = ImageDraw.Draw(region_mask)
            region_draw.rectangle([x1, y1, x2, y2], fill=255)

            # Размываем
            feather = int(region.feather * min(scale_x, scale_y))
            if feather > 0:
                region_mask = region_mask.filter(ImageFilter.GaussianBlur(feather))

            # Объединяем с основной маской (берём максимум)
            mask = Image.composite(
                Image.new("L", (width, height), 255),
                mask,
                region_mask
            )

    # Глобальное размытие
    if feather_global > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(feather_global))

    # Инвертируем если нужно
    if invert:
        mask = ImageOps.invert(mask)

    return mask


def auto_detect_ui_mask(
    image: Union[Image.Image, str],
    edge_threshold: int = 30,
    min_region_size: int = 1000,
    border_width: int = 50
) -> Image.Image:
    """
    Автоматическая детекция UI по краям и контрасту.

    Ищет области с высоким контрастом и чёткими границами,
    характерными для UI элементов.

    Args:
        image: Изображение
        edge_threshold: Порог детекции краёв
        min_region_size: Минимальный размер UI региона
        border_width: Ширина границ экрана для автодетекции

    Returns:
        Grayscale маска
    """
    if isinstance(image, str):
        image = Image.open(image)

    if image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size

    # Детекция краёв
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)

    # Бинаризация краёв
    edges_np = np.array(edges)
    edges_binary = (edges_np > edge_threshold).astype(np.uint8) * 255

    # Расширяем области с краями (морфологическая дилатация)
    from PIL import ImageFilter
    edges_img = Image.fromarray(edges_binary)
    edges_dilated = edges_img.filter(ImageFilter.MaxFilter(5))

    # Создаём маску на основе краёв
    mask = np.array(edges_dilated)

    # Добавляем границы экрана как UI
    mask[:border_width, :] = 255  # Верх
    mask[-border_width:, :] = 255  # Низ
    mask[:, :border_width] = 255  # Лево
    mask[:, -border_width:] = 255  # Право

    # Размытие для плавных переходов
    result = Image.fromarray(mask)
    result = result.filter(ImageFilter.GaussianBlur(10))

    return result


def apply_with_mask(
    original: Union[Image.Image, str],
    stylized: Union[Image.Image, str],
    mask: Union[Image.Image, str],
    ui_style: str = "original"
) -> Image.Image:
    """
    Применить стилизацию с учётом маски.

    Args:
        original: Оригинальное изображение
        stylized: Стилизованное изображение
        mask: Маска (белый = UI/оригинал, чёрный = стилизованное)
        ui_style: Как обрабатывать UI:
            - "original": оставить без изменений
            - "light": лёгкая стилизация (50% blend)
            - "desaturate": только обесцветить

    Returns:
        Результат композиции
    """
    # Загружаем если пути
    if isinstance(original, str):
        original = Image.open(original)
    if isinstance(stylized, str):
        stylized = Image.open(stylized)
    if isinstance(mask, str):
        mask = Image.open(mask)

    # Приводим к одному размеру
    if original.size != stylized.size:
        stylized = stylized.resize(original.size, Image.Resampling.LANCZOS)
    if mask.size != original.size:
        mask = mask.resize(original.size, Image.Resampling.LANCZOS)

    # Конвертируем
    if original.mode != "RGB":
        original = original.convert("RGB")
    if stylized.mode != "RGB":
        stylized = stylized.convert("RGB")
    if mask.mode != "L":
        mask = mask.convert("L")

    # Подготовка UI слоя
    if ui_style == "original":
        ui_layer = original
    elif ui_style == "light":
        # 50% blend оригинала и стилизованного
        ui_layer = Image.blend(original, stylized, 0.5)
    elif ui_style == "desaturate":
        # Только обесцвечиваем
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Color(original)
        ui_layer = enhancer.enhance(0.5)
    else:
        ui_layer = original

    # Композиция: mask белый = ui_layer, mask чёрный = stylized
    result = Image.composite(ui_layer, stylized, mask)

    return result


def visualize_mask(
    image: Union[Image.Image, str],
    mask: Union[Image.Image, str],
    output_path: Optional[str] = None,
    overlay_color: Tuple[int, int, int] = (255, 0, 0),
    opacity: float = 0.4
) -> Image.Image:
    """
    Визуализировать маску поверх изображения.

    Args:
        image: Исходное изображение
        mask: Маска
        output_path: Путь для сохранения (опционально)
        overlay_color: Цвет наложения для UI областей
        opacity: Прозрачность наложения

    Returns:
        Изображение с визуализацией маски
    """
    if isinstance(image, str):
        image = Image.open(image)
    if isinstance(mask, str):
        mask = Image.open(mask)

    if image.mode != "RGB":
        image = image.convert("RGB")
    if mask.mode != "L":
        mask = mask.convert("L")

    # Создаём цветной оверлей
    overlay = Image.new("RGB", image.size, overlay_color)

    # Применяем маску к оверлею
    mask_normalized = mask.point(lambda x: int(x * opacity))

    # Композиция
    result = Image.composite(overlay, image, mask_normalized)

    if output_path:
        result.save(output_path)

    return result


def save_layout(layout: UILayout, path: str):
    """Сохранить layout в JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(layout.to_dict(), f, indent=2, ensure_ascii=False)


def load_layout(path: str) -> UILayout:
    """Загрузить layout из JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return UILayout.from_dict(data)


def main():
    """CLI для работы с масками."""
    import argparse

    parser = argparse.ArgumentParser(
        description="UI Mask System - создание и применение масок",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Команды")

    # Команда create - создать маску
    create_parser = subparsers.add_parser("create", help="Создать маску")
    create_parser.add_argument("image", help="Входное изображение")
    create_parser.add_argument("output", help="Выходная маска")
    create_parser.add_argument("--preset", "-p", choices=list(UI_PRESETS.keys()),
                              help="Пресет UI layout")
    create_parser.add_argument("--auto", "-a", action="store_true",
                              help="Автодетекция UI")
    create_parser.add_argument("--visualize", "-v", action="store_true",
                              help="Сохранить визуализацию")

    # Команда apply - применить маску
    apply_parser = subparsers.add_parser("apply", help="Применить стилизацию с маской")
    apply_parser.add_argument("original", help="Оригинальное изображение")
    apply_parser.add_argument("stylized", help="Стилизованное изображение")
    apply_parser.add_argument("mask", help="Маска")
    apply_parser.add_argument("output", help="Результат")
    apply_parser.add_argument("--ui-style", choices=["original", "light", "desaturate"],
                              default="original", help="Стиль UI")

    # Команда list - показать пресеты
    list_parser = subparsers.add_parser("list", help="Показать пресеты")

    args = parser.parse_args()

    if args.command == "create":
        print(f"Создание маски для: {args.image}")

        if args.auto:
            print("Режим: автодетекция")
            mask = auto_detect_ui_mask(args.image)
        elif args.preset:
            print(f"Режим: пресет '{args.preset}'")
            mask = create_ui_mask(args.image, preset=args.preset)
        else:
            print("Режим: пустая маска (укажите --preset или --auto)")
            img = Image.open(args.image)
            mask = Image.new("L", img.size, 0)

        mask.save(args.output)
        print(f"Маска сохранена: {args.output}")

        if args.visualize:
            vis_path = args.output.replace(".png", "_vis.png")
            visualize_mask(args.image, mask, vis_path)
            print(f"Визуализация: {vis_path}")

    elif args.command == "apply":
        print(f"Применение маски...")
        result = apply_with_mask(
            args.original,
            args.stylized,
            args.mask,
            args.ui_style
        )
        result.save(args.output)
        print(f"Результат: {args.output}")

    elif args.command == "list":
        print("Доступные пресеты UI:")
        for name, layout in UI_PRESETS.items():
            print(f"\n  {name}: {layout.name}")
            for r in layout.regions:
                print(f"    - {r.name}: {r.x},{r.y} {r.width}x{r.height}")

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
