# Прогресс

## Лог

### 2026-02-22 (session 4)
- **Test Suite** (111 tests total, all passing):
  - 65 unit tests (task_queue, project_status, budget)
  - 34 integration tests (orchestrator, analyzer)
  - 12 E2E tests (full cycle, CLI, parallel execution)
  - `ptero-studio test` command (--unit, --integration, --e2e, --coverage)
  - Thread-safety tests for parallel workers
  - Fixed: e2e tests now use `analyze=False` for mocked tests
  - Fixed: ParallelExecutor tests use class-level patching

- **Inter-project Communication**:
  - `core/project_status.py` — STATUS.json для проектов
  - Состояния: idle, working, blocked, error, ready
  - Автоматическое обновление в orchestrator
  - `ptero-studio status --projects` для обзора всех проектов

- **Parallel Workers**:
  - `core/parallel.py` — параллельное выполнение задач
  - Thread-safe task queue с project locking
  - `--workers N` (1-4) для daemon команды
  - Разные проекты выполняются параллельно, один проект — последовательно

- **File Logging**:
  - `core/logging_config.py` — настройка логирования
  - `logs/daemon.log` — общий лог демона (daily rotation, 7 дней)
  - `logs/tasks.log` — детальный лог задач
  - Флаг `--no-log` для отключения файлового логирования

### 2026-02-22 (session 3)
- **Opus Analyzer Pipeline**:
  - `core/analyzer.py` — анализ задач через Opus перед выполнением
  - Классификация: SIMPLE, CLEAR, COMPLEX, UNCLEAR
  - COMPLEX → автоматическая декомпозиция на подзадачи
  - UNCLEAR → отклонение с фидбэком пользователю
  - Флаг `--no-analyze` для пропуска анализа

- **Улучшенный промпт**:
  - Контекст про игровые объекты (уровень = локация, не меню)
  - Рекомендуемые файлы для чтения
  - Поддержка `--model` для выбора модели

- **Тест на реальной задаче**:
  - "добавить парк с деревьями" → Opus декомпозировал на 7 подзадач
  - "сделай интереснее" → Opus отклонил как UNCLEAR
  - Создан park_room.lua, rooms.lua, система переходов
  - Игра работает с новым контентом

- **Статистика сессии**:
  - 19 задач выполнено
  - 2 задачи отклонены (UNCLEAR)
  - $0.08 потрачено

### 2026-02-22 (session 2)
- **MVP готов и протестирован**:
  - Полный цикл: idea → decompose → daemon → validate → budget
  - Тест на hamster: добавлен loading screen через 3 автоматические задачи

- **Daemon mode** (`ptero-studio daemon`):
  - Непрерывное выполнение задач из очереди
  - Опции: --max, --interval, --max-failures
  - Graceful shutdown по Ctrl+C

- **Budget tracking** (`ptero-studio budget`):
  - Подсчёт токенов и стоимости
  - Дневные и месячные лимиты
  - Интеграция с orchestrator

- **Декомпозиция идей** (`ptero-studio idea`):
  - Разбивка идей на конкретные задачи через Claude Code
  - --dry-run для просмотра без добавления
  - --max-tasks для ограничения

- **Unreal интеграция**:
  - Проекты автоматически обнаруживаются
  - Валидация через window capture (если редактор открыт)

- **Валидация для LÖVE**:
  - Background capture работает (PrintWindow API)
  - Скриншоты сохраняются в `studio/validation/`

### 2025-02-22
- **Реализован Toolbox (Фаза 0)**:
  - `tools/window_capture/` — захват окон через Windows API
  - `tools/vision_validator/` — проверка через Claude Vision API
  - `tools/game_runner/` — запуск LÖVE/Unreal проектов
  - `tools/cli.py` — единая точка входа `ptero-tool`
- **Реализован Core Infrastructure (Фаза 1)**:
  - `core/project.py` — модель проекта с discover и scaffold
  - `core/task_queue.py` — приоритетная очередь задач (JSON persistence)
  - `core/orchestrator.py` — координатор (проекты + задачи + выполнение через Claude Code)
  - `cli.py` — CLI `ptero-studio` (projects, tasks, add, run, new, status)
- **Протестирован полный цикл**: add → run → Claude Code выполняет → коммит
- Ключевое открытие: stdin без `-p` включает tool execution в Claude CLI
- Создан `pyproject.toml`

### 2025-02-21 (session 2)
- Добавлена архитектура Toolbox — инструменты как отдельные модули
- Добавлена архитектура Inter-project Communication (STATUS.json)
- Добавлена архитектура Context Isolation (многоуровневая защита)
- Создана структура tools/ с документацией для 3 инструментов
- Создан шаблон isolation.yaml для границ проектов
- Создан системный промпт worker_isolation.md (EN) для изоляции агентов
- Добавлены фазы 0, 0.5, 0.6 в план реализации
- Добавлена секция Task Decomposition с decision tree
- Добавлена секция Git Strategy (multi-repo)
- Инициализирован git репозиторий для studio/
- Создан .gitignore для workspace и studio

### 2025-02-21 (session 1)
- Создана структура документации Ptero Dactyl Studio
- Написана архитектура системы (Orchestrator, Adapters, Validation)
- Определены 7 фаз реализации
- Интегрированы существующие наработки:
  - babylon/MCP → UnrealAdapter
  - backpack_hero → тестовый полигон для LoveAdapter
  - studio/README.md → основа для CLI

## Бенчмарки

### Базовые метрики

| Метрика | Значение | Дата | Контекст |
|---------|----------|------|----------|
| babylon MCP tools | 28 | 2025-02-21 | Готовы к интеграции |
| backpack_hero LOC | ~18,600 | 2025-02-21 | Тестовый проект |
| Token cost (Vision 800x600) | 640 tokens | 2025-02-21 | Из babylon docs |

### История измерений

<!-- Шаблон:
### YYYY-MM-DD — [Что изменилось]
**До:** ...
**После:** ...
**Вывод:** ...
-->
