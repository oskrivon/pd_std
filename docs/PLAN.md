# План

## In Progress

(Нет активных задач)

## TODO

### Telegram интеграция (источник задач)

- [ ] **Telegram Bot Integration** (`core/telegram_source.py`):
  - [ ] Подключение к Telegram Bot API (python-telegram-bot или aiogram)
  - [ ] Парсинг сообщений из рабочей группы проекта
  - [ ] Распознавание задач из резюме бота (формат `@User: описание задачи`)
  - [ ] Автоматическое определение проекта по контексту/тегам
  - [ ] Команда `/task <project> <description>` для добавления через бота
  - [ ] Polling или Webhook режим
  - [ ] Дедупликация (не добавлять одну задачу дважды)
  - [ ] Уведомления о статусе задачи обратно в группу

- [ ] **CLI команды**:
  - [ ] `ptero-studio telegram import` — ручной импорт из канала
  - [ ] `ptero-studio telegram watch` — режим наблюдения за группой
  - [ ] `ptero-studio telegram status` — статус подключения

### Asset Review System

- [ ] **Auto-regeneration daemon** (`core/asset_regenerator.py`):
  - [ ] Мониторинг assets с status="pending" (после feedback)
  - [ ] Автоматическая перегенерация с учетом feedback
  - [ ] Интеграция с FeedbackProcessor для построения промптов
  - [ ] Настройка: max_retries, cooldown между генерациями
  - [ ] CLI: `ptero-studio assets watch` — режим наблюдения
  - [ ] CLI: `ptero-studio assets regenerate <asset_id>` — ручной запуск

- [ ] **Partial UI deploy** (remote access without local API):
  - [ ] Разделение web UI и генерации (UI → remote, generation → local)
  - [ ] WebSocket bridge для команд UI → local worker
  - [ ] Tunnel (ngrok/cloudflared) для доступа к локальному серверу
  - [ ] Альтернатива: статический UI + polling к local API через tunnel

### Следующие улучшения

- [ ] **Prompt caching** — оптимизация токенов через кэширование

### Web Dashboard UX

- [ ] **Улучшение UX админки** (`web/`):
  - [ ] Realtime обновления через WebSocket (не polling)
  - [ ] Фильтры по проекту и статусу
  - [ ] Поиск по задачам
  - [ ] Детальный просмотр задачи (description, output, error)
  - [ ] Drag-and-drop изменение приоритета
  - [ ] Подтверждение перед удалением/отменой
  - [ ] Индикатор прогресса демона (какая задача выполняется)
  - [ ] История выполнения с таймингами
  - [ ] Dark mode

## Done

### 2026-02-22 — Context Isolation
- [x] **Context isolation** (`core/isolation.py`):
  - [x] IsolationConfig class (.isolation files)
  - [x] Path validation (boundary + restricted paths)
  - [x] Post-execution boundary check
  - [x] Automatic rollback on violations
  - [x] Isolation rules in worker prompt
  - [x] 17 unit tests for isolation

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
- [ ] **Web UI** — дашборд для мониторинга
- [ ] **Notifications** — Telegram/Discord уведомления

## Done

### 2026-02-22 — MVP Complete
- [x] **Opus Analyzer Pipeline** (`core/analyzer.py`):
  - [x] Классификация задач: SIMPLE, CLEAR, COMPLEX, UNCLEAR
  - [x] COMPLEX → автоматическая декомпозиция на подзадачи
  - [x] UNCLEAR → отклонение с фидбэком пользователю
  - [x] Рекомендация модели (Opus/Sonnet/Haiku)
  - [x] Контекст про игровые объекты (уровень = локация, не меню)
  - [x] Флаг `--no-analyze` для пропуска анализа

- [x] **Фаза 3: Continuous Mode**:
  - [x] `core/daemon.py` — непрерывное выполнение задач
  - [x] Graceful shutdown по Ctrl+C
  - [x] Опции: --max, --interval, --max-failures
  - [x] `core/budget.py` — подсчёт токенов и стоимости
  - [x] Дневные и месячные лимиты

- [x] **Декомпозиция идей** (`core/decomposer.py`):
  - [x] Разбивка идей на конкретные задачи через Claude Code
  - [x] Команда `ptero-studio idea`
  - [x] --dry-run для просмотра без добавления

- [x] **CLI расширения**:
  - [x] `ptero-studio daemon` — continuous mode
  - [x] `ptero-studio budget` — показ бюджета
  - [x] `ptero-studio idea` — декомпозиция идеи
  - [x] `ptero-studio validate` — валидация проекта

- [x] **Unreal интеграция**:
  - [x] Проекты автоматически обнаруживаются
  - [x] Валидация через window capture (если редактор открыт)

### 2025-02-22 — Core Infrastructure
- [x] **Фаза 1: Core Infrastructure**:
  - [x] `core/project.py` — модель проекта с discover и scaffold
  - [x] `core/task_queue.py` — приоритетная очередь (heapq + JSON)
  - [x] `core/orchestrator.py` — координатор с Claude Code интеграцией
  - [x] `cli.py` — CLI `ptero-studio` (projects, tasks, add, run, new, status)

- [x] **Фаза 2: Worker System** (интегрировано в orchestrator):
  - [x] Subprocess `claude` с --cwd проекта
  - [x] Передача задачи через stdin (ключевое: без -p включает tool execution)
  - [x] Чтение результата и обработка ошибок
  - [x] smoke_test(): run → capture → validate (для LÖVE)

- [x] **Toolbox (Фаза 0)**:
  - [x] tools/window_capture — захват окон (PrintWindow API)
  - [x] tools/vision_validator — проверка через Claude Vision
  - [x] tools/game_runner — запуск LÖVE/Unreal
  - [x] tools/cli.py — единая точка входа ptero-tool

- [x] Создан pyproject.toml

### 2025-02-21 — Planning
- [x] Создана структура документации
- [x] Написан CLAUDE.md, ARCHITECTURE.md
- [x] Создана структура tools/
- [x] Написаны CLAUDE.md для инструментов
