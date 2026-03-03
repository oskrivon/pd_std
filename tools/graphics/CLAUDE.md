# Graphics Tool

AI-powered инструмент для создания и валидации игровой графики.

## Возможности

### Генерация

| Модуль | Описание | API |
|--------|----------|-----|
| `sprites` | Спрайты персонажей, предметов, объектов | PixelLab |
| `ui` | Иконки, кнопки, панели, рамки | PixelLab |
| `portraits` | Портреты персонажей в стиле Deceiver | PixelLab + postprocess |
| `tiles` | Тайлы для карт (повторяющиеся) | PixelLab |
| `concepts` | Концепт-арт, референсы | AIML API (Flux, Gemini) |

### Трансформации

| Модуль | Описание | API |
|--------|----------|-----|
| `rotate` | Ротации спрайтов (8 направлений) | PixelLab |
| `sprite_animation` | Покадровая анимация спрайтов (НЕ 3D!) | PixelLab |
| `stylize` | Стилизация (Deceiver, Loop Hero, custom) | Local + AI |
| `pixelate` | Пикселизация с сохранением деталей | Local |

#### Sprite Animation Presets

| Preset | Action | Loop | Описание |
|--------|--------|------|----------|
| `idle` | idle breathing | ping-pong | Стояние на месте |
| `walk` | walk cycle | ping-pong | Ходьба |
| `run` | run cycle | loop | Бег |
| `attack` | attack swing | once | Базовая атака |
| `attack_sword` | sword attack swing | once | Атака мечом |
| `attack_magic` | cast magic spell | once | Каст заклинания |
| `jump` | jump up and land | once | Прыжок |
| `hurt` | take damage hit | once | Получение урона |
| `death` | death fall down | once | Смерть |
| `item_use` | use item interact | once | Использование предмета |

### Валидация

| Модуль | Описание | API |
|--------|----------|-----|
| `ui_check` | Читаемость UI, контраст, размеры | Vision API |
| `style_check` | Консистентность стиля в наборе | Vision API |
| `palette_check` | Проверка соответствия палитре | Local |

### Утилиты

| Модуль | Описание |
|--------|----------|
| `spritesheet` | Сборка sprite sheets из отдельных кадров |
| `slice9` | 9-slice нарезка для растягиваемых панелей |
| `palette` | Извлечение и применение палитр |
| `batch` | Batch обработка папок |

## Структура

```
tools/graphics/
├── CLAUDE.md           # Этот файл
├── __init__.py
├── cli.py              # CLI: ptero-graphics
│
├── generators/
│   ├── pixellab.py     # PixelLab API wrapper
│   ├── sprites.py      # Генерация спрайтов
│   ├── ui.py           # UI элементы
│   ├── portraits.py    # Портреты персонажей
│   └── concepts.py     # Концепт-арт (AIML)
│
├── transforms/
│   ├── rotate.py       # 8-направленные ротации
│   ├── animate.py      # Анимации
│   ├── stylize.py      # Стилизация (Deceiver и др.)
│   └── pixelate.py     # Пикселизация
│
├── validators/
│   ├── ui_validator.py     # Валидация UI
│   ├── style_validator.py  # Консистентность стиля
│   └── palette_validator.py # Проверка палитры
│
├── utils/
│   ├── spritesheet.py  # Сборка sprite sheets
│   ├── slice9.py       # 9-slice нарезка
│   ├── palette.py      # Работа с палитрами
│   └── batch.py        # Batch обработка
│
├── palettes/           # Готовые палитры
│   ├── deceiver.json
│   ├── loop_hero.json
│   └── custom/
│
└── templates/          # Шаблоны для генерации
    ├── ui_button.json
    ├── inventory_icon.json
    └── character_portrait.json
```

## CLI

