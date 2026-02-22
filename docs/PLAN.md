# План

## In Progress

### Фаза 1: Core Infrastructure

## TODO

### Фаза 1: Core Infrastructure (управление проектами)

- [x] **core/project.py** — модель проекта
  - [x] Dataclass Project (path, engine, status)
  - [x] Загрузка из CLAUDE.md / конфига
  - [x] Scaffold для нового LÖVE / Unreal проекта
  - [x] Git init + .gitignore по типу движка

- [x] **core/task_queue.py** — очередь задач
  - [x] Dataclass Task (id, project, description, priority, status)
  - [x] Приоритетная очередь (heapq)
  - [x] Сериализация в JSON (tasks.json)
  - [x] Методы: add(), pop_best(), complete(), fail()

- [x] **core/orchestrator.py** — координатор
  - [x] Загрузка проектов из workspace
  - [x] Dispatch задач на выполнение (через Claude CLI)
  - [x] Валидация после выполнения (через tools/)
  - [ ] Декомпозиция идей → задачи (Claude API) — TODO

- [x] **cli.py** — точка входа `ptero-studio`
  - [x] `ptero-studio projects` — список проектов
  - [x] `ptero-studio tasks` — список задач
  - [x] `ptero-studio add <project> "<task>"` — добавить задачу
  - [x] `ptero-studio run [--once]` — выполнить задачи
  - [x] `ptero-studio new <name>` — создать проект
  - [x] `ptero-studio status` — общий статус

### Фаза 2: Worker System (выполнение задач)

- [ ] **core/worker.py** — запуск Claude Code
  - [ ] Subprocess `claude` с --cwd проекта
  - [ ] Передача задачи через prompt
  - [ ] Чтение результата

- [ ] **core/validator.py** — валидация результата
  - [ ] Интеграция с tools/game_runner
  - [ ] Интеграция с tools/vision_validator
  - [ ] smoke_test(): run → capture → validate

- [ ] **adapters/love.py** — LÖVE адаптер
  - [ ] Использует tools/game_runner
  - [ ] Использует tools/window_capture

### Фаза 3: Continuous Mode

- [ ] **core/daemon.py** — непрерывный режим
  - [ ] run_forever() с graceful shutdown
  - [ ] Логирование в файл

- [ ] **core/budget.py** — token tracking
  - [ ] Подсчёт использования
  - [ ] Alerts при лимите

## Backlog

### Asset Generation (когда понадобится)
- [ ] **tools/asset_gen/** — DALL-E + procedural
- [ ] **assets/dalle.py** — DALL-E клиент
- [ ] **assets/procedural.py** — процедурная генерация

### DCC Integration (когда понадобится)
- [ ] **adapters/dcc/blender.py** — Blender headless
- [ ] **adapters/dcc/houdini.py** — Houdini (опционально)

### Unreal Integration (когда понадобится)
- [ ] **adapters/unreal.py** — обёртка над babylon/MCP

### Advanced Features
- [ ] **Web UI** — дашборд
- [ ] **Notifications** — Telegram/Discord
- [ ] **Parallel workers** — несколько сессий
- [ ] **Prompt caching** — оптимизация токенов
- [ ] **Inter-project communication** — STATUS.json
- [ ] **Context isolation** — boundary validation

## Done

### 2025-02-22
- [x] Реализован Toolbox (Фаза 0):
  - [x] tools/window_capture — захват окон (PrintWindow API)
  - [x] tools/vision_validator — проверка через Claude Vision
  - [x] tools/game_runner — запуск LÖVE/Unreal
  - [x] tools/cli.py — единая точка входа ptero-tool
- [x] Создан pyproject.toml

### 2025-02-21
- [x] Создана структура документации
- [x] Написан CLAUDE.md, ARCHITECTURE.md
- [x] Создана структура tools/
- [x] Написаны CLAUDE.md для инструментов
