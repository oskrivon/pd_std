# Runbook

## Окружение

- **OS**: Windows 10/11
- **Путь**: `C:\Ptero Dactyl Games\studio`
- **Python**: 3.11+
- **LÖVE**: `C:\Program Files\LOVE\love.exe`
- **Unreal**: 5.7 (для babylon проекта)
- **Blender**: 4.0+ (опционально, для 3D ассетов)

## Зависимости

```bash
# Основные
pip install anthropic          # Claude API
pip install openai             # DALL-E API
pip install asyncio aiohttp    # Async HTTP
pip install pillow             # Обработка изображений
pip install pyautogui          # Window automation
pip install psutil             # Process management

# Для Blender интеграции (опционально)
# Blender использует встроенный Python, установка не требуется

# Для Unreal интеграции
pip install websockets         # MCP communication
pip install mcp[cli]           # MCP SDK
```

## Конфигурация

### API ключи

Создать `studio/config/.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Опционально
TELEGRAM_BOT_TOKEN=...
DISCORD_WEBHOOK_URL=...
```

### Пути

В `studio/config/settings.py`:
```python
LOVE_PATH = r"C:\Program Files\LOVE\love.exe"
BLENDER_PATH = r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe"
UNREAL_MCP_HOST = "localhost"
UNREAL_MCP_PORT = 9877
```

## Запуск

### Быстрый старт (одна задача)

```bash
cd "C:\Ptero Dactyl Games"
python -m studio.cli run backpack_hero
```

### Daemon mode (непрерывно)

```bash
python -m studio.cli daemon                    # базовый запуск
python -m studio.cli daemon --workers 2        # 2 параллельных воркера
python -m studio.cli daemon --no-analyze       # без Opus анализа
python -m studio.cli daemon --no-reset         # не сбрасывать IN_PROGRESS задачи
```

**Таймауты:**
- Idle timeout: 90 сек (убивает если нет вывода)
- Max timeout: 10 мин (абсолютный лимит)

### Создание нового проекта

```bash
python -m studio.cli init "tower_defense" --engine love --style "pixel art"
```

### Проверка статуса

```bash
python -m studio.cli status
```

### Web Dashboard

```bash
python -m studio.cli web
# Открыть http://127.0.0.1:8000
```

### Генерация тест-плана

```bash
# CLI
python -m studio.cli test-plan backpack_hero --commits 5
python -m studio.cli test-plan backpack_hero --save  # сохранить в docs/TEST_PLAN.md

# Или через dashboard: http://127.0.0.1:8000/test-plan/backpack_hero
```

### Импорт задач из markdown

```bash
# Создать шаблон задачи
python -m studio.cli inbox --new "Моя задача" --project backpack_hero

# Импортировать все задачи из tasks_inbox/
python -m studio.cli inbox
```

## Сервисы

| Сервис | Команда | Порт |
|--------|---------|------|
| Unreal MCP | `py babylon/Scripts/UnrealPython/startup.py` | 9877 |
| Studio Daemon | `python -m studio.cli daemon` | — |

## Логи

| Файл | Содержимое |
|------|------------|
| `studio/logs/daemon.log` | Основной лог демона |
| `studio/logs/tasks/` | Логи отдельных задач |
| `studio/logs/validation/` | Скриншоты и результаты валидации |

Просмотр логов:
```bash
tail -f studio/logs/daemon.log
```

## Мониторинг

### Проверить что демон работает
```bash
python -m studio.cli status
# Показывает: текущую задачу, очередь, бюджет
```

### Проверить использование токенов
```bash
python -m studio.cli budget
# Показывает: использовано / лимит, по моделям
```

## Частые проблемы

| Симптом | Причина | Решение |
|---------|---------|---------|
| `LOVE not found` | Неверный путь к LÖVE | Проверить `LOVE_PATH` в settings.py |
| `MCP connection refused` | Unreal не запущен или MCP не активен | Запустить startup.py в Unreal |
| `Vision timeout` | Слишком большой скриншот | Уменьшить разрешение в capture() |
| `Rate limit exceeded` | Слишком много запросов | Добавить задержку или снизить параллелизм |
| `Daemon stopped unexpectedly` | Exception в задаче | Проверить logs/daemon.log |
| `Window not found` | Игра не запустилась | Проверить логи запуска игры |
| `Task idle timeout` | Задача зависла без вывода | Проверить что Claude CLI работает, увеличить idle timeout |
| `IN_PROGRESS tasks reset` | Daemon перезапустился | Использовать `--no-reset` или запускать из dashboard |
| `Test plan timeout` | Claude CLI долго генерирует | Подождать до 5 мин, проверить сеть |

## Восстановление

### Daemon упал
```bash
# Проверить последнюю ошибку
tail -100 studio/logs/daemon.log

# Перезапустить
python -m studio.cli daemon
```

### Откат изменений
```bash
cd project_folder
git checkout HEAD~1 .
```

### Очистить очередь
```bash
python -m studio.cli queue clear
```

## Unreal-специфичное

### Запуск MCP сервера
```bash
# В Unreal Editor Output Log:
py "C:/Ptero Dactyl Games/babylon/Scripts/UnrealPython/startup.py"
```

### Проверка подключения
```bash
python -c "from studio.adapters.unreal import UnrealAdapter; import asyncio; asyncio.run(UnrealAdapter().get_project_info())"
```

### Rebuild C++
```bash
python -c "from studio.adapters.unreal import UnrealAdapter; import asyncio; asyncio.run(UnrealAdapter().rebuild())"
```

## Blender-специфичное

### Проверить установку
```bash
"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe" --version
```

### Тестовый рендер
```bash
python -c "from studio.adapters.dcc.blender import BlenderAdapter; import asyncio; asyncio.run(BlenderAdapter().test())"
```
