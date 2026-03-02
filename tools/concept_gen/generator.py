"""
Concept Generator

Генерация концептов по референсам через AIML API.
Использует GPT-4o для анализа референсов и Flux/DALL-E для генерации.

Требует: AIMLAPI_KEY в переменных окружения или .env файле.
"""

import base64
import json
import os
import sys
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
import requests

logger = logging.getLogger("concept_gen")

# Настройки API
AIMLAPI_BASE = "https://api.aimlapi.com"
VISION_MODEL = "gpt-4o"  # Для анализа референсов
IMAGE_MODEL = "flux/schnell"  # Для генерации (быстрый)
# Альтернативы: "dall-e-3", "flux-pro", "stable-diffusion-xl"


@dataclass
class ConceptResult:
    """Результат генерации концепта."""
    success: bool
    image_path: Optional[str] = None
    image_url: Optional[str] = None
    prompt_used: str = ""
    ref_analysis: str = ""
    error: Optional[str] = None
    tokens_used: int = 0


def _get_api_key() -> Optional[str]:
    """Получить API ключ из окружения или .env."""
    key = os.environ.get("AIMLAPI_KEY")
    if key:
        return key

    # Попробовать загрузить из .env
    env_paths = [
        Path(__file__).parent.parent.parent / "config" / ".env",
        Path.cwd() / ".env"
    ]

    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.startswith("AIMLAPI_KEY="):
                        return line.split("=", 1)[1].strip().strip('"\'')

    return None


def _load_image_base64(image_path: str) -> tuple[str, str]:
    """Загрузить изображение и конвертировать в base64."""
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

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


def analyze_reference(
    image_path: str,
    context: str = "",
    api_key: Optional[str] = None
) -> dict:
    """
    Проанализировать референс через GPT-4o Vision.

    Args:
        image_path: Путь к изображению референса
        context: Дополнительный контекст (что это за игра, стиль и т.д.)
        api_key: API ключ (опционально, иначе из окружения)

    Returns:
        dict с полями: description, style, colors, elements, mood
    """
    key = api_key or _get_api_key()
    if not key:
        return {"error": "AIMLAPI_KEY не найден"}

    try:
        image_data, media_type = _load_image_base64(image_path)
    except FileNotFoundError as e:
        return {"error": str(e)}

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    system_prompt = """Ты — эксперт по игровому арту и UI/UX дизайну.
Проанализируй изображение и опиши его для последующей генерации похожих концептов.

Ответь в JSON формате:
{
    "description": "Краткое описание что изображено",
    "style": "Художественный стиль (pixel art, flat, realistic, etc.)",
    "colors": ["основные цвета в hex или названиях"],
    "elements": ["ключевые визуальные элементы"],
    "mood": "Настроение/атмосфера",
    "composition": "Описание композиции",
    "suggestions": ["идеи для вариаций"]
}"""

    user_prompt = "Проанализируй это изображение для генерации концептов."
    if context:
        user_prompt += f"\n\nКонтекст: {context}"

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_data}"
                        }
                    },
                    {"type": "text", "text": user_prompt}
                ]
            }
        ],
        "max_tokens": 1024
    }

    try:
        response = requests.post(
            f"{AIMLAPI_BASE}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()

        text = data["choices"][0]["message"]["content"]

        # Парсить JSON из ответа
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])

        return {"description": text, "error": "JSON не распарсился"}

    except requests.RequestException as e:
        return {"error": f"API error: {e}"}
    except (KeyError, json.JSONDecodeError) as e:
        return {"error": f"Parse error: {e}"}


def generate_image(
    prompt: str,
    output_path: Optional[str] = None,
    model: str = IMAGE_MODEL,
    size: str = "1024x1024",
    api_key: Optional[str] = None
) -> ConceptResult:
    """
    Сгенерировать изображение по промпту.

    Args:
        prompt: Текстовое описание для генерации
        output_path: Куда сохранить (опционально)
        model: Модель для генерации
        size: Размер изображения
        api_key: API ключ

    Returns:
        ConceptResult с результатом
    """
    key = api_key or _get_api_key()
    if not key:
        return ConceptResult(success=False, error="AIMLAPI_KEY не найден")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size
    }

    try:
        response = requests.post(
            f"{AIMLAPI_BASE}/v1/images/generations",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        data = response.json()

        # Получить URL изображения
        image_url = data["data"][0].get("url")
        if not image_url:
            # Попробовать b64_json
            b64 = data["data"][0].get("b64_json")
            if b64 and output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(b64))
                return ConceptResult(
                    success=True,
                    image_path=output_path,
                    prompt_used=prompt
                )

        # Скачать по URL если нужно сохранить
        saved_path = None
        if output_path and image_url:
            img_response = requests.get(image_url, timeout=60)
            img_response.raise_for_status()
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(img_response.content)
            saved_path = output_path

        return ConceptResult(
            success=True,
            image_path=saved_path,
            image_url=image_url,
            prompt_used=prompt
        )

    except requests.RequestException as e:
        return ConceptResult(success=False, error=f"API error: {e}", prompt_used=prompt)


