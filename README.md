# Ptero Dactyl Studio

AI-driven геймдев студия. Ты генерируешь идеи — AI реализует прототипы.

## Концепция

```
ТЫ: "Tower defense с магами, изометрия, LÖVE 2D"
                    │
                    ▼
        ┌───────────────────────┐
        │     ORCHESTRATOR      │  ← Claude Opus декомпозирует
        │   (декомпозиция)      │
        └───────────┬───────────┘
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
┌───────┐      ┌───────┐      ┌───────┐
│ CODE  │      │  ART  │      │ TEST  │
│WORKER │      │WORKER │      │WORKER │
└───┬───┘      └───┬───┘      └───┬───┘
    │              │              │
    └──────────────┼──────────────┘
                   ▼
        ┌───────────────────────┐
        │     VALIDATOR         │  ← Vision проверяет результат
        │  (smoke + gameplay)   │
        └───────────────────────┘
                   │
                   ▼
           ИГРАБЕЛЬНЫЙ ПРОТОТИП
```

## Быстрый старт

```bash
# 1. Установить зависимости
pip install anthropic openai pillow pyautogui psutil

# 2. Настроить API ключи
cp studio/config/.env.example studio/config/.env
# Отредактировать .env

# 3. Создать проект из идеи
python -m studio.cli init "tower_defense" --engine love

# 4. Запустить разработку
python -m studio.cli run tower_defense
```

## Поддерживаемые движки

| Движок | Статус | Описание |
|--------|--------|----------|
| **LÖVE 2D** | Готов | 2D игры на Lua |
| **Unreal Engine** | Готов | 3D/сложные проекты (через babylon/MCP) |
| **Blender** | В работе | 3D модели → 2D спрайты |

## Генерация ассетов

| Метод | Когда использовать |
|-------|-------------------|
| **DALL-E** | Уникальные персонажи, иллюстрации |
| **Procedural** | Тайлы, паттерны, градиенты |
| **Blender** | 3D модели, изометрические спрайты |
| **Placeholder** | WIP, быстрые прототипы |

## Режимы работы

### Интерактивный (по задачам)
```bash
python -m studio.cli run backpack_hero
# Выполняет первую задачу из BACKLOG.md
```

### Daemon (непрерывный)
```bash
python -m studio.cli daemon --budget 1000000
# Работает пока есть задачи и бюджет
```

### Idea-driven (от идеи до прототипа)
```bash
python -m studio.cli idea "roguelike с колодой карт"
# Полный цикл: декомпозиция → код → ассеты → тесты
```

## Структура

```
studio/
├── CLAUDE.md          # Контекст для AI
├── README.md          # Этот файл
├── cli.py             # Точка входа
│
├── core/              # Ядро системы
├── adapters/          # Адаптеры движков
├── assets/            # Генерация ассетов
├── validation/        # Тестирование
├── config/            # Настройки
│
└── docs/              # Документация
    ├── ARCHITECTURE.md
    ├── PLAN.md
    ├── PROGRESS.md
    └── RUNBOOK.md
```

## Документация

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — полная архитектура системы
- [PLAN.md](docs/PLAN.md) — план реализации по фазам
- [RUNBOOK.md](docs/RUNBOOK.md) — инструкции по запуску
- [PROGRESS.md](docs/PROGRESS.md) — лог изменений

## Принципы

1. **Автономность** — минимум вмешательства человека
2. **Непрерывность** — daemon работает пока есть задачи
3. **Жадность** — оптимизация использования токенов
4. **Fail Fast** — валидация после каждого изменения
5. **Переиспользование** — не дублировать код (babylon/MCP)

## Связанные проекты

| Проект | Описание |
|--------|----------|
| [backpack_hero](../backpack_hero/) | LÖVE 2D roguelike — тестовый полигон |
| [babylon](../babylon/) | Unreal CCG — источник MCP интеграции |
| [hamster](../hamster/) | LÖVE 2D мини-проект |

---

*Ptero Dactyl Studio — let AI build your games*
