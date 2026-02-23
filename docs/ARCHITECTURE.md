# Архитектура

## Обзор

Ptero Dactyl Studio — AI-driven система разработки игровых прототипов. Человек генерирует идеи, система автономно декомпозирует их в задачи, выполняет код, генерирует ассеты, тестирует результат и итерирует до готового прототипа.

Ключевая идея: **непрерывный автономный цикл** с минимальным участием человека и **жадной** оптимизацией использования токенов.

## Стек

- **Orchestration**: Python 3.11+, asyncio
- **AI**: Claude API (Opus/Sonnet/Haiku), DALL-E API
- **Game Engines**: LÖVE 2D (Lua), Unreal Engine 5.7 (C++)
- **DCC Tools**: Blender (Python API), Houdini (опционально)
- **Validation**: Vision API, window automation

## Высокоуровневая архитектура

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PTERO DACTYL STUDIO                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐                                                        │
│  │   ЧЕЛОВЕК   │  "Tower defense с магами, изометрия, LÖVE 2D"         │
│  └──────┬──────┘                                                        │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ ORCHESTRATOR (Claude Opus)                                       │   │
│  │                                                                  │   │
│  │ • Декомпозиция идеи → эпики → задачи                            │   │
│  │ • Планирование зависимостей                                      │   │
│  │ • Выбор инструмента для каждой задачи                           │   │
│  │ • Мониторинг прогресса                                          │   │
│  └─────────────────────────┬───────────────────────────────────────┘   │
│                            │                                            │
│         ┌──────────────────┼──────────────────┐                        │
│         ▼                  ▼                  ▼                        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │ GAME ENGINE │    │ DCC TOOLS   │    │ ASSET GEN   │                 │
│  │ WORKERS     │    │ WORKERS     │    │ WORKERS     │                 │
│  ├─────────────┤    ├─────────────┤    ├─────────────┤                 │
│  │ • LÖVE 2D   │    │ • Blender   │    │ • DALL-E    │                 │
│  │ • Unreal    │    │ • Houdini   │    │ • Procedural│                 │
│  └─────────────┘    └─────────────┘    └─────────────┘                 │
│         │                  │                  │                        │
│         └──────────────────┼──────────────────┘                        │
│                            ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ VALIDATOR (Vision + Gameplay)                                    │   │
│  │                                                                  │   │
│  │ • Запуск игры → скриншот → "работает?"                          │   │
│  │ • Автоматический gameplay test                                   │   │
│  │ • Сравнение с референсом                                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Структура кодовой базы

```
studio/
├── cli.py                 # Точка входа CLI
│
├── core/
│   ├── orchestrator.py    # Главный координатор
│   │   └── Orchestrator   # Класс: decompose(), schedule(), dispatch()
│   ├── task_db.py         # SQLite-based task queue (thread-safe)
│   │   └── TaskDB         # Класс: add(), pop(), complete(), fail(), stats()
│   ├── project.py         # Модель проекта
│   │   └── Project        # Класс: структура, состояние, файлы
│   ├── daemon.py          # Continuous execution
│   │   └── Daemon         # Класс: run_forever(), graceful_shutdown()
│   └── budget.py          # Token economy
│       └── BudgetManager  # Класс: track(), select_model(), estimate()
│
├── adapters/
│   ├── base.py            # Базовый интерфейс
│   │   └── EngineAdapter  # ABC: run(), capture(), inject(), get_state()
│   ├── love.py            # LÖVE 2D адаптер
│   │   └── LoveAdapter    # subprocess + window capture
│   ├── unreal.py          # Unreal Engine адаптер
│   │   └── UnrealAdapter  # Обёртка над babylon/MCP
│   └── dcc/
│       ├── blender.py     # Blender headless
│       │   └── BlenderAdapter  # render_sprite(), create_model()
│       └── houdini.py     # Houdini процедурка
│           └── HoudiniAdapter  # generate_tileset(), generate_vfx()
│
├── assets/
│   ├── generator.py       # Фасад генерации
│   │   └── AssetGenerator # Выбирает метод по типу ассета
│   ├── dalle.py           # DALL-E клиент
│   │   └── DALLEClient    # generate(), with_style()
│   └── procedural.py      # Код-генерация
│       └── ProceduralGen  # make_tileset(), make_gradient()
│
├── validation/
│   ├── validator.py       # Главный валидатор
│   │   └── GameValidator  # smoke_test(), gameplay_test()
│   └── scenarios.py       # DSL для сценариев
│       └── Scenario       # Парсинг и выполнение
│
└── config/
    ├── settings.py        # Конфигурация
    └── prompts/           # Системные промпты для агентов
```

