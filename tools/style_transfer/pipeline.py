"""
Deceiver Style Pipeline

Комбинированный подход: AI img2img + алгоритмическая постобработка.

Этапы:
1. AI стилизация (Qwen) — атмосфера, базовые цвета
2. Алгоритмическая обработка — палитра Deceiver, dithering, пиксельность

Использование:
    python pipeline.py input.png output.png [--keep-intermediate]
"""

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from deceiver_style import deceiver_stylize, StyleConfig, DECEIVER_PALETTE
from ai_style_transfer import ai_style_transfer, STYLE_PRESETS
from ui_mask import create_ui_mask, apply_with_mask, visualize_mask, UI_PRESETS


@dataclass
class PipelineResult:
    """Результат пайплайна."""
    success: bool
    output_path: Optional[str] = None
    ai_intermediate: Optional[str] = None
    mask_path: Optional[str] = None
    error: Optional[str] = None
    stages_completed: int = 0


# Промпты для AI этапа
AI_PROMPTS = {
    "dark": """Transform this game screenshot into dark fantasy style:
- Muted, desaturated color palette
- Rusty browns, burgundy reds, dark greens, steel blues
- Gloomy medieval atmosphere
- Keep all UI elements and composition intact
- Do NOT add blur or lose details
- Maintain sharp edges and readability""",

    "balanced": """Restyle this game screenshot with muted fantasy colors:
- Slightly desaturated but NOT dark
- Warm earthy tones: browns, amber, olive greens
- Keep original brightness level
- Maintain all details and readability
- Do NOT darken the image significantly
- Keep UI elements clear and visible""",

    "light": """Apply subtle color grading to this game screenshot:
- Slightly muted colors, keep brightness
- Warm undertones without darkening
- Preserve all details and contrast
- Keep the image readable and clear
- Minimal changes to overall luminosity"""
}

AI_PROMPT = AI_PROMPTS["balanced"]  # По умолчанию сбалансированный


