# Toolbox Catalog

Реестр инструментов Ptero Dactyl Studio.

## Доступные инструменты

| Tool | Команда | Описание | Статус |
|------|---------|----------|--------|
| [window-capture](window-capture/CLAUDE.md) | `ptero-tool capture` | Захват скриншота окна | В разработке |
| [vision-validator](vision-validator/CLAUDE.md) | `ptero-tool validate` | Проверка через Claude Vision | В разработке |
| [game-runner](game-runner/CLAUDE.md) | `ptero-tool run` | Запуск и управление играми | В разработке |
| [asset-gen](asset-gen/CLAUDE.md) | `ptero-tool asset` | Генерация ассетов | Планируется |
| blender-render | `ptero-tool blender` | Рендер в Blender | Планируется |

## Использование

### CLI
```bash
ptero-tool <command> [options]

# Примеры
ptero-tool capture --window "LÖVE" --output game.png
ptero-tool validate game.png --prompt "Game running?"
ptero-tool run backpack_hero --engine love --wait 2
ptero-tool asset character --prompt "Fire mage" --style pixel
```

### Python API
```python
from studio.tools import capture, validate, run_game, generate_asset

screenshot = capture(window="CardGame")
result = validate(screenshot, prompt="UI works?")
process = run_game("backpack_hero", engine="love")
asset = generate_asset("character", prompt="Fire mage")
```

## Создание нового инструмента

1. Создать папку `tools/my-tool/`
2. Добавить `CLAUDE.md` с документацией
3. Реализовать `cli.py` (argparse CLI)
4. Реализовать логику в `*.py`
5. Добавить запись в эту таблицу
6. Добавить в `tools/__init__.py`

## Принципы

- **Один инструмент — одна задача**
- **CLI + Python API** для каждого
- **Самодокументация** через CLAUDE.md
- **Изоляция** — tool не знает о контексте проекта
- **Идемпотентность** — повторный вызов безопасен
