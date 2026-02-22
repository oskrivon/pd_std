"""
Window Capture Tool

Захват скриншота окна по заголовку через Windows API.
Поддерживает захват перекрытых окон через PrintWindow API.

Usage:
    from studio.tools.window_capture import capture_window, list_windows

    path = capture_window(window="CardGame", output="screenshot.png")
    windows = list_windows()
"""

import ctypes
from ctypes import wintypes
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
import logging
import sys

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

logger = logging.getLogger("window_capture")

# Windows API (only on Windows)
if sys.platform == "win32":
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    dwmapi = ctypes.windll.dwmapi
else:
    user32 = None
    gdi32 = None
    dwmapi = None

# Constants
DWMWA_EXTENDED_FRAME_BOUNDS = 9
PW_RENDERFULLCONTENT = 2  # Windows 8.1+, captures DirectX content
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0


def _check_windows():
    """Проверить что запущено на Windows."""
    if sys.platform != "win32":
        raise RuntimeError("window-capture работает только на Windows")
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow не установлен. Запустите: pip install Pillow")


def _find_window_by_title(title_substring: str) -> Optional[int]:
    """Найти окно по части заголовка."""
    result = []

    def enum_callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if title_substring.lower() in buffer.value.lower():
                    result.append((hwnd, buffer.value))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

    if result:
        return result[0][0]
    return None


def _get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """Получить координаты окна (left, top, right, bottom)."""
    rect = wintypes.RECT()

    # Попробуем DWM для точных границ (без теней)
    result = dwmapi.DwmGetWindowAttribute(
        hwnd,
        DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(rect),
        ctypes.sizeof(rect)
    )

    if result == 0:
        return (rect.left, rect.top, rect.right, rect.bottom)

    # Fallback на обычный GetWindowRect
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)

    return None


def _capture_printwindow(hwnd: int) -> Optional["Image.Image"]:
    """
    Захватить окно через PrintWindow API.
    Работает даже когда окно перекрыто другими окнами.
    """
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top

    if width <= 0 or height <= 0:
        logger.error(f"Invalid window size: {width}x{height}")
        return None

    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        logger.error("Failed to get window DC")
        return None

    try:
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        if not mem_dc:
            return None

        try:
            bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
            if not bitmap:
                return None

            try:
                old_bitmap = gdi32.SelectObject(mem_dc, bitmap)

                # Захват через PrintWindow
                result = user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)

                if not result:
                    # Fallback на BitBlt
                    gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, SRCCOPY)

                # Получить данные bitmap
                class BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [
                        ('biSize', wintypes.DWORD),
                        ('biWidth', wintypes.LONG),
                        ('biHeight', wintypes.LONG),
                        ('biPlanes', wintypes.WORD),
                        ('biBitCount', wintypes.WORD),
                        ('biCompression', wintypes.DWORD),
                        ('biSizeImage', wintypes.DWORD),
                        ('biXPelsPerMeter', wintypes.LONG),
                        ('biYPelsPerMeter', wintypes.LONG),
                        ('biClrUsed', wintypes.DWORD),
                        ('biClrImportant', wintypes.DWORD),
                    ]

                class BITMAPINFO(ctypes.Structure):
                    _fields_ = [
                        ('bmiHeader', BITMAPINFOHEADER),
                        ('bmiColors', wintypes.DWORD * 3),
                    ]

                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = width
                bmi.bmiHeader.biHeight = -height  # Negative для top-down
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = BI_RGB

                buffer_size = width * height * 4
                buffer = ctypes.create_string_buffer(buffer_size)

                gdi32.GetDIBits(
                    mem_dc, bitmap, 0, height,
                    buffer, ctypes.byref(bmi), DIB_RGB_COLORS
                )

                gdi32.SelectObject(mem_dc, old_bitmap)

                # Создать PIL Image (BGRA -> RGB)
                img = Image.frombuffer('RGBA', (width, height), buffer, 'raw', 'BGRA', 0, 1)
                return img.convert('RGB')

            finally:
                gdi32.DeleteObject(bitmap)
        finally:
            gdi32.DeleteDC(mem_dc)
    finally:
        user32.ReleaseDC(hwnd, hwnd_dc)


def capture_window(
    window: str,
    output: Optional[str] = None,
    resize: Optional[Tuple[int, int]] = None,
    format: str = "png"
) -> Optional[str]:
    """
    Захватить скриншот окна.

    Args:
        window: Часть заголовка окна для поиска
        output: Путь для сохранения (опционально, генерируется автоматически)
        resize: Размер для ресайза (width, height) или None
        format: Формат изображения (png, jpg)

    Returns:
        Путь к сохранённому файлу или None при ошибке
    """
    _check_windows()

    hwnd = _find_window_by_title(window)
    if not hwnd:
        logger.error(f"Window '{window}' not found")
        return None

    rect = _get_window_rect(hwnd)
    if not rect:
        logger.error("Failed to get window rect")
        return None

    # Захват
    img = _capture_printwindow(hwnd)

    # Fallback на mss
    if img is None and MSS_AVAILABLE:
        left, top, right, bottom = rect
        with mss.mss() as sct:
            monitor = {
                "left": left,
                "top": top,
                "width": right - left,
                "height": bottom - top
            }
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    if img is None:
        logger.error("Failed to capture window")
        return None

    # Ресайз
    if resize:
        img = img.resize(resize, Image.Resampling.LANCZOS)

    # Определить путь
    if output:
        output_path = Path(output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"capture_{timestamp}.{format}")

    # Убедиться что директория существует
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Сохранить
    img.save(str(output_path))
    img.close()

    return str(output_path)


def list_windows(filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Получить список видимых окон.

    Args:
        filter: Фильтр по заголовку (опционально)

    Returns:
        Список словарей с информацией об окнах
    """
    _check_windows()

    windows = []

    def enum_callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value

                # Фильтрация
                if filter and filter.lower() not in title.lower():
                    return True

                rect = _get_window_rect(hwnd)
                if rect:
                    windows.append({
                        "handle": int(hwnd),
                        "title": title,
                        "width": rect[2] - rect[0],
                        "height": rect[3] - rect[1]
                    })
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

    return windows


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Захват скриншота окна по заголовку",
        prog="ptero-tool capture"
    )

    parser.add_argument(
        "-w", "--window",
        help="Часть заголовка окна для поиска"
    )
    parser.add_argument(
        "-o", "--output",
        help="Путь для сохранения (по умолчанию capture_TIMESTAMP.png)"
    )
    parser.add_argument(
        "--resize",
        help="Ресайз изображения (WxH, например 800x600)"
    )
    parser.add_argument(
        "--format",
        choices=["png", "jpg"],
        default="png",
        help="Формат изображения"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Показать список доступных окон"
    )
    parser.add_argument(
        "--filter",
        help="Фильтр для списка окон"
    )

    args = parser.parse_args()

    # Режим списка
    if args.list:
        windows = list_windows(filter=args.filter)
        if not windows:
            print("Окна не найдены")
            return 1

        for w in windows:
            print(f"{w['title']} ({w['width']}x{w['height']})")
        return 0

    # Режим захвата
    if not args.window:
        parser.error("--window обязателен для захвата")

    resize = None
    if args.resize:
        try:
            w, h = args.resize.lower().split("x")
            resize = (int(w), int(h))
        except ValueError:
            parser.error("--resize должен быть в формате WxH (например 800x600)")

    result = capture_window(
        window=args.window,
        output=args.output,
        resize=resize,
        format=args.format
    )

    if result:
        print(result)
        return 0
    else:
        print("Ошибка захвата", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