def run_pipeline(
    input_path: str,
    output_path: str,
    keep_intermediate: bool = False,
    skip_ai: bool = False,
    ai_model: str = "qwen-edit",
    ai_strength: float = 0.5,
    ai_mood: str = "balanced",
    style_reference: Optional[str] = None,
    palette_size: int = 32,
    dithering: bool = True,
    downscale: float = 1.0,
    ui_mask_preset: Optional[str] = None,
    ui_style: str = "original",
    debug: bool = False
) -> PipelineResult:
    """
    Запустить комбинированный пайплайн стилизации.

    Args:
        input_path: Входное изображение
        output_path: Выходное изображение
        keep_intermediate: Сохранить промежуточные файлы
        skip_ai: Пропустить AI этап (только алгоритм)
        ai_model: Модель для AI этапа (qwen-edit, gemini-pro, reve-remix, flux-lora-edit)
        ai_strength: Сила AI трансформации (0.3-0.7 рекомендуется)
        ai_mood: Настроение AI ("dark", "balanced", "light")
        palette_size: Размер палитры для алгоритма
        dithering: Применять dithering
        downscale: Коэффициент уменьшения для пиксельности
        ui_mask_preset: Пресет маски UI (None = без маски)
        ui_style: Стиль обработки UI ("original", "light", "desaturate")
        debug: Отладочный вывод

    Returns:
        PipelineResult
    """
    stages_completed = 0
    ai_output = None
    mask_output = None

    # Определяем путь для промежуточного файла
    out_path = Path(output_path)
    if keep_intermediate:
        ai_intermediate_path = str(out_path.parent / f"{out_path.stem}_ai_stage.png")
    else:
        # Используем временный файл
        ai_intermediate_path = tempfile.mktemp(suffix=".png")

    # =========================================================================
    # ЭТАП 1: AI стилизация (если не пропускаем)
    # =========================================================================
    if not skip_ai:
        # Выбираем промпт по настроению
        selected_prompt = AI_PROMPTS.get(ai_mood, AI_PROMPTS["balanced"])

        if debug:
            print("\n=== ЭТАП 1: AI стилизация ===")
            print(f"Model: {ai_model}")
            print(f"Strength: {ai_strength}")
            print(f"Mood: {ai_mood}")
            if style_reference:
                print(f"Style reference: {style_reference}")

        ai_result = ai_style_transfer(
            input_path=input_path,
            output_path=ai_intermediate_path,
            style="custom",
            custom_prompt=selected_prompt,
            model=ai_model,
            strength=ai_strength,
            style_reference=style_reference,
            debug=debug
        )

        if not ai_result.success:
            return PipelineResult(
                success=False,
                error=f"AI этап провалился: {ai_result.error}",
                stages_completed=0
            )

        stages_completed = 1
        ai_output = ai_intermediate_path
        algo_input = ai_intermediate_path

        if debug:
            print(f"AI результат: {ai_intermediate_path}")
    else:
        if debug:
            print("\n=== ЭТАП 1: AI пропущен ===")
        algo_input = input_path

    # =========================================================================
    # ЭТАП 2: Алгоритмическая обработка
    # =========================================================================
    if debug:
        print("\n=== ЭТАП 2: Алгоритмическая обработка ===")
        print(f"Палитра: {palette_size} цветов")
        print(f"Dithering: {dithering}")
        print(f"Downscale: {downscale}")

    algo_config = StyleConfig(
        palette_size=palette_size,
        saturation=0.75,          # Сохраняем насыщенность
        brightness=1.1,           # Немного осветляем (компенсация AI)
        contrast=1.05,            # Минимальный контраст
        hue_shift=8,              # Минимальный сдвиг — AI уже сделал
        dithering=dithering,
        dither_strength=0.35,     # Умеренный dithering
        use_deceiver_palette=True,
        downscale=downscale
    )

    try:
        algo_result = deceiver_stylize(
            input_path=algo_input,
            output_path=output_path,
            config=algo_config
        )

        if not algo_result.get("success"):
            return PipelineResult(
                success=False,
                error=f"Алгоритмический этап провалился",
                stages_completed=stages_completed,
                ai_intermediate=ai_output if keep_intermediate else None
            )

        stages_completed = 2

    except Exception as e:
        return PipelineResult(
            success=False,
            error=f"Алгоритмический этап: {e}",
            stages_completed=stages_completed,
            ai_intermediate=ai_output if keep_intermediate else None
        )

    # =========================================================================
    # ЭТАП 3: Применение маски UI (если указан пресет)
    # =========================================================================
    if ui_mask_preset:
        if debug:
            print(f"\n=== ЭТАП 3: Применение маски UI ===")
            print(f"Пресет: {ui_mask_preset}")
            print(f"UI стиль: {ui_style}")

        try:
            from PIL import Image

            # Создаём маску
            mask = create_ui_mask(input_path, preset=ui_mask_preset)

            # Сохраняем маску если нужно
            if keep_intermediate:
                mask_output = str(out_path.parent / f"{out_path.stem}_mask.png")
                mask.save(mask_output)

                # Визуализация маски
                vis_path = str(out_path.parent / f"{out_path.stem}_mask_vis.png")
                visualize_mask(input_path, mask, vis_path)
                if debug:
                    print(f"Маска: {mask_output}")
                    print(f"Визуализация: {vis_path}")

            # Применяем маску: комбинируем оригинал (UI) и стилизованное (контент)
            # Временно сохраняем стилизованный результат
            stylized_temp = str(out_path.parent / f"{out_path.stem}_stylized_temp.png")
            Path(output_path).rename(stylized_temp)

            # Композиция
            result = apply_with_mask(
                original=input_path,
                stylized=stylized_temp,
                mask=mask,
                ui_style=ui_style
            )
            result.save(output_path)

            # Удаляем временный файл
            Path(stylized_temp).unlink()

            stages_completed = 3

            if debug:
                print(f"Композиция с маской завершена")

        except Exception as e:
            if debug:
                print(f"Ошибка маски: {e}")
            # Не критично - результат уже есть без маски

    # Очистка временного файла если не сохраняем
    if not keep_intermediate and ai_output and Path(ai_output).exists():
        try:
            Path(ai_output).unlink()
        except:
            pass

    if debug:
        print(f"\n=== ГОТОВО ===")
        print(f"Результат: {output_path}")

    return PipelineResult(
        success=True,
        output_path=output_path,
        ai_intermediate=ai_output if keep_intermediate else None,
        mask_path=mask_output if keep_intermediate else None,
        stages_completed=stages_completed
    )


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Deceiver Style Pipeline — AI + алгоритмическая обработка",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s input.png output.png
  %(prog)s input.png output.png --keep-intermediate
  %(prog)s input.png output.png --skip-ai --dither
  %(prog)s input.png output.png --ai-strength 0.4 --palette 24
        """
    )

    parser.add_argument("input", help="Входное изображение")
    parser.add_argument("output", help="Выходное изображение")

    parser.add_argument("--keep-intermediate", "-k", action="store_true",
                        help="Сохранить промежуточные файлы")
    parser.add_argument("--skip-ai", action="store_true",
                        help="Пропустить AI этап (только алгоритм)")

    # AI параметры
    parser.add_argument("--ai-model", "-m", default="qwen-edit",
                        help="AI модель: qwen-edit, gemini-pro, reve-remix, flux-lora-edit (default: qwen-edit)")
    parser.add_argument("--ai-strength", type=float, default=0.5,
                        help="Сила AI трансформации 0.3-0.7 (default: 0.5)")
    parser.add_argument("--ai-mood", choices=["dark", "balanced", "light"],
                        default="balanced", help="Настроение AI: dark/balanced/light (default: balanced)")
    parser.add_argument("--style-ref", "-r", default=None,
                        help="Путь к референсу стиля (для gemini-pro, flux-kontext)")

    # Алгоритмические параметры
    parser.add_argument("--palette", type=int, default=32,
                        help="Размер палитры (default: 32)")
    parser.add_argument("--dither", dest='dither', action="store_true", default=True,
                        help="Включить dithering (default)")
    parser.add_argument("--no-dither", dest='dither', action="store_false",
                        help="Отключить dithering")
    parser.add_argument("--downscale", type=float, default=1.0,
                        help="Коэффициент уменьшения для пиксельности (default: 1.0)")

    # UI маска
    parser.add_argument("--ui-mask", "-u", choices=list(UI_PRESETS.keys()),
                        help="Пресет маски UI для сохранения читаемости")
    parser.add_argument("--ui-style", choices=["original", "light", "desaturate"],
                        default="original", help="Стиль обработки UI (default: original)")

    parser.add_argument("--debug", action="store_true", help="Отладочный вывод")
    parser.add_argument("--json", action="store_true", help="JSON вывод")

    args = parser.parse_args()

    if not args.json:
        print(f"Deceiver Style Pipeline")
        print(f"=" * 40)
        print(f"Вход: {args.input}")
        print(f"Выход: {args.output}")
        if args.skip_ai:
            print(f"Режим: только алгоритм")
        else:
            print(f"Режим: AI ({args.ai_model}, strength={args.ai_strength}) + алгоритм")
        if args.style_ref:
            print(f"Style ref: {args.style_ref}")
        if args.ui_mask:
            print(f"UI маска: {args.ui_mask} ({args.ui_style})")
        print()

    result = run_pipeline(
        input_path=args.input,
        output_path=args.output,
        keep_intermediate=args.keep_intermediate,
        skip_ai=args.skip_ai,
        ai_model=args.ai_model,
        ai_strength=args.ai_strength,
        ai_mood=args.ai_mood,
        style_reference=args.style_ref,
        palette_size=args.palette,
        dithering=args.dither,
        downscale=args.downscale,
        ui_mask_preset=args.ui_mask,
        ui_style=args.ui_style,
        debug=args.debug
    )

    if args.json:
        output = {
            "success": result.success,
            "output_path": result.output_path,
            "ai_intermediate": result.ai_intermediate,
            "stages_completed": result.stages_completed,
            "error": result.error
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if result.success:
            print(f"\n[OK] Готово: {result.output_path}")
            print(f"  Этапов выполнено: {result.stages_completed}")
            if result.ai_intermediate:
                print(f"  AI промежуточный: {result.ai_intermediate}")
            if result.mask_path:
                print(f"  Маска: {result.mask_path}")
        else:
            print(f"\n[FAIL] Ошибка: {result.error}")
            print(f"  Этапов выполнено: {result.stages_completed}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
