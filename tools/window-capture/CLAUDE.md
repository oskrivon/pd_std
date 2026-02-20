# Tool: window-capture

Захват скриншота окна по заголовку. Работает на Windows.

## CLI

```bash
ptero-tool capture --window "TITLE" [options]
```

### Опции

| Опция | Описание | По умолчанию |
|-------|----------|--------------|
| `--window`, `-w` | Часть заголовка окна (обязательно) | — |
| `--output`, `-o` | Путь для сохранения | `capture_TIMESTAMP.png` |
| `--resize` | Ресайз (WxH), экономит токены | Без ресайза |
| `--format` | Формат: png, jpg | png |
| `--list` | Показать доступные окна | — |

## Примеры

```bash
# Захватить окно LÖVE игры
ptero-tool capture --window "LÖVE" --output game.png

# С ресайзом для экономии токенов Vision API
ptero-tool capture --window "CardGame" --resize 800x600 --output small.png

# Показать все окна
ptero-tool capture --list

# Захватить Unreal Editor
ptero-tool capture --window "Unreal Editor" --output editor.png
```

## Python API

```python
from studio.tools.window_capture import capture_window, list_windows

# Захватить окно
path = capture_window(
    window="CardGame",
    output="screenshot.png",
    resize=(800, 600)
)

# Список окон
windows = list_windows()
for w in windows:
    print(f"{w['title']} ({w['handle']})")
```

## Возвращает

### CLI
- **stdout**: Путь к сохранённому файлу
- **exit 0**: Успех
- **exit 1**: Окно не найдено или ошибка

### Python
- `str`: Путь к файлу при успехе
- `None`: При ошибке

## Зависимости

- `pywin32` — работа с Windows API
- `Pillow` — обработка изображений

## Источник

Портирован из `babylon/MCP/window_capture.py`.