## Ключевые классы

| Класс | Ответственность |
|-------|-----------------|
| `Orchestrator` | Декомпозиция идей, планирование, координация воркеров |
| `TaskDB` | SQLite task queue: atomic pop, transactions, crash recovery |
| `Daemon` | Непрерывное выполнение, graceful shutdown |
| `BudgetManager` | Трекинг токенов, выбор модели (Opus/Sonnet/Haiku) |
| `EngineAdapter` | Unified API для движков: run, capture, inject |
| `LoveAdapter` | LÖVE 2D специфика: subprocess, hot reload |
| `UnrealAdapter` | Делегирует в babylon/MCP |
| `BlenderAdapter` | Headless Blender для рендера |
| `AssetGenerator` | Роутинг: DALL-E vs Procedural vs Blender |
| `GameValidator` | Vision-based проверка + gameplay automation |

## Ключевые паттерны

### 1. Adapter Pattern
Все движки реализуют единый интерфейс `EngineAdapter`:
```python
class EngineAdapter(ABC):
    async def create_project(self, name: str, template: str) -> Path
    async def run(self, project_path: Path) -> Process
    async def capture(self) -> Path  # скриншот
    async def inject(self, code: str) -> bool  # hot reload
    async def get_state(self) -> dict  # текущее состояние игры
```

### 2. Strategy Pattern для генерации ассетов
```python
# AssetGenerator выбирает стратегию по типу
if asset_type == "character":
    return await self.dalle.generate(...)
elif asset_type == "tileset":
    return await self.procedural.make_tileset(...)
elif asset_type == "3d_sprite":
    return await self.blender.render_sprite(...)
```

### 3. Token Economy (жадный алгоритм)
```python
def pick_best_task(tasks):
    return max(tasks, key=lambda t:
        t.priority * t.value / t.estimated_tokens * t.context_overlap
    )
```

### 4. Model Tiering
| Модель | Стоимость | Применение |
|--------|-----------|------------|
| Haiku | $0.25/1M | Форматирование, boilerplate, мелкие правки |
| Sonnet | $3/1M | Код, фичи, дебаг, тесты |
| Opus | $15/1M | Архитектура, планирование, сложные решения |

## Зависимости между модулями

```
                    ┌─────────────┐
                    │ Orchestrator│
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ TaskDB      │ │ BudgetMgr   │ │ Validator   │
    │ (SQLite)    │ │             │ │             │
    └─────────────┘ └─────────────┘ └──────┬──────┘
                                           │
                                           ▼
    ┌─────────────────────────────────────────────┐
    │              EngineAdapter                  │
    ├─────────────┬─────────────┬─────────────────┤
    │ LoveAdapter │UnrealAdapter│ BlenderAdapter  │
    └─────────────┴─────────────┴─────────────────┘
           │              │
           │              ▼
           │       ┌─────────────┐
           │       │ babylon/MCP │ (внешний)
           │       └─────────────┘
           ▼
    ┌─────────────┐
    │AssetGenerator│
    ├─────────────┤
    │ DALL-E      │
    │ Procedural  │
    └─────────────┘
```

**Критичные зависимости:**
- `UnrealAdapter` → `babylon/MCP` (не дублировать код!)
- `Validator` → `EngineAdapter.capture()` (для скриншотов)
- `Orchestrator` → `BudgetManager` (выбор модели)

## Task Decomposition

