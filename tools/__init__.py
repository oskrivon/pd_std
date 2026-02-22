"""
Ptero Dactyl Studio Toolbox

Набор переиспользуемых инструментов для AI-агентов.

Usage:
    from tools import capture, validate, run_game

    screenshot = capture(window="CardGame")
    result = validate(screenshot, prompt="Game running?")
    process = run_game("backpack_hero", engine="love")
"""


# Ленивый импорт для ускорения загрузки
def capture(window: str, output: str = None, resize: tuple = None, **kwargs):
    """Захват скриншота окна."""
    from .window_capture import capture_window
    return capture_window(window=window, output=output, resize=resize, **kwargs)


def validate(image: str, prompt: str, model: str = "haiku", **kwargs):
    """Проверка изображения через Vision AI."""
    from .vision_validator import validate as _validate
    return _validate(image=image, prompt=prompt, model=model, **kwargs)


def run_game(project: str, engine: str = None, wait: float = 0, **kwargs):
    """Запуск игрового проекта."""
    from .game_runner import run_game as _run_game
    return _run_game(project=project, engine=engine, wait=wait, **kwargs)


def generate_asset(*args, **kwargs):
    """Генерация ассетов (WIP)."""
    raise NotImplementedError("Asset generation not implemented yet")


__all__ = ['capture', 'validate', 'run_game', 'generate_asset']
