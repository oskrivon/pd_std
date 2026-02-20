"""
Ptero Dactyl Studio Toolbox

Набор переиспользуемых инструментов для AI-агентов.

Использование:
    from studio.tools import capture, validate, run_game

    screenshot = capture(window="CardGame")
    result = validate(screenshot, prompt="Game running?")
    process = run_game("backpack_hero", engine="love")
"""

# Ленивый импорт для ускорения загрузки
def capture(*args, **kwargs):
    from .window_capture import capture_window
    return capture_window(*args, **kwargs)

def validate(*args, **kwargs):
    from .vision_validator import validate
    return validate(*args, **kwargs)

def run_game(*args, **kwargs):
    from .game_runner import run_game
    return run_game(*args, **kwargs)

def generate_asset(*args, **kwargs):
    from .asset_gen import generate
    return generate(*args, **kwargs)

__all__ = ['capture', 'validate', 'run_game', 'generate_asset']