Orchestrator (Opus) решает, нужна ли декомпозиция задачи.

### Decision Tree

```
New task from PLAN.md
        │
        ▼
┌───────────────────┐
│ Simple task?      │──── YES ───► Worker executes directly
│ (1-2 files, <100  │              No decomposition needed
│  lines change)    │
└───────────────────┘
        │ NO
        ▼
┌───────────────────┐
│ Has subtasks      │──── YES ───► Worker executes first subtask
│ already?          │
└───────────────────┘
        │ NO
        ▼
┌───────────────────┐
│ DECOMPOSE (Opus)  │──────────────► Updates PLAN.md with subtasks
│                   │              ► Worker executes first subtask
└───────────────────┘
```

### Decomposition Prompt (English)

```
TASK DECOMPOSITION

You are analyzing a task to determine if it needs decomposition.

TASK: {task_description}
PROJECT: {project_id}
CONTEXT: {project_claude_md_summary}

RULES:
1. If task touches 1-2 files and <100 lines → NO decomposition
2. If task is ambiguous or too large → DECOMPOSE into 3-7 subtasks
3. Each subtask must be:
   - Atomic (one clear outcome)
   - Testable (can verify completion)
   - Independent (minimal dependencies)
4. If task is too vague ("make it better") → REJECT with clarification request

OUTPUT FORMAT:
{
  "needs_decomposition": true/false,
  "reason": "...",
  "subtasks": [
    {"title": "...", "description": "...", "estimated_files": ["..."]},
    ...
  ]
}
```

### Examples

| Task | Decision | Reason |
|------|----------|--------|
| "Fix typo in menu" | NO decomposition | 1 file, trivial |
| "Add mana display" | NO decomposition | 1-2 files, clear scope |
| "Add drag-and-drop for cards" | DECOMPOSE | Multiple systems: input, visual, validation |
| "Add multiplayer" | DECOMPOSE | Large feature, 10+ subtasks |
| "Make game better" | REJECT | Too vague, need clarification |

### Subtask Structure in PLAN.md

```markdown
## TODO

- [ ] Add drag-and-drop for cards
  - [ ] Handle mouse down on card widget
  - [ ] Create ghost card visual during drag
  - [ ] Detect valid drop zones
  - [ ] Validate drop action (mana check, target check)
  - [ ] Animate card to final position
```

Worker выполняет подзадачи последовательно. Родительская задача отмечается `[x]` когда все подзадачи завершены.

## Continuous Loop (Daemon Mode)

```python
async def run_continuous(self):
    """
    Основной цикл студии.
    Работает пока есть задачи и бюджет.
    """
    while True:
        # 1. Проверить бюджет
        if not self.budget.has_remaining():
            await self.notify("Budget exhausted")
            break

        # 2. Выбрать лучшую задачу
        task = self.queue.pop_best()
        if not task:
            await self.notify("All tasks completed")
            break

        # 3. Выполнить
        try:
            result = await self.execute(task)
        except Exception as e:
            self.queue.add_fix_task(task, e)
            continue

        # 4. Валидировать
        validation = await self.validator.smoke_test(result)
        if not validation.passed:
            self.queue.add_fix_task(task, validation.issues)
            continue

        # 5. Коммит и отчёт
        await self.commit(result)
        self.state.mark_done(task)

        # 6. Уведомить если milestone
        if task.is_milestone:
            await self.notify(f"Milestone: {task.name}")
```

## Интеграция с существующими проектами

### babylon/MCP
Переиспользуется полностью через `UnrealAdapter`:
- 28 MCP tools
- Vision pipeline
- Pixel Streaming
- Rebuild pipeline

### backpack_hero
Тестовый полигон для `LoveAdapter`:
- Запуск через LÖVE CLI
- Window capture для скриншотов
- Hot reload через файловую систему

## Расширяемость

Добавление нового движка:
1. Создать `adapters/newengine.py`
2. Реализовать `EngineAdapter` интерфейс
3. Зарегистрировать в `adapters/__init__.py`
4. Добавить в `Orchestrator.get_adapter()`

