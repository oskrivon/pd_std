# Tool: concept-gen

Генерация концептов по референсам через AIML API.

## Требования

- AIML API ключ: [aimlapi.com](https://aimlapi.com)
- Переменная `AIMLAPI_KEY` в окружении или `config/.env`

## CLI

```bash
# Анализ референса
ptero-tool concept analyze <image> [--context "..."] [--json]

# Генерация по папке референсов
ptero-tool concept generate <refs_dir> <output_dir> [options]

# Быстрая генерация по одному референсу
ptero-tool concept quick <image> <output.png> [--prompt "..."]
```

### Опции generate

| Опция | Описание | По умолчанию |
|-------|----------|--------------|
| `refs` | Папка с референсами | — |
| `output` | Папка для вывода | — |
| `--prompt`, `-p` | Базовый промпт | — |
| `--context`, `-c` | Контекст проекта | — |
| `--num`, `-n` | Вариантов на референс | 3 |
| `--model`, `-m` | Модель генерации | flux/schnell |

## Примеры

```bash
# Анализ скриншота игры
ptero-tool concept analyze screenshot.png --context "roguelike game UI"

# Генерация концептов UI
ptero-tool concept generate refs/ output/ \
    --prompt "game inventory screen" \
    --context "pixel art roguelike" \
    --num 5

# Быстрый концепт
ptero-tool concept quick ref.png concept.png --prompt "dark fantasy style"
```

## Python API

```python
from studio.tools.concept_gen import generate_concepts, analyze_reference

# Анализ референса
analysis = analyze_reference(
    image_path="ref.png",
    context="roguelike game"
)
print(analysis["style"])       # "pixel art"
print(analysis["colors"])      # ["#2a2a3a", "#4a9"]
print(analysis["suggestions"]) # ["add glow effects", ...]

# Генерация концептов
results = generate_concepts(
    refs_dir="refs/",
    output_dir="output/",
    base_prompt="inventory UI",
    context="roguelike game",
    num_variants=3
)

for r in results:
    if r.success:
        print(f"OK: {r.image_path}")
    else:
        print(f"Error: {r.error}")
```

## Модели генерации

| Модель | Скорость | Качество | Стоимость |
|--------|----------|----------|-----------|
| `flux/schnell` | Быстрый | Хорошее | Низкая |
| `flux-pro` | Средний | Высокое | Средняя |
| `dall-e-3` | Средний | Высокое | Высокая |
| `stable-diffusion-xl` | Быстрый | Среднее | Низкая |

## Конфигурация

В `studio/config/.env`:
```bash
AIMLAPI_KEY=your-api-key-here
```

Или через переменную окружения:
```bash
export AIMLAPI_KEY=your-api-key-here
```

## Workflow

1. **Анализ** — GPT-4o Vision анализирует референс
2. **Промпт** — Формируется на основе стиля, цветов, настроения
3. **Генерация** — Flux/DALL-E создаёт варианты
4. **Сохранение** — Результаты в output папке

## Результат анализа

```json
{
    "description": "Game inventory screen with grid layout",
    "style": "pixel art",
    "colors": ["#2a2a3a", "#4a9", "#f80"],
    "elements": ["inventory grid", "item icons", "stats panel"],
    "mood": "dark fantasy",
    "composition": "centered UI with side panels",
    "suggestions": ["add glow effects", "try isometric view"]
}
```
