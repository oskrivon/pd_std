# Style Transfer Pipeline Research

**Дата:** 2026-03-03
**Цель:** Создать пайплайн стилизации скриншотов игры в стиле Deceiver (Loop Hero)

## Задача

Трансформировать игровые скриншоты в пиксельный стиль Deceiver (Dmitry Karimov):
- Приглушённая "ржавая" палитра (browns, burgundy, dark greens)
- Ограниченное количество цветов (16-32)
- Dithering
- Тёмная атмосфера dark fantasy
- Сохранение композиции и читаемости UI

## Протестированные модели

### AI img2img модели через AIML API

| Модель | Сохраняет layout | Качество стиля | Стоимость | Вердикт |
|--------|------------------|----------------|-----------|---------|
| **gemini-pro** | ✅ Отлично | ✅ Отлично | 390k credits | 🥇 **Лучший** |
| **flux-lora-edit** | ✅ Отлично | ✅ Хорошо | 109k credits | 🥈 Хорошо с LoRA |
| **reve-remix** | ✅ Хорошо | ✅ Хорошо | 104k credits | 🥉 Альтернатива |
| **qwen-edit** | ✅ Отлично | ✅ Хорошо | 117k credits | Надёжный |
| flux-edit | ❌ Генерирует новое | — | 62k credits | Не подходит |
| flux-kontext | ❌ Объединяет изображения | — | 104k credits | Не подходит |

### Важные находки

1. **Критичный баг:** Многие модели требуют `image_urls: [...]` (массив), а не `image_url: "..."` (строка). Без исходного изображения модели генерируют новую картинку по промпту вместо трансформации.

2. **Flux Kontext** не подходит для style transfer — архитектурно заточен на объединение/редактирование изображений, а не перенос стиля.

3. **LoRA** работают через HuggingFace repo ID (бесплатно) или Civitai URL (требует API токен).

### Доступные LoRA пресеты

| Пресет | Модель | Trigger word | Scale |
|--------|--------|--------------|-------|
| retro-pixel | prithivMLmods/Retro-Pixel-Flux-LoRA | "Retro Pixel" | 0.9 |
| modern-pixel | UmeAiRT/FLUX.1-dev-LoRA-Modern_Pixel_art | "modern pixel art" | 0.85 |
| pixel-art-xl | nerijs/pixel-art-xl | "pixel art" | 1.0 |

## Финальная архитектура пайплайна

```
[Input Image]
      ↓
┌─────────────────────────────┐
│  ЭТАП 1: AI Стилизация      │
│  Модель: gemini-pro         │
│  Промпт: balanced mood      │
│  Strength: 0.5              │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│  ЭТАП 2: Алгоритмическая    │
│  - Палитра Deceiver (32)    │
│  - Dithering (Bayer 4x4)    │
│  - Brightness boost 1.1     │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│  ЭТАП 3: UI Маска           │
│  - Сохранение текста        │
│  - Оригинальные цвета UI    │
│  - Feathered edges          │
└─────────────────────────────┘
      ↓
[Output Image]
```

## Рекомендуемые команды

### Полный пайплайн с Gemini Pro
```bash
python pipeline.py input.png output.png \
  --ai-model gemini-pro \
  --ai-mood balanced \
  --ai-strength 0.5 \
  --ui-mask backpack_hero_minimal
```

### Только AI (без алгоритма)
```bash
python ai_style_transfer.py input.png output.png \
  --model gemini-pro \
  --strength 0.6
```

### С LoRA
```bash
python ai_style_transfer.py input.png output.png \
  --model flux-lora-edit \
  --lora-preset retro-pixel \
  --strength 0.65
```

## Созданные файлы

| Файл | Описание |
|------|----------|
| `tools/style_transfer/ai_style_transfer.py` | AI img2img через AIML API |
| `tools/style_transfer/deceiver_style.py` | Алгоритмическая стилизация |
| `tools/style_transfer/pipeline.py` | Комбинированный пайплайн |
| `tools/style_transfer/ui_mask.py` | Маскирование UI |
| `tools/style_transfer/__init__.py` | Экспорт модулей |

## Палитра Deceiver (32 цвета)

Извлечена из Loop Hero:
- Тёмные: #1a1a2e, #16213e, #0f0f23
- Коричневые: #4a3728, #5c4033, #6b4423, #8b5a2b
- Красные: #722f37, #8b0000, #a0522d
- Зелёные: #2d4a3e, #3d5a4a, #556b2f
- Синие: #2c3e50, #34495e, #4a6fa5
- Акценты: #c9a959, #d4a574, #e8d4b8

## Production Workflow: Разделение на слои

Для продакшена рекомендуется разделять рендер на слои и стилизовать отдельно:

### Архитектура слоёв

```
┌─────────────────────────────────────┐
│  СЛОЙ 3: Текст (рендерится в игре)  │  ← Не стилизуется, поверх всего
├─────────────────────────────────────┤
│  СЛОЙ 2: UI рамки/панели            │  ← Опционально: свой стиль или оригинал
├─────────────────────────────────────┤
│  СЛОЙ 1: Игровой контент            │  ← Стилизуется через AI + алгоритм
│  (карта, персонажи, окружение)      │
└─────────────────────────────────────┘
```

### Workflow

1. **Игровой контент** — рендерится без UI → стилизация Gemini → алгоритм
2. **UI панели** — рендерятся отдельно → либо свой стиль, либо оригинал
3. **Текст** — рендерится в игре поверх стилизованного (шрифт, цвет контролируются в коде)

### Пример реализации (LÖVE 2D)

```lua
-- Создаём canvas для каждого слоя
local gameCanvas = love.graphics.newCanvas()
local uiCanvas = love.graphics.newCanvas()

function love.draw()
    -- Слой 1: Игровой контент
    love.graphics.setCanvas(gameCanvas)
    love.graphics.clear()
    drawMap()
    drawCharacters()
    drawEnvironment()

    -- Слой 2: UI рамки (без текста)
    love.graphics.setCanvas(uiCanvas)
    love.graphics.clear()
    drawUIFrames()
    drawUIPanels()

    -- Композиция на экран
    love.graphics.setCanvas()
    love.graphics.draw(gameCanvas)   -- стилизованный или оригинал
    love.graphics.draw(uiCanvas)     -- стилизованный или оригинал

    -- Слой 3: Текст поверх всего (всегда читаем)
    love.graphics.print("HP: 100", 10, 10)
    drawUIText()
end
```

### Преимущества

- **Текст всегда читаем** — не проходит через AI стилизацию
- **Гибкость** — можно стилизовать слои по-разному
- **Производительность** — стилизация offline, в игре только композиция
- **Итерации** — можно менять стиль слоёв независимо

### Рекомендуемый пайплайн для ассетов

```bash
# 1. Экспорт слоёв из игры (скриншоты без UI/текста)
# 2. Batch-стилизация игрового контента
for img in game_layer_*.png; do
    python ai_style_transfer.py "$img" "styled_$img" --model gemini-pro --style deceiver
    python pipeline.py "styled_$img" "final_$img" --skip-ai --palette 32 --dither
done

# 3. Опционально: стилизация UI панелей
# 4. Сборка в игре через слои
```

## Выводы

1. **Gemini Pro** — лучший выбор для style transfer (сохраняет композицию, понимает промпты)
2. **Комбинированный пайплайн** даёт лучший результат чем только AI или только алгоритм
3. **UI маска** критична для сохранения читаемости интерфейса (или разделение на слои)
4. **LoRA** полезны для усиления конкретного стиля, но требуют настройки
5. **Разделение на слои** — лучший подход для продакшена (текст всегда читаем)
