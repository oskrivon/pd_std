# Toolbox Catalog

Реестр инструментов Ptero Dactyl Studio.

## Доступные инструменты

| Tool | Команда | Описание | Статус |
|------|---------|----------|--------|
| [window_capture](window_capture/CLAUDE.md) | `ptero-tool capture` | Захват скриншота окна | Готов |
| [vision_validator](vision_validator/CLAUDE.md) | `ptero-tool validate` | Проверка через Claude Vision | Готов |
| [game_runner](game_runner/CLAUDE.md) | `ptero-tool run` | Запуск и управление играми | Готов |
| [asset_gen](asset_gen/CLAUDE.md) | `ptero-tool asset` | Генерация ассетов | Планируется |
| blender_render | `ptero-tool blender` | Рендер в Blender | Планируется |

## Использование

### CLI
```bash
python -m tools.cli <command> [options]

# Примеры
python -m tools.cli capture --window "LOVE" --output game.png
python -m tools.cli validate game.png --prompt "Game running?"
python -m tools.cli run backpack_hero --engine love --wait 2
```

### Python API
```python
from tools import capture, validate, run_game

screenshot = capture(window="CardGame")
result = validate(screenshot, prompt="UI works?")
process = run_game("backpack_hero", engine="love")
```

## Создание нового инструмента

1. Создать папку `tools/my_tool/`
2. Добавить `CLAUDE.md` с документацией
3. Реализовать CLI в `*.py` (argparse)
4. Добавить `__init__.py` с exports
5. Добавить запись в эту таблицу
6. Добавить lazy import в `tools/__init__.py`

## Принципы

- **Один инструмент — одна задача**
- **CLI + Python API** для каждого
- **Самодокументация** через CLAUDE.md
- **Изоляция** — tool не знает о контексте проекта
- **Идемпотентность** — повторный вызов безопасен
