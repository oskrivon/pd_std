# UI Concept Generation Research

Исследование моделей и workflow для генерации UI концептов игр.

## Дата: 2026-03-02

## Цель

Найти оптимальную модель и workflow для генерации UI/интерфейсов игр по референсам.

## Протестированные модели

### Через AIML API

| Модель | Скорость | Качество UI | Текст | Цена | Вердикт |
|--------|----------|-------------|-------|------|---------|
| `flux/schnell` | Быстро (~5с) | Абстрактный | Плохой | Низкая | Для итераций |
| `flux-pro` | Средне (~15с) | Детальный | Хороший | Средняя | **Лучший выбор** |
| `dall-e-3` | - | - | - | - | 400 Error |

### По данным исследований (не тестировались)

| Модель | Сила | Применение |
|--------|------|------------|
| Midjourney V6/V7 | Художественность | Концепт-арт (нет API) |
| Ideogram 3.0 | Текст (90% точность) | UI с надписями |
| Imagen 4 | Чистые структуры | Wireframes |
| Adobe Firefly | Legal safety | Коммерческие проекты |

## Лучший промпт для UI

```
pixel art roguelike game screen, tactical mining interface, Into the Breach style UI

THREE CONNECTED ZONES:

LEFT ZONE - BACKPACK PANEL:
- Vertical panel with orange tech frame
- Title: BACKPACK with version label
- Triangular grid inventory inside mechanical frame
- Colored gem icons and tool items
- Load indicator (45/126)

RIGHT-UPPER ZONE - MINING FIELD:
- Large triangular tile exploration grid
- Irregular shape with glowing cyan border outline
- Brown/dark triangular cells pattern
- Stats overlay: cells 70, cleared 0

BOTTOM ZONE - CAVE ROOM:
- Isometric view of cave entrance
- Player character with backpack
- Multiple glowing lava pools (bright orange)
- Rock formations, cave walls

DARK COLOR SCHEME:
- Background: very dark gray/charcoal (#1a1a2e)
- UI panels: dark blue-gray (#16213e)
- Borders: cyan/teal glow (#0ff, #4ecdc4)
- Accents: orange (#ff6b35) for lava and highlights

Style: pixel art 16-bit, clean readable UI, dark sci-fi atmosphere
```

## Ключевые находки

### Что работает:
1. **Детальное описание зон** — модель лучше понимает layout
2. **Конкретные цвета в hex** — точнее результат
3. **Референс на известную игру** (Into the Breach) — стилистика
4. **"pixel art 16-bit"** — правильный стиль
5. **"clean readable UI"** — улучшает читаемость

### Что не работает:
1. Абстрактные описания ("nice UI")
2. Смешение стилей в одном промпте
3. Слишком много элементов (>5 зон)

## Workflow

```
1. Референсы
   └── UI стиль (Into the Breach, Darkest Dungeon, etc.)
   └── Компоновка (текущий проект)
   └── Цветовая схема

2. Анализ
   └── Определить зоны экрана
   └── Ключевые элементы каждой зоны
   └── Цветовую палитру

3. Промпт
   └── Английский язык
   └── Структура: ZONES → COLORS → STYLE
   └── Конкретные детали (размеры, числа, названия)

4. Генерация
   └── flux/schnell — быстрые наброски (3-5 вариантов)
   └── flux-pro — финальные концепты (3 варианта)

5. Итерация
   └── Выбрать лучший вариант
   └── Уточнить промпт
   └── Повторить с flux-pro
```

## Результаты для backpack_hero

Лучшие варианты сохранены в `studio/test_output/`:
- `v3.2_dark_1.png` — классическая компоновка
- `v3.2_dark_2.png` — максимум деталей, tech feel
- `v3.2_dark_3.png` — структурированный, чистый

## Источники

- [Best AI Image Generators 2025](https://pxz.ai/blog/best-ai-image-generators-2025-tested-ranked)
- [Midjourney vs DALL-E vs Flux](https://freeacademy.ai/blog/midjourney-vs-dalle-vs-stable-diffusion-vs-flux-comparison-2026)
- [AIML API Docs](https://docs.aimlapi.com/api-references/model-database)

## Статус

**В процессе** — можно расширить тестированием других моделей (Ideogram, Imagen 4)
