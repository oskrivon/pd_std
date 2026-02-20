# Рефакторинг

## Активный

### Миграция studio/README.md в новую структуру — 2025-02-21
**Что:** Существующий README.md описывает BACKLOG-driven workflow
**Зачем:** Интегрировать в Orchestrator, сохранить обратную совместимость
**План:**
1. [ ] Сохранить BACKLOG.md формат как один из входов для TaskQueue
2. [ ] Orchestrator умеет читать BACKLOG.md и конвертировать в Task objects
3. [ ] CLI поддерживает оба режима: idea-driven и backlog-driven
**Риски:** Потеря простоты текущего workflow
**Статус:** Запланировано

### Извлечение window_capture из babylon — 2025-02-21
**Что:** babylon/MCP/window_capture.py содержит полезный код для LÖVE
**Зачем:** LoveAdapter нужен захват окна, код уже написан
**План:**
1. [ ] Создать shared/window_capture.py
2. [ ] Импортировать в babylon/MCP и studio/adapters
3. [ ] Убрать дублирование
**Риски:** Минимальные
**Статус:** Запланировано

## Завершённые

## Отложенные
