"""
Vision Validator Tool

Проверка скриншотов через Claude Vision API.
Отвечает на вопросы вида "работает ли игра?", "есть ли ошибки?".

Usage:
    from studio.tools.vision_validator import validate

    result = validate(image="game.png", prompt="Is the game running?")
    if result.passed:
        print("OK")
    else:
        print(f"Issues: {result.issues}")
"""

import base64
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
import logging

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

logger = logging.getLogger("vision_validator")

# Модели для валидации
MODELS = {
    "haiku": "claude-3-5-haiku-20241022",
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514"
}


@dataclass
class ValidationResult:
    """Результат валидации через Vision API."""
    passed: bool
    explanation: str
    issues: List[str] = field(default_factory=list)
    tokens_used: int = 0
    error: Optional[str] = None


def _load_image_base64(image_path: str) -> tuple[str, str]:
    """Загрузить изображение и конвертировать в base64."""
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Определить media type
    suffix = path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp"
    }

    media_type = media_types.get(suffix, "image/png")

    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")

    return data, media_type


def validate(
    image: str,
    prompt: str,
    model: str = "haiku"
) -> ValidationResult:
    """
    Проверить изображение через Claude Vision.

    Args:
        image: Путь к изображению
        prompt: Вопрос для проверки
        model: Модель (haiku, sonnet, opus)

    Returns:
        ValidationResult с результатом проверки
    """
    if not ANTHROPIC_AVAILABLE:
        return ValidationResult(
            passed=False,
            explanation="",
            error="anthropic не установлен. Запустите: pip install anthropic"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return ValidationResult(
            passed=False,
            explanation="",
            error="ANTHROPIC_API_KEY не установлен"
        )

    try:
        image_data, media_type = _load_image_base64(image)
    except FileNotFoundError as e:
        return ValidationResult(
            passed=False,
            explanation="",
            error=str(e)
        )

    # Получить модель
    model_id = MODELS.get(model, MODELS["haiku"])

    # Системный промпт для структурированного ответа
    system_prompt = """You are a visual QA validator for games and applications.
Analyze the screenshot and answer the user's question.

ALWAYS respond in this exact JSON format:
{
    "passed": true/false,
    "explanation": "Brief explanation of what you see",
    "issues": ["issue1", "issue2"] or [] if no issues
}

Rules:
- "passed" should be true if everything looks correct based on the question
- "passed" should be false if there are errors, crashes, or problems
- Be concise but specific about what you observe
- List specific issues if any are found"""

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=model_id,
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )

        # Получить текст ответа
        text = response.content[0].text

        # Посчитать токены
        tokens = response.usage.input_tokens + response.usage.output_tokens

        # Парсить JSON
        try:
            # Найти JSON в ответе
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                data = json.loads(json_str)

                return ValidationResult(
                    passed=data.get("passed", False),
                    explanation=data.get("explanation", ""),
                    issues=data.get("issues", []),
                    tokens_used=tokens
                )
        except json.JSONDecodeError:
            pass

        # Fallback: если JSON не распарсился
        return ValidationResult(
            passed="error" not in text.lower() and "fail" not in text.lower(),
            explanation=text,
            issues=[],
            tokens_used=tokens
        )

    except anthropic.APIError as e:
        return ValidationResult(
            passed=False,
            explanation="",
            error=f"API error: {e}"
        )


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Проверка изображения через Claude Vision",
        prog="ptero-tool validate"
    )

    parser.add_argument(
        "image",
        help="Путь к изображению"
    )
    parser.add_argument(
        "-p", "--prompt",
        required=True,
        help="Вопрос для проверки"
    )
    parser.add_argument(
        "-m", "--model",
        choices=["haiku", "sonnet", "opus"],
        default="haiku",
        help="Модель для использования"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывод в JSON формате"
    )

    args = parser.parse_args()

    result = validate(
        image=args.image,
        prompt=args.prompt,
        model=args.model
    )

    if args.json:
        output = {
            "passed": result.passed,
            "explanation": result.explanation,
            "issues": result.issues,
            "tokens_used": result.tokens_used
        }
        if result.error:
            output["error"] = result.error
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
            return 1

        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.explanation}")

        if result.issues:
            print("\nIssues:")
            for issue in result.issues:
                print(f"  - {issue}")

        print(f"\nTokens: {result.tokens_used}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
