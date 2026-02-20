# План

## In Progress

## TODO

### Фаза 0: Toolbox (переиспользуемые инструменты)

- [ ] **tools/window-capture/** — захват окон
  - [ ] Портировать код из babylon/MCP/window_capture.py
  - [ ] CLI: `ptero-tool capture --window "TITLE" --output file.png`
  - [ ] Python API: `capture_window(window, output, resize)`

- [ ] **tools/vision-validator/** — проверка через Vision
  - [ ] Интеграция с Claude Vision API
  - [ ] CLI: `ptero-tool validate image.png --prompt "Game works?"`
  - [ ] Python API: `validate(image, prompt) -> ValidationResult`

- [ ] **tools/game-runner/** — запуск игр
  - [ ] Runner для LÖVE 2D (subprocess)
  - [ ] Runner для Unreal (через MCP)
  - [ ] CLI: `ptero-tool run project --engine love --capture`
  - [ ] Python API: `run_game(project, engine) -> GameProcess`

- [ ] **tools/asset-gen/** — генерация ассетов
  - [ ] DALL-E генератор
  - [ ] Процедурный генератор (placeholder, gradient, tiles)
  - [ ] CLI: `ptero-tool asset character --prompt "Fire mage"`

- [ ] **tools/ptero-tool CLI** — единая точка входа
  - [ ] Роутинг команд к инструментам
  - [ ] `ptero-tool --help` со списком всех команд

### Фаза 0.5: Inter-project Communication

- [ ] **core/project_scanner.py** — сканер проектов
  - [ ] Читать STATUS.json из всех проектов
  - [ ] Агрегировать статусы для Orchestrator

- [ ] **STATUS.json в каждом проекте**
  - [ ] Добавить в babylon/docs/STATUS.json
  - [ ] Добавить в backpack_hero/docs/STATUS.json
  - [ ] Worker обновляет STATUS.json после задачи

- [ ] **core/status_updater.py** — обновление статуса
  - [ ] Парсить PLAN.md → подсчёт задач
  - [ ] Проверять last_validation
  - [ ] Обновлять metrics (LOC, commits)

### Фаза 0.6: Context Isolation

- [ ] **core/worker_launcher.py** — изолированный запуск worker
  - [ ] Subprocess с --cwd проекта
  - [ ] Инъекция системного промпта с границами (EN)
  - [ ] Ограничение доступных tools

- [ ] **core/boundary_validator.py** — post-validation
  - [ ] Получить git diff после выполнения
  - [ ] Проверить все изменения в пределах boundary
  - [ ] Rollback при нарушении

- [ ] **core/violation_handler.py** — обработка нарушений
  - [ ] Логирование в studio/logs/violations.jsonl
  - [ ] Alert (Telegram/Discord)
  - [ ] Пометка задачи для ревью

- [ ] **.isolation файл в каждом проекте**
  - [ ] Создать babylon/.isolation
  - [ ] Создать backpack_hero/.isolation
  - [ ] Документировать формат в templates/

- [ ] **config/prompts/worker_isolation.md** — системный промпт
  - [ ] Строгие правила изоляции (EN)
  - [ ] Список forbidden actions
  - [ ] Инструкции при violation

### Фаза 1: Core Infrastructure (фундамент)

- [ ] **core/orchestrator.py** — главный координатор
  - [ ] Класс Orchestrator с методами decompose(), schedule(), dispatch()
  - [ ] Интеграция с Claude API для декомпозиции идей
  - [ ] Промпт для Opus в config/prompts/orchestrator.md

- [ ] **core/task_queue.py** — очередь задач
  - [ ] Приоритетная очередь с heapq
  - [ ] Метод pop_best() с учётом ROI
  - [ ] Сериализация/десериализация (JSON)

- [ ] **core/project.py** — модель проекта
  - [ ] Dataclass Project со структурой
  - [ ] Scaffold для LÖVE и Unreal проектов
  - [ ] Автогенерация CLAUDE.md и BACKLOG.md
  - [ ] Git init для нового проекта
  - [ ] Генерация .gitignore по типу движка
  - [ ] Initial commit с описанием проекта

- [ ] **adapters/base.py** — базовый адаптер
  - [ ] ABC EngineAdapter с unified API
  - [ ] Методы: create_project, run, capture, inject, get_state

- [ ] **adapters/love.py** — LÖVE 2D адаптер
  - [ ] Запуск через subprocess
  - [ ] Window capture (портировать из babylon)
  - [ ] Hot reload через файловую систему

### Фаза 2: Validation Pipeline

- [ ] **validation/validator.py** — валидатор
  - [ ] smoke_test(): запуск → скриншот → Claude Vision
  - [ ] gameplay_test(): выполнение сценария

- [ ] **validation/scenarios.py** — DSL сценариев
  - [ ] Парсер простого языка: "click 100,200; wait 1s; capture"
  - [ ] Интеграция с pyautogui/window automation

- [ ] **Интеграция Validator в Orchestrator**
  - [ ] Автоматическая валидация после каждой задачи
  - [ ] Создание fix-задач при провале

### Фаза 3: Asset Generation

- [ ] **assets/dalle.py** — DALL-E клиент
  - [ ] Генерация с промптом и стилем
  - [ ] Постобработка (remove background, resize)
  - [ ] Кэширование результатов

- [ ] **assets/procedural.py** — процедурная генерация
  - [ ] make_tileset(): простые тайлы кодом
  - [ ] make_gradient(): фоны
  - [ ] make_placeholder(): цветные прямоугольники с текстом

- [ ] **assets/generator.py** — фасад
  - [ ] Роутинг по типу ассета
  - [ ] Комбинирование методов

### Фаза 4: DCC Integration

- [ ] **adapters/dcc/blender.py** — Blender адаптер
  - [ ] Headless запуск с Python скриптом
  - [ ] render_sprite(): 3D → 2D спрайты
  - [ ] create_low_poly(): простые модели из примитивов

- [ ] **adapters/dcc/houdini.py** — Houdini адаптер (опционально)
  - [ ] Процедурные тайлсеты
  - [ ] VFX спрайт-шиты

### Фаза 5: Unreal Integration

- [ ] **adapters/unreal.py** — Unreal адаптер
  - [ ] Обёртка над babylon/MCP
  - [ ] Методы EngineAdapter делегируют в MCP
  - [ ] Rebuild pipeline интеграция

### Фаза 6: Daemon Mode

- [ ] **core/daemon.py** — непрерывное выполнение
  - [ ] run_forever() с graceful shutdown
  - [ ] Signal handlers (SIGINT, SIGTERM)
  - [ ] Логирование в файл

- [ ] **core/budget.py** — token economy
  - [ ] Трекинг использования по моделям
  - [ ] select_model() по типу задачи
  - [ ] Alerts при приближении к лимиту

- [ ] **Notifications**
  - [ ] Telegram/Discord webhook при milestones
  - [ ] Сводка за сессию

### Фаза 7: CLI и UX

- [ ] **cli.py** — точка входа
  - [ ] `ptero-studio init <name>` — создать проект
  - [ ] `ptero-studio run <project>` — выполнить задачи
  - [ ] `ptero-studio daemon` — запустить демон
  - [ ] `ptero-studio status` — показать очередь и прогресс

- [ ] **Интерактивный режим**
  - [ ] REPL для ввода идей
  - [ ] Просмотр прогресса в реальном времени

## Backlog

- [ ] **Web UI** — дашборд с прогрессом и логами
- [ ] **Godot адаптер** — если понадобится третий движок
- [ ] **Unity адаптер** — для 3D мобильных игр
- [ ] **Audio generation** — интеграция с Suno/ElevenLabs
- [ ] **Multiplayer testing** — запуск нескольких инстансов
- [ ] **A/B testing визуала** — сравнение вариантов через Vision
- [ ] **Cost optimization** — автоматический выбор дешёвой модели
- [ ] **Prompt caching** — переиспользование контекста между задачами
- [ ] **Parallel workers** — несколько Claude сессий одновременно
- [ ] **Git integration** — автоматические коммиты с описанием
- [ ] **Rollback** — откат к предыдущей рабочей версии

## Done

### 2025-02-21
- [x] Создана структура документации по шаблону
- [x] Написан CLAUDE.md с контекстом проекта
- [x] Написан ARCHITECTURE.md с полной архитектурой
- [x] Написан PLAN.md с фазами реализации
- [x] Добавлена секция Inter-project Communication в ARCHITECTURE.md
- [x] Добавлена секция Toolbox в ARCHITECTURE.md
- [x] Создана структура tools/ с CATALOG.md
- [x] Написаны CLAUDE.md для window-capture, vision-validator, game-runner
- [x] Создан шаблон templates/STATUS.json
- [x] Создан tools/__init__.py с ленивым импортом
- [x] Добавлена секция Tool Lifecycle в ARCHITECTURE.md
- [x] Добавлена секция Context Isolation в ARCHITECTURE.md
- [x] Создан templates/isolation.yaml — шаблон .isolation файла
- [x] Создан config/prompts/worker_isolation.md — системный промпт (EN)
- [x] Добавлена Фаза 0.6 (Context Isolation) в план
- [x] Добавлена секция Task Decomposition в ARCHITECTURE.md
