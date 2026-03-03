"""
AI Style Transfer через AIML API

Использует img2img модели (Flux, Gemini) для стилизации изображений.
Поддерживает пресеты стилей (Deceiver/Loop Hero, etc.)

Требует: AIMLAPI_KEY в переменных окружения или config/.env
"""

import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any
import requests

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

AIMLAPI_BASE = "https://api.aimlapi.com"

# Доступные img2img модели
MODELS = {
    "qwen-edit": "alibaba/qwen-image-edit",  # Одно изображение
    "flux-dev": "flux/dev/image-to-image",   # Одно изображение
    "flux-kontext": "flux/kontext-pro/image-to-image",  # Multi-reference!
    "flux-kontext-max": "flux/kontext-max/image-to-image",  # Multi-reference premium
    "flux-edit": "blackforestlabs/flux-2-edit",
    "flux-pro-edit": "blackforestlabs/flux-2-pro-edit",  # Premium edit
    "flux-lora": "blackforestlabs/flux-2-lora",  # LoRA support (text2img)
    "flux-lora-edit": "blackforestlabs/flux-2-lora-edit",  # LoRA support (img2img)
    "gemini-flash": "google/gemini-2.5-flash-image-edit",
    "gemini-pro": "google/gemini-3-pro-image-preview-edit",  # Новый Gemini
    "reve-edit": "reve/edit-image",
    "reve-remix": "reve/remix-edit-image",  # Style remix
    "seedream": "bytedance/seedream-v4-edit",  # ByteDance
}

# Модели с поддержкой нескольких изображений
MULTI_REF_MODELS = {"flux-kontext", "flux-kontext-max", "gemini-pro", "gemini-flash"}

# Модели с поддержкой LoRA
LORA_MODELS = {"flux-lora", "flux-lora-edit"}

# Известные LoRA для pixel art (HuggingFace - без токена)
LORA_PRESETS = {
    "retro-pixel": {
        "name": "Retro Pixel Flux LoRA",
        "url": "prithivMLmods/Retro-Pixel-Flux-LoRA",  # HF repo ID
        "trigger": "Retro Pixel",
        "scale": 0.9,
    },
    "modern-pixel": {
        "name": "Modern Pixel Art Flux",
        "url": "UmeAiRT/FLUX.1-dev-LoRA-Modern_Pixel_art",  # HF repo ID
        "trigger": "modern pixel art",
        "scale": 0.85,
    },
    "pixel-art-xl": {
        "name": "Pixel Art XL (SDXL)",
        "url": "nerijs/pixel-art-xl",  # HF repo ID
        "trigger": "pixel art",
        "scale": 1.0,
    },
}

DEFAULT_MODEL = "qwen-edit"  # По умолчанию модель с поддержкой base64

# ============================================================================
# ПРЕСЕТЫ СТИЛЕЙ
# ============================================================================

STYLE_PRESETS = {
    "deceiver": {
        "name": "Deceiver / Loop Hero",
        "prompt": """Transform this image into the pixel art style of Loop Hero game by Deceiver (Dmitry Karimov).
Key characteristics:
- Muted, rusty color palette with browns, burgundy, dark greens
- Limited color count (16-32 colors)
- Dark, gloomy atmosphere
- Desaturated tones
- Pixel art aesthetic with visible pixels
- Medieval dark fantasy mood
Maintain the original composition and elements but apply this distinctive visual style.""",
        "negative_prompt": "bright colors, neon, modern, clean, sharp, high saturation, cartoon, anime",
        "strength": 0.65,
    },

    "lospec-fantasy": {
        "name": "Lospec Dark Fantasy",
        "prompt": """Convert to dark fantasy pixel art style:
- Limited 32-color palette
- Earthy tones: browns, dark greens, deep reds
- Medieval atmosphere
- Textured pixels with dithering effect
- Moody lighting with strong shadows
Keep the original layout and objects.""",
        "negative_prompt": "bright, colorful, modern, 3D, realistic",
        "strength": 0.7,
    },

    "8bit-nes": {
        "name": "8-bit NES Style",
        "prompt": """Transform into classic 8-bit NES pixel art:
- Strict 4-color per sprite limitation feel
- Sharp pixels, no anti-aliasing
- Limited palette (~25 colors total)
- Retro game aesthetic from 1985-1990
- Simple shapes, iconic readability
Preserve the scene composition.""",
        "negative_prompt": "modern, detailed, gradient, soft, smooth",
        "strength": 0.75,
    },

    "gba-advance": {
        "name": "GBA Style",
        "prompt": """Convert to Game Boy Advance pixel art style:
- 15-bit color depth feel
- Vibrant but slightly muted colors
- Clean pixel art with subtle dithering
- 2000s handheld game aesthetic
- Good readability and contrast
Maintain original composition.""",
        "negative_prompt": "dark, gloomy, realistic, 3D",
        "strength": 0.6,
    },

    "custom": {
        "name": "Custom Prompt",
        "prompt": "",
        "negative_prompt": "",
        "strength": 0.65,
    }
}