Добавление нового типа ассетов:
1. Добавить стратегию в `assets/generator.py`
2. Если нужен новый источник — создать клиент в `assets/`

## Git Strategy (Multi-repo)

Каждый проект — отдельный репозиторий. Это обеспечивает изоляцию и независимость.

```
C:/Ptero Dactyl Games/           ← НЕ git (workspace)
├── .gitignore                   ← Игнорирует всё (safety net)
│
├── studio/                      ← git repo (инфраструктура)
│   └── .git/
│
├── babylon/                     ← git repo (проект)
│   └── .git/
│
├── backpack_hero/               ← git repo (проект)
│   └── .git/
│
└── projects/                    ← Новые проекты
    └── new_game/                ← git repo (проект)
        └── .git/
```

### Преимущества для изоляции

| Аспект | Польза |
|--------|--------|
| **Worker safety** | `git diff` показывает только изменения в своём репо |
| **Boundary check** | Коммит не может затронуть чужой проект |
| **Independent history** | Проекты развиваются независимо |
| **Selective clone** | Клонируешь только нужный проект |

### Worker Git Protocol

```
WORKER GIT RULES

After completing a task:
1. Stage only files within project boundary
2. Commit with descriptive message
3. DO NOT push (Orchestrator decides when to push)
4. Update STATUS.json with last_commit timestamp

Commit message format:
  <type>: <description>

  - type: feat, fix, refactor, docs, style, test
  - description: what changed and why

  Co-Authored-By: Claude <noreply@anthropic.com>
```

### Orchestrator Git Protocol

```python
class GitManager:
    def validate_changes(self, project_path: str) -> bool:
        """Verify all changes are within project boundary."""
        # Get list of changed files
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD'],
            cwd=project_path,
            capture_output=True
        )
        # All paths should be relative to project_path
        # No ../ or absolute paths outside boundary
        return self._check_paths(result.stdout)

    def commit_if_valid(self, project_path: str, message: str):
        """Commit only if validation passes."""
        if self.validate_changes(project_path):
            subprocess.run(['git', 'add', '-A'], cwd=project_path)
            subprocess.run(['git', 'commit', '-m', message], cwd=project_path)
```

## Inter-project Communication

### Иерархия контекстов

```
┌─────────────────────────────────────────────────────────────────────┐
│                         STUDIO LEVEL                                │
│                                                                     │
│  studio/                                                            │
│  ├── CLAUDE.md         ← Orchestrator читает ЭТО                   │
│  ├── docs/PLAN.md      ← Глобальные цели студии                    │
│  └── docs/PROGRESS.md  ← Общий прогресс                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ Orchestrator знает О проектах,
                                │ но не ВНУТРИ них
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│ babylon/      │       │ backpack_hero/│       │ projects/new/ │
│               │       │               │       │               │
│ CLAUDE.md ◄───┼───────┼── Worker      │       │ CLAUDE.md     │
│ docs/         │       │    читает     │       │ docs/         │
│   STATUS.json │       │    ТОЛЬКО     │       │   STATUS.json │
│   PLAN.md     │       │    свой       │       │   PLAN.md     │
│               │       │    контекст   │       │               │
└───────────────┘       └───────────────┘       └───────────────┘
```

### STATUS.json — машиночитаемый статус проекта

Каждый проект содержит `STATUS.json` в корне (автоматически обновляется orchestrator):

```json
{
  "project": "babylon",
  "state": "working",
  "current_task": "Implement card drag-drop",
  "last_task": "Add mana display",
  "last_task_status": "completed",
  "last_updated": "2025-02-21T15:30:00Z",
  "blocked_by": null,
  "error_message": null,
  "tasks_completed": 45,
  "tasks_failed": 2
}
```

**Состояния проекта:**
- `idle` — нет активной работы
- `working` — задача выполняется
- `blocked` — ожидание внешнего ресурса
- `error` — последняя задача failed
- `ready` — готов к следующей задаче

