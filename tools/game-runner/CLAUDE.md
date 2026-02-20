# Tool: game-runner

Запуск и управление игровыми процессами. Поддерживает LÖVE 2D и Unreal Engine.

## CLI

```bash
ptero-tool run <project> [options]
```

### Опции

| Опция | Описание | По умолчанию |
|-------|----------|--------------|
| `project` | Путь к проекту (обязательно) | — |
| `--engine`, `-e` | Движок: love, unreal | Автоопределение |
| `--wait`, `-w` | Ждать N секунд после запуска | 0 |
| `--capture`, `-c` | Сделать скриншот после wait | — |
| `--kill`, `-k` | Завершить процесс после capture | — |
| `--timeout` | Таймаут запуска (секунды) | 30 |

## Примеры

```bash
# Запустить LÖVE проект
ptero-tool run backpack_hero --engine love

# Запустить, подождать, сделать скриншот
ptero-tool run backpack_hero --wait 3 --capture --output game.png

# Запустить, проверить, завершить (для тестов)
ptero-tool run backpack_hero --wait 2 --capture --kill

# Unreal PIE
ptero-tool run babylon --engine unreal
```

## Python API

```python
from studio.tools.game_runner import run_game, GameProcess

# Запустить игру
process = run_game(
    project="backpack_hero",
    engine="love",
    wait=2
)

# Проверить состояние
print(process.is_running())  # True
print(process.pid)           # 12345

# Сделать скриншот
screenshot = process.capture()

# Завершить
process.kill()
```

## Поддерживаемые движки

### LÖVE 2D
```python
# Автоопределение по наличию main.lua
# Запуск: love.exe <project_path>
```

### Unreal Engine
```python
# Автоопределение по .uproject
# Использует babylon/MCP для PIE
# Требует запущенный MCP сервер
```

## Возвращает

### CLI
```json
{
  "pid": 12345,
  "engine": "love",
  "project": "backpack_hero",
  "screenshot": "capture_20250221_153000.png"
}
```

### Python
```python
@dataclass
class GameProcess:
    pid: int
    engine: str
    project: str
    process: subprocess.Popen

    def is_running(self) -> bool
    def capture(self) -> str
    def kill(self) -> None
    def send_key(self, key: str) -> None
```

## Зависимости

- `psutil` — управление процессами
- `window-capture` — скриншоты
- `babylon/MCP` — для Unreal