@dataclass
class StyleTransferResult:
    """Результат AI стилизации."""
    success: bool
    output_path: Optional[str] = None
    output_url: Optional[str] = None
    model_used: str = ""
    prompt_used: str = ""
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


def _get_api_key() -> Optional[str]:
    """Получить API ключ."""
    key = os.environ.get("AIMLAPI_KEY")
    if key:
        return key

    env_paths = [
        Path(__file__).parent.parent.parent / "config" / ".env",
        Path.cwd() / ".env",
        Path.cwd() / "config" / ".env",
    ]

    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("AIMLAPI_KEY="):
                        return line.split("=", 1)[1].strip().strip('"\'')

    return None


def _validate_image_file(path: str) -> tuple[bool, Optional[str]]:
    """
    Проверить, что файл является валидным изображением.

    Returns:
        (True, None) если валидно, (False, error_message) если нет
    """
    file_path = Path(path)

    if not file_path.exists():
        return False, f"Файл не существует: {path}"

    # Проверка минимального размера (PNG header минимум 67 байт)
    file_size = file_path.stat().st_size
    if file_size < 50:
        return False, f"Файл слишком мал ({file_size} байт), вероятно битый: {path}"

    # Попытка открыть и проверить через PIL
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            _ = img.size
        return True, None
    except Exception as e:
        return False, f"Не удалось открыть изображение: {e}"


def _load_image_base64(image_path: str) -> tuple[str, str]:
    """Загрузить изображение в base64."""
    path = Path(image_path)

    # Валидация перед загрузкой
    is_valid, error = _validate_image_file(image_path)
    if not is_valid:
        raise ValueError(error)

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    suffix = path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    media_type = media_types.get(suffix, "image/png")

    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")

    return data, media_type


def _upload_to_temp_hosting(image_path: str) -> Optional[str]:
    """Загрузить изображение на временный хостинг (с fallback)."""

    # Список хостингов для попытки (в порядке приоритета)
    hostings = [
        ("catbox.moe", _upload_to_catbox),
        ("litterbox", _upload_to_litterbox),
        ("0x0.st", _upload_to_0x0),
    ]

    for name, upload_fn in hostings:
        try:
            url = upload_fn(image_path)
            if url:
                return url
        except Exception as e:
            print(f"  {name} failed: {e}")
            continue

    return None


def _upload_to_catbox(image_path: str) -> Optional[str]:
    """Загрузить на catbox.moe (постоянный хостинг)."""
    with open(image_path, "rb") as f:
        response = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": f},
            timeout=60
        )
    if response.status_code == 200 and response.text.startswith("http"):
        return response.text.strip()
    return None


def _upload_to_litterbox(image_path: str) -> Optional[str]:
    """Загрузить на litterbox.catbox.moe (временный, 1 час)."""
    with open(image_path, "rb") as f:
        response = requests.post(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data={"reqtype": "fileupload", "time": "1h"},
            files={"fileToUpload": f},
            timeout=60
        )
    if response.status_code == 200 and response.text.startswith("http"):
        return response.text.strip()
    return None