```bash
# Генерация спрайта
ptero-graphics sprite "warrior with sword" output.png --size 64

# Генерация с референсом стиля
ptero-graphics sprite "dark mage" mage.png --ref deceiver_warrior.png --strength 70

# Ротации (8 направлений)
ptero-graphics rotate sprite.png output_dir/ --angles 8

# Анимация
ptero-graphics animate sprite.png walk.gif --type skeleton --frames 8

# Стилизация
ptero-graphics stylize input.png output.png --style deceiver

# UI элементы
ptero-graphics ui icon "health potion" potion.png --size 32
ptero-graphics ui button "Start Game" button.png --width 128 --height 48
ptero-graphics ui panel panel.png --width 200 --height 200 --style medieval

# Валидация UI
ptero-graphics validate ui screenshot.png --check contrast,readability

# Batch обработка
ptero-graphics batch stylize input_dir/ output_dir/ --style deceiver
```

## API Keys

Требуемые ключи в `config/.env`:

```env
PIXELLAB_API_KEY=xxx    # PixelLab (спрайты, ротации, анимации)
AIMLAPI_KEY=xxx         # AIML API (концепты, валидация)
```

## Пайплайны

### Спрайтовая анимация персонажа

```python
from tools.graphics.transforms import sprite_animation

# Простая анимация по пресету
result = sprite_animation.animate_sprite_preset(
    reference_image="knight.png",
    description="knight in armor",
    preset="walk",  # idle, walk, run, attack, jump, hurt, death
    direction="east",
    size=64
)

# Сохранить как GIF (x4 масштаб для наглядности)
sprite_animation.create_sprite_gif(result, "knight_walk.gif", scale=4)

# Сохранить как sprite sheet
sprite_animation.create_sprite_sheet(result, "knight_walk_sheet.png")

# Генерация набора анимаций для персонажа
sprite_animation.generate_character_animations(
    reference_image="knight.png",
    description="knight in armor",
    output_dir="knight_animations/",
    presets=["idle", "walk", "attack", "hurt"],
    directions=["east", "west"],  # или все 8 направлений
    create_gifs=True,
    create_sheets=True
)
```

### Персонаж в стиле Deceiver

```python
from tools.graphics import sprites, transforms

# 1. Генерация базового спрайта с референсом
sprite = sprites.generate(
    description="old wizard with staff and hat",
    ref_image="deceiver_warrior.png",
    strength=70,
    size=400
)

# 2. Постобработка для "грязного" стиля
styled = transforms.stylize(sprite, style="deceiver_rough")

# 3. Ротации
rotations = transforms.rotate(styled, angles=8, size=64)
```

### UI набор

```python
from tools.graphics import ui, utils

# Генерация элементов
icons = ui.generate_icons(["sword", "shield", "potion"], size=32)
button = ui.generate_button("Play", width=128, height=48)
panel = ui.generate_panel(width=200, height=200, style="dark_fantasy")

# Сборка sprite sheet
utils.spritesheet.create(icons, output="icons_sheet.png", columns=4)

# 9-slice нарезка панели
utils.slice9.create(panel, output_dir="panel_slices/", margin=16)
```

### Валидация

```python
from tools.graphics import validators

# Проверка UI скриншота
result = validators.ui_check(
    "game_screenshot.png",
    checks=["contrast", "readability", "touch_targets"]
)

# Проверка консистентности стиля
style_result = validators.style_check(
    images=["char1.png", "char2.png", "char3.png"],
    reference_style="deceiver"
)
```

## Лимиты API

### PixelLab

| Параметр | Лимит |
|----------|-------|
| pixflux max size | 400×400 |
| bitforge max size | 200×200 |
| rotate/animate | 200×200 |

### Рекомендации

- Спрайты предметов: 32×32, 64×64
- Портреты: 200×200, 400×400
- UI иконки: 32×32, 64×64
- Кнопки: 128×48
- Панели: 200×200 (для 9-slice)

## Исследования

Результаты экспериментов в `docs/PROGRESS.md`:
- PixelLab API: img2img, rotate, animate
- Deceiver стилизация: пайплайн постобработки
- UI пикселизация: локальная vs AI
