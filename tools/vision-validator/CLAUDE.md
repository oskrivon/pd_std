# Tool: vision-validator

Проверка скриншота через Claude Vision API. Отвечает на вопрос "работает ли это?".

## CLI

```bash
ptero-tool validate <image> --prompt "QUESTION" [options]
```

### Опции

| Опция | Описание | По умолчанию |
|-------|----------|--------------|
| `image` | Путь к изображению (обязательно) | — |
| `--prompt`, `-p` | Вопрос для проверки (обязательно) | — |
| `--model`, `-m` | Модель: haiku, sonnet | haiku |
| `--json` | Вывод в JSON | — |

## Примеры

```bash
# Проверить что игра запустилась
ptero-tool validate game.png --prompt "Is the game running? Any error messages?"

# Проверить UI
ptero-tool validate ui.png --prompt "Are all buttons visible and properly aligned?"

# С JSON выводом для парсинга
ptero-tool validate game.png --prompt "Game working?" --json

# Использовать Sonnet для сложной проверки
ptero-tool validate complex.png --prompt "Describe all UI issues" --model sonnet
```

## Python API

```python
from studio.tools.vision_validator import validate, ValidationResult

# Простая проверка
result = validate(
    image="game.png",
    prompt="Is the game running correctly?"
)

print(result.passed)      # True/False
print(result.explanation) # "The game appears to be running..."
print(result.issues)      # ["Button overlaps text", ...]

# С кастомной моделью
result = validate(
    image="complex.png",
    prompt="List all visual bugs",
    model="sonnet"
)
```

## Возвращает

### CLI
```json
{
  "passed": true,
  "explanation": "The game is running correctly...",
  "issues": [],
  "tokens_used": 450
}
```

### Python
```python
@dataclass
class ValidationResult:
    passed: bool
    explanation: str
    issues: list[str]
    tokens_used: int
```

## Стоимость токенов

| Размер | Токены | Стоимость (Haiku) |
|--------|--------|-------------------|
| 800×600 | ~640 | ~$0.0002 |
| 1280×720 | ~1200 | ~$0.0003 |
| 1920×1080 | ~2700 | ~$0.0007 |

**Рекомендация**: Использовать `--resize 800x600` в capture для экономии.

## Зависимости

- `anthropic` — Claude API
- `Pillow` — чтение изображений