def generate_concepts(
    refs_dir: str,
    output_dir: str,
    base_prompt: str = "",
    context: str = "",
    num_variants: int = 3,
    model: str = IMAGE_MODEL,
    api_key: Optional[str] = None
) -> List[ConceptResult]:
    """
    Сгенерировать концепты на основе референсов.

    Args:
        refs_dir: Папка с референсами
        output_dir: Папка для вывода
        base_prompt: Базовый промпт (дополняет анализ референсов)
        context: Контекст проекта (название игры, жанр и т.д.)
        num_variants: Количество вариантов на каждый референс
        model: Модель для генерации
        api_key: API ключ

    Returns:
        Список ConceptResult
    """
    refs_path = Path(refs_dir)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not refs_path.exists():
        return [ConceptResult(success=False, error=f"Папка референсов не найдена: {refs_dir}")]

    # Найти все изображения
    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    ref_images = [f for f in refs_path.iterdir() if f.suffix.lower() in image_exts]

    if not ref_images:
        return [ConceptResult(success=False, error=f"Нет изображений в {refs_dir}")]

    results = []

    for ref_img in ref_images:
        logger.info(f"Анализирую референс: {ref_img.name}")

        # Анализ референса
        analysis = analyze_reference(str(ref_img), context, api_key)

        if "error" in analysis:
            results.append(ConceptResult(
                success=False,
                error=f"Ошибка анализа {ref_img.name}: {analysis['error']}"
            ))
            continue

        # Формируем промпт для генерации
        ref_description = analysis.get("description", "")
        ref_style = analysis.get("style", "")
        ref_mood = analysis.get("mood", "")
        ref_colors = ", ".join(analysis.get("colors", []))
        suggestions = analysis.get("suggestions", [])

        base = f"{ref_style} style, {ref_mood} mood"
        if ref_colors:
            base += f", color palette: {ref_colors}"
        if base_prompt:
            base = f"{base_prompt}, {base}"

        # Генерируем варианты
        for i in range(num_variants):
            variant_prompt = base

            # Добавить suggestion если есть
            if suggestions and i < len(suggestions):
                variant_prompt += f", {suggestions[i]}"
            elif i > 0:
                variant_prompt += f", variation {i + 1}"

            output_name = f"{ref_img.stem}_concept_{i + 1}.png"
            output_file = out_path / output_name

            logger.info(f"Генерирую: {output_name}")
            logger.debug(f"Промпт: {variant_prompt}")

            result = generate_image(
                prompt=variant_prompt,
                output_path=str(output_file),
                model=model,
                api_key=api_key
            )

            result.ref_analysis = json.dumps(analysis, ensure_ascii=False, indent=2)
            results.append(result)

            # Небольшая пауза между запросами
            time.sleep(1)

    return results


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Генерация концептов по референсам через AIML API",
        prog="ptero-tool concept"
    )

    subparsers = parser.add_subparsers(dest="command", help="Команды")

    # Команда analyze
    analyze_parser = subparsers.add_parser("analyze", help="Анализ референса")
    analyze_parser.add_argument("image", help="Путь к изображению")
    analyze_parser.add_argument("-c", "--context", default="", help="Контекст проекта")
    analyze_parser.add_argument("--json", action="store_true", help="JSON вывод")

    # Команда generate
    gen_parser = subparsers.add_parser("generate", help="Генерация концептов")
    gen_parser.add_argument("refs", help="Папка с референсами")
    gen_parser.add_argument("output", help="Папка для вывода")
    gen_parser.add_argument("-p", "--prompt", default="", help="Базовый промпт")
    gen_parser.add_argument("-c", "--context", default="", help="Контекст проекта")
    gen_parser.add_argument("-n", "--num", type=int, default=3, help="Вариантов на референс")
    gen_parser.add_argument("-m", "--model", default=IMAGE_MODEL, help="Модель генерации")

    # Команда quick — быстрая генерация по одному референсу
    quick_parser = subparsers.add_parser("quick", help="Быстрая генерация по одному референсу")
    quick_parser.add_argument("image", help="Референс")
    quick_parser.add_argument("output", help="Выходной файл")
    quick_parser.add_argument("-p", "--prompt", default="", help="Дополнительный промпт")

    args = parser.parse_args()

    if args.command == "analyze":
        result = analyze_reference(args.image, args.context)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if "error" in result:
                print(f"Error: {result['error']}", file=sys.stderr)
                return 1
            print(f"Description: {result.get('description', 'N/A')}")
            print(f"Style: {result.get('style', 'N/A')}")
            print(f"Mood: {result.get('mood', 'N/A')}")
            print(f"Colors: {', '.join(result.get('colors', []))}")
            print(f"Elements: {', '.join(result.get('elements', []))}")
            if result.get("suggestions"):
                print(f"Suggestions: {', '.join(result['suggestions'])}")

    elif args.command == "generate":
        results = generate_concepts(
            refs_dir=args.refs,
            output_dir=args.output,
            base_prompt=args.prompt,
            context=args.context,
            num_variants=args.num,
            model=args.model
        )

        success = sum(1 for r in results if r.success)
        failed = len(results) - success

        print(f"\nГотово: {success} успешно, {failed} ошибок")

        for r in results:
            if r.success:
                print(f"  [OK] {r.image_path or r.image_url}")
            else:
                print(f"  [FAIL] {r.error}")

        return 0 if failed == 0 else 1

    elif args.command == "quick":
        # Анализ
        print(f"Анализирую: {args.image}")
        analysis = analyze_reference(args.image, args.prompt)

        if "error" in analysis:
            print(f"Error: {analysis['error']}", file=sys.stderr)
            return 1

        # Формируем промпт
        style = analysis.get("style", "digital art")
        mood = analysis.get("mood", "")
        desc = analysis.get("description", "")

        prompt = f"{style} style"
        if mood:
            prompt += f", {mood} mood"
        if args.prompt:
            prompt = f"{args.prompt}, {prompt}"
        else:
            prompt = f"{desc}, {prompt}"

        print(f"Промпт: {prompt[:100]}...")

        # Генерация
        print("Генерирую...")
        result = generate_image(prompt, args.output)

        if result.success:
            print(f"Готово: {result.image_path or result.image_url}")
            return 0
        else:
            print(f"Error: {result.error}", file=sys.stderr)
            return 1

    else:
        parser.print_help()
        return 0

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