def _upload_to_0x0(image_path: str) -> Optional[str]:
    """Загрузить на 0x0.st."""
    headers = {"User-Agent": "curl/8.0.0"}
    with open(image_path, "rb") as f:
        response = requests.post(
            "https://0x0.st",
            files={"file": f},
            headers=headers,
            timeout=30
        )
    if response.status_code == 200:
        return response.text.strip()
    return None


def _save_image_from_response(
    response_data: Dict,
    output_path: str
) -> Optional[str]:
    """Сохранить изображение из ответа API."""
    try:
        # Разные форматы ответа
        image_data = None
        image_url = None

        # Формат OpenAI-like
        if "data" in response_data and response_data["data"]:
            item = response_data["data"][0]
            # Проверяем значение, а не только наличие ключа (может быть null)
            if item.get("b64_json"):
                image_data = item["b64_json"]
            if item.get("url"):
                image_url = item["url"]

        # Формат с images
        if "images" in response_data and response_data["images"]:
            item = response_data["images"][0]
            if isinstance(item, str):
                if item.startswith("http"):
                    image_url = item
                else:
                    image_data = item
            elif isinstance(item, dict):
                image_data = image_data or item.get("b64_json") or item.get("base64")
                image_url = image_url or item.get("url")

        # Формат с output
        elif "output" in response_data:
            output = response_data["output"]
            if isinstance(output, str):
                if output.startswith("http"):
                    image_url = output
                else:
                    image_data = output
            elif isinstance(output, list) and output:
                image_url = output[0] if output[0].startswith("http") else None
                image_data = output[0] if not output[0].startswith("http") else None

        # Формат Flux/Replicate
        elif "image" in response_data:
            img = response_data["image"]
            if isinstance(img, str):
                if img.startswith("http"):
                    image_url = img
                else:
                    image_data = img

        # Сохранение
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if image_data:
            # Убираем data:image prefix если есть
            if "base64," in image_data:
                image_data = image_data.split("base64,")[1]
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(image_data))
            return output_path

        elif image_url:
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path

        return None

    except Exception as e:
        print(f"Error saving image: {e}")
        return None