**CLI команда:**
```bash
ptero-studio status --projects
```

### Принцип изоляции

| Уровень | Видит | Не видит |
|---------|-------|----------|
| **Orchestrator** | studio/*, projects/*/STATUS.json | Внутренности проектов |
| **Worker** | project/CLAUDE.md, project/docs/*, project/src/* | studio/*, другие проекты |
| **Tool** | Только переданные аргументы | Контексты проектов |

### Поток информации

```
Worker завершил задачу
         │
         ▼
┌─────────────────────────┐
│ Обновить STATUS.json    │  ← Worker пишет
│ Обновить PROGRESS.md    │
│ Обновить PLAN.md        │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Orchestrator сканирует  │  ← Orchestrator читает
│ все STATUS.json         │
│ Выбирает следующую      │
│ задачу с лучшим ROI     │
└─────────────────────────┘
```

## Toolbox — переиспользуемые инструменты

Общий код выносится в **отдельные инструменты** с CLI и библиотечным API.
Агенты вызывают их как внешние команды — это обеспечивает изоляцию и переиспользование.

### Структура Toolbox

```
studio/
└── tools/
    ├── CATALOG.md              ← реестр всех инструментов
    │
    ├── window-capture/         ← захват окон
    │   ├── CLAUDE.md           ← документация для агентов
    │   ├── __init__.py
    │   ├── cli.py              ← ptero-tool capture ...
    │   └── capture.py          ← библиотека
    │
    ├── vision-validator/       ← проверка через Claude Vision
    │   ├── CLAUDE.md
    │   ├── cli.py              ← ptero-tool validate ...
    │   └── validator.py
    │
    ├── asset-gen/              ← генерация ассетов
    │   ├── CLAUDE.md
    │   ├── cli.py              ← ptero-tool asset ...
    │   └── generators/
    │       ├── dalle.py
    │       ├── procedural.py
    │       └── placeholder.py
    │
    ├── game-runner/            ← запуск и управление играми
    │   ├── CLAUDE.md
    │   ├── cli.py              ← ptero-tool run ...
    │   └── runners/
    │       ├── base.py
    │       ├── love.py
    │       └── unreal.py
    │
    └── blender-render/         ← рендер в Blender
        ├── CLAUDE.md
        ├── cli.py              ← ptero-tool blender ...
        └── render.py
```

### Интерфейс инструментов

Каждый инструмент доступен двумя способами:

**1. CLI (для агентов и скриптов):**
```bash
# Захват окна
ptero-tool capture --window "CardGame" --output shot.png

# Валидация скриншота
ptero-tool validate shot.png --prompt "UI отображается корректно?"

# Запуск игры
ptero-tool run backpack_hero --wait 2 --capture

# Генерация ассета
ptero-tool asset character --prompt "Fire mage" --style "pixel art"

# Рендер в Blender
ptero-tool blender render model.blend --angles 0,45,90 --output sprites/
```

**2. Python API (для кода студии):**
```python
from studio.tools.window_capture import capture_window
from studio.tools.vision_validator import validate_screenshot
from studio.tools.game_runner import run_game

# В коде
screenshot = capture_window("CardGame")
result = validate_screenshot(screenshot, "Game is running?")
process = run_game("backpack_hero", engine="love")
```

### CLAUDE.md инструмента (пример)

```markdown
# Tool: window-capture

Захват скриншота окна по заголовку.

## CLI

\`\`\`bash
ptero-tool capture --window "TITLE" [--output PATH] [--resize WxH]
\`\`\`

## Примеры

\`\`\`bash
# Захватить окно LÖVE игры
ptero-tool capture --window "LÖVE" --output game.png

# С ресайзом для экономии токенов
ptero-tool capture --window "CardGame" --resize 800x600 --output small.png
\`\`\`

## Возвращает

- Путь к сохранённому скриншоту
- Exit code 0 при успехе, 1 при ошибке
```

### Преимущества Toolbox подхода

| Аспект | Преимущество |
|--------|--------------|
| **Изоляция** | Tool не знает о контексте проекта |
| **Тестируемость** | Каждый tool тестируется отдельно |
| **Переиспользование** | Один tool для всех проектов |
| **Версионирование** | Tools можно версионировать независимо |
| **Документация** | Каждый tool самодокументирован |
| **CLI** | Агенты вызывают через командную строку |

### Добавление нового инструмента

1. Создать `tools/new-tool/`
2. Написать `CLAUDE.md` с документацией
3. Реализовать `cli.py` с argparse
4. Реализовать библиотеку в `*.py`
5. Добавить в `tools/CATALOG.md`
6. Зарегистрировать в `ptero-tool` CLI

## Tool Lifecycle (приёмка инструментов)

Инструменты проходят через стадии зрелости:

```
┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐
│   DEV   │ ───► │  BETA   │ ───► │ STABLE  │ ───► │ FROZEN  │
└─────────┘      └─────────┘      └─────────┘      └─────────┘
     │                │                │                │
     ▼                ▼                ▼                ▼
 • В проекте      • В studio/     • Тесты ✓        • Не меняется
 • Нет тестов       tools/        • 3+ проекта     • Только
 • Может           • Unit tests     используют       security
   сломаться       • 1 проект     • Документация     fixes
                     использует     полная
```

### Критерии перехода

| Переход | Требования |
|---------|------------|
| DEV → BETA | Работает в 1 проекте, есть CLAUDE.md, базовые тесты |
| BETA → STABLE | Unit + integration тесты, работает в 3+ проектах |
| STABLE → FROZEN | Критичный инструмент, изменения только через RFC |

### STATUS.md инструмента

Каждый tool имеет файл статуса:

```markdown
# Tool Status: window-capture

**Status**: BETA
**Version**: 0.2.0

## Checklist
- [x] CLAUDE.md написан
- [x] Unit tests passing
- [ ] Integration tests
- [x] Используется в: babylon
- [ ] Используется в 3+ проектах
```

### Гибридная модель разработки

1. **DEV** — инструмент живёт в проекте-источнике (`babylon/MCP/new_tool.py`)
2. **BETA+** — переезжает в `studio/tools/`, проект импортирует оттуда
3. **Extraction** — отдельная задача в `studio/docs/PLAN.md`

## Context Isolation (изоляция агентов)

Критически важно: Worker не должен модифицировать чужие проекты.

### Многоуровневая защита

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ISOLATION LAYERS                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 1: PROCESS ISOLATION (надёжно)                              │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ Каждый worker = отдельный процесс `claude`                    │ │
│  │ с --cwd ограниченным папкой проекта                           │ │
│  │                                                                │ │
│  │ claude --cwd "/path/to/project" -p "task..."                  │ │
│  │                                                                │ │
│  │ Worker начинает в изолированном контексте                     │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Layer 2: PROMPT BOUNDARY (средне надёжно)                         │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ Системный промпт с жёсткими ограничениями (EN)                │ │
│  │ См. секцию "Worker System Prompt"                             │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Layer 3: POST-VALIDATION (надёжно, после факта)                  │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ После выполнения Orchestrator проверяет:                      │ │
│  │ • git diff — какие файлы изменены?                            │ │
│  │ • Все в пределах project_path?                                │ │
│  │ • Если нет → ROLLBACK + alert                                 │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Layer 4: FILESYSTEM SANDBOX (опционально, максимум)              │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ Worker работает в tmp-копии проекта                           │ │
│  │ После проверки — merge обратно                                │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Worker System Prompt (English)

```
ISOLATION RULES — STRICT COMPLIANCE REQUIRED

You are a worker agent operating within a SINGLE project.

BOUNDARIES:
- Project root: {project_path}
- You may ONLY read and modify files within this directory
- You may read (but NOT write) files in: studio/tools/*

FORBIDDEN ACTIONS:
- DO NOT read files outside {project_path} (except studio/tools/*)
- DO NOT write/edit/delete files outside {project_path}
- DO NOT use cd to navigate outside {project_path}
- DO NOT spawn sub-agents that access other projects
- DO NOT modify .git directory directly

IF TASK REQUIRES EXTERNAL ACCESS:
- Return error: "ISOLATION_VIOLATION: Task requires access to {path}"
- Do NOT attempt to complete the task
- Orchestrator will handle cross-project coordination

TOOLS USAGE:
- Use ptero-tool CLI for shared functionality
- Tools are isolated and safe to call

VERIFICATION:
- Your changes WILL be audited after execution
- Violations trigger automatic rollback
- Repeated violations flag the task for human review
```

### Worker Launcher Implementation

```python
# core/worker_launcher.py

class WorkerLauncher:
    def run_isolated(self, project_path: str, task: str) -> WorkerResult:
        """Launch worker in isolated context."""

        # Build isolation prompt
        system_prompt = self._build_system_prompt(project_path)

        # Layer 1: Process isolation
        result = subprocess.run(
            [
                'claude',
                '-p', f"{system_prompt}\n\nTASK:\n{task}",
            ],
            cwd=project_path,
            capture_output=True
        )

        # Layer 3: Post-validation
        changes = self._get_git_changes(project_path)
        violations = self._check_boundary_violations(changes, project_path)

        if violations:
            self._rollback(project_path)
            self._alert_violation(project_path, violations)
            raise IsolationViolation(violations)

        return WorkerResult(output=result.stdout, changes=changes)

    def _check_boundary_violations(self,
                                   changes: list[Path],
                                   allowed: Path) -> list[str]:
        """Check all changes are within allowed boundary."""
        violations = []
        for path in changes:
            resolved = path.resolve()
            if not str(resolved).startswith(str(allowed.resolve())):
                violations.append(f"OUT_OF_BOUNDS: {path}")
        return violations
```

### .isolation Marker File

Each project contains a marker file for explicit boundaries:

```yaml
# babylon/.isolation

project_id: babylon
boundary: C:/Ptero Dactyl Games/babylon

allowed_external_reads:
  - studio/tools/**
  - studio/templates/**

allowed_external_writes: []

restricted_paths:
  - .git/
  - .env
  - secrets/
```

### Orchestrator-Worker Communication

```
┌─────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR (studio level)                                         │
│                                                                     │
│ 1. Select task from queue                                          │
│ 2. Identify target project                                         │
│ 3. Read project/.isolation for boundaries                          │
│ 4. Launch worker with isolation prompt                             │
│ 5. Wait for completion                                             │
│ 6. Validate changes against boundaries                             │
│ 7. If OK → commit, update STATUS.json                              │
│    If VIOLATION → rollback, create incident                        │
│                                                                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             │ subprocess (isolated)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ WORKER (project level)                                              │
│                                                                     │
│ Context:                                                            │
│ • cwd = project_path                                               │
│ • Reads: project/CLAUDE.md, project/docs/*                         │
│ • Writes: project/** (within boundary)                             │
│ • Tools: ptero-tool CLI (isolated)                                 │
│                                                                     │
│ CANNOT see:                                                         │
│ • studio/docs/* (orchestrator level)                               │
│ • other_projects/**                                                │
│                                                                     │
│ Output:                                                             │
│ • Modified files (validated by orchestrator)                       │
│ • Updated project/docs/STATUS.json                                 │
│ • Completion status                                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Violation Handling

```python
class IsolationViolation(Exception):
    """Raised when worker attempts to access outside boundaries."""
    pass

class ViolationHandler:
    def handle(self, project: str, violations: list[str]):
        # 1. Rollback all changes
        self._git_reset_hard(project)

        # 2. Log incident
        incident = {
            "timestamp": datetime.now().isoformat(),
            "project": project,
            "violations": violations,
            "action": "rollback"
        }
        self._append_to_log("studio/logs/violations.jsonl", incident)

        # 3. Alert
        self._notify(f"ISOLATION VIOLATION in {project}: {violations}")

        # 4. Mark task for human review
        self._flag_task_for_review(project)
```
