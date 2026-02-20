# Project: Ptero Dactyl Studio

AI-driven геймдев студия: человек генерирует идеи, AI реализует прототипы автономно и непрерывно.

## Стек

- Python 3.11+ (orchestrator, adapters, validation)
- Claude Code / Claude API (Opus для архитектуры, Sonnet для кода, Haiku для рутины)
- LÖVE 2D (Lua) — 2D игры
- Unreal Engine 5.7 (C++) — 3D/сложные проекты
- Blender (Python API) — 3D модели, рендер спрайтов
- Houdini (опционально) — процедурная генерация
- DALL-E API — генерация арт-ассетов

## Документация — маршрутизация

При работе с документами используй СТРОГО эти файлы:

| Что записать | Куда | Формат |
|---|---|---|
| Архитектура, модули, зависимости | `docs/ARCHITECTURE.md` | Обнови нужный раздел |
| Как запустить / задеплоить / починить | `docs/RUNBOOK.md` | Обнови нужный раздел |
| План рефакторинга | `docs/REFACTORING.md` | Новая запись в `## Активный` |
| Новая задача или фича | `docs/PLAN.md` | Добавь в `## TODO` |
| Идея на потом | `docs/PLAN.md` | Добавь в `## Backlog` |
| Новое исследование | `docs/[ТЕМА]_RESEARCH.md` | Создай файл + добавь ссылку в `docs/RESEARCH.md` → Активные |
| Исследование завершено | Перенеси в `docs/archive/`, обнови `docs/RESEARCH.md` — добавь однострочный вывод в Архив |
| Результат / что сделано | `docs/PROGRESS.md` | Новая запись СВЕРХУ с датой |
| Бенчмарк / замер | `docs/PROGRESS.md` | В раздел `## Бенчмарки` |
| Принятое решение | `docs/RESEARCH.md` | В раздел `## Решения` |

## Быстрые команды

Когда я говорю:
- "запиши в план" → `docs/PLAN.md`, раздел TODO
- "в бэклог" → `docs/PLAN.md`, раздел Backlog
- "сохрани исследование" → `docs/RESEARCH.md` + отдельный файл если нужно
- "решение принято" → `docs/RESEARCH.md`, раздел Решения
- "готово" / "сделано" → `docs/PROGRESS.md`
- "замерь" / "бенчмарк" → `docs/PROGRESS.md`, раздел Бенчмарки
- "в архив" → перенеси в `docs/archive/`

## Правила записи

- Новые записи — СВЕРХУ (новое первым)
- Дата в формате YYYY-MM-DD
- НЕ удаляй существующие записи
- Если в PLAN.md больше 30 задач в Done — перенеси в `docs/archive/plan-YYYY-MM.md`
- Если не уверен куда записать — спроси

## Структура проекта

```
studio/
├── CLAUDE.md              # Этот файл
├── README.md              # Обзор для людей
├── cli.py                 # Точка входа: ptero-studio
│
├── core/
│   ├── orchestrator.py    # Главный координатор (декомпозиция идей)
│   ├── task_queue.py      # Очередь задач с приоритетами
│   ├── project.py         # Модель проекта
│   ├── daemon.py          # Continuous execution loop
│   └── budget.py          # Token economy, выбор модели
│
├── adapters/
│   ├── base.py            # Базовый класс EngineAdapter
│   ├── love.py            # LÖVE 2D: run, capture, inject
│   ├── unreal.py          # Unreal Engine (обёртка над MCP)
│   └── dcc/
│       ├── blender.py     # Blender Python API
│       └── houdini.py     # Houdini (опционально)
│
├── assets/
│   ├── generator.py       # Комбинированный генератор
│   ├── dalle.py           # DALL-E интеграция
│   └── procedural.py      # Процедурные алгоритмы
│
├── validation/
│   ├── validator.py       # Vision + gameplay tests
│   └── scenarios.py       # Тестовые сценарии
│
├── config/
│   ├── settings.py        # Пути, API ключи
│   └── prompts/           # Системные промпты
│       ├── orchestrator.md
│       ├── code_worker.md
│       └── art_worker.md
│
└── docs/                  # Документация (этот шаблон)
    ├── ARCHITECTURE.md
    ├── PLAN.md
    ├── PROGRESS.md
    ├── RESEARCH.md
    ├── REFACTORING.md
    ├── RUNBOOK.md
    └── archive/
```

## Важные правила кода

- **Adapters** должны наследоваться от `EngineAdapter` и реализовывать unified API
- **Orchestrator** использует Claude Opus для декомпозиции, не Sonnet
- **Validation** обязателен после каждого значимого изменения
- При работе с Unreal — переиспользовать `babylon/MCP`, не дублировать
- Daemon mode должен быть graceful: корректное завершение по сигналу
- Логи в `studio/logs/`, ротация по дате

## Связанные проекты

| Проект | Путь | Описание |
|--------|------|----------|
| backpack_hero | `../backpack_hero/` | LÖVE 2D roguelike (тестовый полигон) |
| babylon | `../babylon/` | Unreal CCG (источник MCP интеграции) |
| hamster | `../hamster/` | LÖVE 2D мини-проект |

## Принципы работы

1. **Идея → Декомпозиция → Задачи → Выполнение → Валидация**
2. **Жадность**: всегда выбирать задачу с лучшим ROI (value / tokens)
3. **Fail Fast**: smoke test после каждого изменения
4. **Непрерывность**: daemon работает пока есть задачи и бюджет
5. **Автономность**: минимум вмешательства человека