def ai_style_transfer(
    input_path: str,
    output_path: str,
    style: str = "deceiver",
    custom_prompt: str = "",
    model: str = DEFAULT_MODEL,
    strength: float = 0.65,
    style_reference: Optional[str] = None,
    lora_url: Optional[str] = None,
    lora_preset: Optional[str] = None,
    lora_scale: float = 0.9,
    api_key: Optional[str] = None,
    debug: bool = False
) -> StyleTransferResult:
    """
    Применить AI стилизацию к изображению.

    Args:
        input_path: Путь к входному изображению
        output_path: Путь для сохранения результата
        style: Пресет стиля из STYLE_PRESETS или "custom"
        custom_prompt: Кастомный промпт (используется если style="custom")
        model: Модель для генерации (ключ из MODELS)
        strength: Сила трансформации (0.0-1.0)
        style_reference: Путь к референсу стиля (для flux-kontext)
        lora_url: URL LoRA модели (для flux-lora/flux-lora-edit)
        lora_preset: Пресет LoRA из LORA_PRESETS (loop-hero, pixel-art-xl)
        lora_scale: Сила LoRA (0.1-2.0, рекомендуется 0.3-1.2)
        api_key: API ключ (опционально)
        debug: Выводить отладочную информацию

    Returns:
        StyleTransferResult
    """
    key = api_key or _get_api_key()
    if not key:
        return StyleTransferResult(
            success=False,
            error="AIMLAPI_KEY не найден. Установите переменную окружения или добавьте в config/.env"
        )

    # Загрузка изображения
    try:
        image_data, media_type = _load_image_base64(input_path)
    except (FileNotFoundError, ValueError) as e:
        return StyleTransferResult(success=False, error=str(e))

    # Получение пресета стиля
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["deceiver"])
    prompt = custom_prompt if style == "custom" and custom_prompt else preset["prompt"]
    negative_prompt = preset.get("negative_prompt", "")

    if not strength:
        strength = preset.get("strength", 0.65)

    # Модель
    model_id = MODELS.get(model, MODELS[DEFAULT_MODEL])

    # Используем data URL (base64) напрямую — не нужен внешний хостинг!
    image_url = f"data:{media_type};base64,{image_data}"
    style_ref_url = None

    if debug:
        print(f"Using data URL (base64), size: {len(image_data) // 1024}KB")

    # Загружаем style reference если указан
    if style_reference and model in MULTI_REF_MODELS:
        if Path(style_reference).exists():
            if debug:
                print(f"Loading style reference: {style_reference}")
            try:
                ref_data, ref_type = _load_image_base64(style_reference)
                style_ref_url = f"data:{ref_type};base64,{ref_data}"
                if debug:
                    print(f"Style ref loaded: {len(ref_data) // 1024}KB")
            except Exception as e:
                if debug:
                    print(f"Failed to load style ref: {e}")
        else:
            if debug:
                print(f"Style reference not found: {style_reference}")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    # Формируем запрос (формат зависит от модели)

    if "qwen" in model_id.lower():
        # Qwen требует URL изображения
        payload = {
            "model": model_id,
            "prompt": prompt,
            "image": image_url,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

    elif "flux" in model_id.lower():
        # Flux модели

        # LoRA модели (flux-lora, flux-lora-edit)
        if model in LORA_MODELS:
            # Определяем LoRA URL и trigger
            final_lora_url = lora_url
            lora_trigger = ""
            final_lora_scale = lora_scale

            if lora_preset and lora_preset in LORA_PRESETS:
                preset_data = LORA_PRESETS[lora_preset]
                final_lora_url = preset_data["url"]
                lora_trigger = preset_data.get("trigger", "")
                final_lora_scale = preset_data.get("scale", lora_scale)
                if debug:
                    print(f"Using LoRA preset: {preset_data['name']}")

            if not final_lora_url:
                return StyleTransferResult(
                    success=False,
                    error="LoRA URL required for flux-lora models. Use --lora-url or --lora-preset"
                )

            # Добавляем trigger word к промпту
            final_prompt = f"{lora_trigger}, {prompt}" if lora_trigger else prompt

            payload = {
                "model": model_id,
                "prompt": final_prompt,
                "loras": [{"path": final_lora_url, "scale": final_lora_scale}],
                "num_outputs": 1,
                "output_format": "png",
            }

            # Для img2img добавляем изображение (flux-lora-edit требует image_urls массив)
            if "edit" in model_id.lower() or "image-to-image" in model_id.lower():
                payload["image_urls"] = [image_url]  # Массив URL
                payload["strength"] = strength

            if debug:
                print(f"LoRA mode: {final_lora_url}")
                print(f"LoRA scale: {final_lora_scale}")
                print(f"Trigger: {lora_trigger}")

        # Kontext multi-reference
        elif style_ref_url and "kontext" in model_id.lower():
            style_prompt = f"""Use the FIRST image as a style reference ONLY.
Transform the SECOND image to match the pixel art style, color palette, and atmosphere of the first image.
Keep all content, layout and composition from the second image intact.
Apply: muted rusty colors, pixel art aesthetic, dark fantasy mood.
Do NOT combine or merge the images. Only transfer the visual style to the second image."""
            payload = {
                "model": model_id,
                "prompt": style_prompt,
                "image_url": [style_ref_url, image_url],
            }
            if debug:
                print(f"Multi-reference mode: 2 images (style transfer)")

        # Обычный flux img2img
        else:
            # flux-2-edit и flux-2-pro-edit требуют image_urls массив
            if "edit" in model_id.lower() and "lora" not in model_id.lower():
                payload = {
                    "model": model_id,
                    "prompt": prompt,
                    "image_urls": [image_url],
                    "strength": strength,
                    "num_outputs": 1,
                    "output_format": "png",
                }
            else:
                payload = {
                    "model": model_id,
                    "prompt": prompt,
                    "image_url": image_url,
                    "strength": strength,
                    "num_outputs": 1,
                    "output_format": "png",
                }

        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

    elif "gemini" in model_id.lower():
        # Gemini требует image_urls массив (поддерживает до 14 изображений)
        img_source = image_url if image_url else f"data:{media_type};base64,{image_data}"

        # Multi-reference: исходник + референс стиля
        if style_ref_url:
            style_prompt = f"""Transform the FIRST image to match the pixel art style of the SECOND image.
Keep all content, layout and composition from the first image.
Apply the color palette, texture, and atmosphere from the second image.
The second image is a style reference from Loop Hero game - use its muted colors, pixel art aesthetic, and dark fantasy mood.
Do NOT merge the images. Only transfer the visual style."""
            payload = {
                "model": model_id,
                "prompt": style_prompt,
                "image_urls": [img_source, style_ref_url],
            }
            if debug:
                print("Gemini multi-reference mode: source + style ref")
        else:
            payload = {
                "model": model_id,
                "prompt": prompt,
                "image_urls": [img_source],
            }

    elif "reve" in model_id.lower():
        # Reve требует image_urls массив
        payload = {
            "model": model_id,
            "prompt": prompt,
            "image_urls": [image_url],
            "strength": strength,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

    elif "seedream" in model_id.lower():
        # ByteDance Seedream
        payload = {
            "model": model_id,
            "prompt": prompt,
            "image_url": image_url,
            "strength": strength,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

    else:
        # Общий формат
        image_url = f"data:{media_type};base64,{image_data}"
        payload = {
            "model": model_id,
            "prompt": prompt,
            "image_url": image_url,
            "strength": strength,
            "n": 1,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

    if debug:
        print(f"Model: {model_id}")
        print(f"Prompt: {prompt[:100]}...")
        print(f"Strength: {strength}")

    # API запрос
    try:
        response = requests.post(
            f"{AIMLAPI_BASE}/v1/images/generations",
            headers=headers,
            json=payload,
            timeout=180  # img2img может быть медленным
        )

        if debug:
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text[:500]}")

        response.raise_for_status()
        data = response.json()

        # Сохранение результата
        saved_path = _save_image_from_response(data, output_path)

        if saved_path:
            return StyleTransferResult(
                success=True,
                output_path=saved_path,
                model_used=model_id,
                prompt_used=prompt,
                raw_response=data if debug else None
            )
        else:
            return StyleTransferResult(
                success=False,
                error="Не удалось извлечь изображение из ответа API",
                model_used=model_id,
                prompt_used=prompt,
                raw_response=data
            )

    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = e.response.json()
        except:
            error_detail = e.response.text[:500]
        return StyleTransferResult(
            success=False,
            error=f"API error {e.response.status_code}: {error_detail}",
            model_used=model_id,
            prompt_used=prompt
        )
    except requests.exceptions.RequestException as e:
        return StyleTransferResult(
            success=False,
            error=f"Request error: {e}",
            model_used=model_id,
            prompt_used=prompt
        )


def list_styles() -> Dict[str, str]:
    """Вернуть список доступных стилей."""
    return {k: v["name"] for k, v in STYLE_PRESETS.items()}


def list_models() -> Dict[str, str]:
    """Вернуть список доступных моделей."""
    return MODELS.copy()


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="AI Style Transfer через AIML API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s input.png output.png --style deceiver
  %(prog)s input.png output.png --style 8bit-nes --model flux-kontext
  %(prog)s input.png output.png --style custom --prompt "dark fantasy pixel art"
  %(prog)s --list-styles
  %(prog)s --list-models
        """
    )

    parser.add_argument("input", nargs='?', help="Входное изображение")
    parser.add_argument("output", nargs='?', help="Выходное изображение")

    parser.add_argument("--style", "-s", default="deceiver",
                        help=f"Пресет стиля: {', '.join(STYLE_PRESETS.keys())}")
    parser.add_argument("--prompt", "-p", default="",
                        help="Кастомный промпт (для style=custom)")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                        help=f"Модель: {', '.join(MODELS.keys())}")
    parser.add_argument("--strength", type=float, default=0.65,
                        help="Сила трансформации 0.0-1.0 (default: 0.65)")
    parser.add_argument("--style-ref", "-r", default=None,
                        help="Путь к референсу стиля (для flux-kontext)")

    # LoRA параметры
    parser.add_argument("--lora-url", default=None,
                        help="URL LoRA модели (для flux-lora/flux-lora-edit)")
    parser.add_argument("--lora-preset", default=None,
                        choices=list(LORA_PRESETS.keys()),
                        help=f"Пресет LoRA: {', '.join(LORA_PRESETS.keys())}")
    parser.add_argument("--lora-scale", type=float, default=0.9,
                        help="Сила LoRA 0.1-2.0 (default: 0.9)")

    parser.add_argument("--list-styles", action="store_true",
                        help="Показать доступные стили")
    parser.add_argument("--list-models", action="store_true",
                        help="Показать доступные модели")
    parser.add_argument("--list-loras", action="store_true",
                        help="Показать доступные LoRA пресеты")
    parser.add_argument("--debug", action="store_true",
                        help="Отладочный вывод")
    parser.add_argument("--json", action="store_true",
                        help="JSON вывод")

    args = parser.parse_args()

    if args.list_styles:
        print("Доступные стили:")
        for key, name in list_styles().items():
            preset = STYLE_PRESETS[key]
            print(f"  {key:20} - {name}")
            if key != "custom":
                print(f"                       Strength: {preset.get('strength', 0.65)}")
        return 0

    if args.list_models:
        print("Доступные модели:")
        for key, model_id in list_models().items():
            default_mark = " (default)" if key == DEFAULT_MODEL else ""
            lora_mark = " [LoRA]" if key in LORA_MODELS else ""
            multi_mark = " [multi-ref]" if key in MULTI_REF_MODELS else ""
            print(f"  {key:20} - {model_id}{default_mark}{lora_mark}{multi_mark}")
        return 0

    if args.list_loras:
        print("Доступные LoRA пресеты:")
        for key, data in LORA_PRESETS.items():
            print(f"  {key:20} - {data['name']}")
            print(f"                       Trigger: {data.get('trigger', 'none')}")
            print(f"                       Scale: {data.get('scale', 0.9)}")
        return 0

    if not args.input:
        parser.print_help()
        return 1

    if not args.output:
        inp = Path(args.input)
        args.output = str(inp.parent / f"{inp.stem}_{args.style}.png")

    print(f"Стилизация: {args.input}")
    print(f"Стиль: {args.style}")
    print(f"Модель: {args.model}")
    print(f"Сила: {args.strength}")
    print("Обработка... (может занять 30-60 секунд)")

    result = ai_style_transfer(
        input_path=args.input,
        output_path=args.output,
        style=args.style,
        custom_prompt=args.prompt,
        model=args.model,
        strength=args.strength,
        style_reference=args.style_ref,
        lora_url=args.lora_url,
        lora_preset=args.lora_preset,
        lora_scale=args.lora_scale,
        debug=args.debug
    )

    if args.json:
        output = {
            "success": result.success,
            "output_path": result.output_path,
            "model_used": result.model_used,
            "error": result.error
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if result.success:
            print(f"\nГотово: {result.output_path}")
            print(f"Модель: {result.model_used}")
        else:
            print(f"\nОшибка: {result.error}")
            if result.raw_response:
                print(f"Response: {json.dumps(result.raw_response, indent=2)[:500]}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
