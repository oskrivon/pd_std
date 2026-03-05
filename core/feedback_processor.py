"""
Feedback Processor

Преобразует фидбэк от людей в промпты для генерации.
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from .asset_feedback import (
    AssetHistory, AssetFeedback, FeedbackIssue,
    ChangeIntensity, ISSUE_DESCRIPTIONS, INTENSITY_INSTRUCTIONS
)


class FeedbackProcessor:
    """Обработчик фидбэка для генерации промптов."""

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.design_tokens = self._load_design_tokens()

    def _load_design_tokens(self) -> dict:
        """Загрузить design tokens проекта."""
        tokens_path = self.project_path / "assets" / "design_tokens.json"
        if tokens_path.exists():
            with open(tokens_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def get_style_description(self) -> str:
        """Получить описание стиля из design tokens."""
        if not self.design_tokens:
            return "pixel art style"

        parts = []

        # Основные цвета
        colors = self.design_tokens.get("colors", {})
        if colors:
            primary = colors.get("primary", {}).get("value", "")
            accent = colors.get("accent", {}).get("value", "")
            if primary:
                parts.append(f"primary color {primary}")
            if accent:
                parts.append(f"accent color {accent}")

        return ", ".join(parts) if parts else "pixel art style"

    def build_initial_prompt(self, spec: dict) -> str:
        """
        Построить начальный промпт из спецификации.

        Args:
            spec: Спецификация ассета из manifest.json

        Returns:
            Промпт для генерации
        """
        parts = []

        # Тип ассета
        asset_type = spec.get("type", "image")
        parts.append(f"pixel art game {asset_type}")

        # Описание
        if spec.get("description"):
            parts.append(spec["description"])

        # Размеры
        width = spec.get("width", 64)
        height = spec.get("height", 64)
        parts.append(f"{width}x{height} pixels")

        # Теги
        tags = spec.get("tags", [])
        if tags:
            parts.append(", ".join(tags))

        # Стиль
        parts.append("16-bit retro style")
        parts.append(self.get_style_description())

        return ", ".join(parts)

    def build_revision_prompt(self, history: AssetHistory) -> str:
        """
        Построить промпт для ревизии на основе истории и фидбэка.

        Args:
            history: Полная история генераций с фидбэком

        Returns:
            Промпт для следующей итерации
        """
        parts = []

        # 1. Базовое описание из спецификации
        base_prompt = self.build_initial_prompt(history.spec)
        parts.append(f"Generate: {base_prompt}")

        # 2. Стиль из design tokens
        style = self.get_style_description()
        if style:
            parts.append(f"\nStyle requirements: {style}")

        # 3. История итераций
        if len(history.generations) > 1:
            parts.append("\n--- PREVIOUS ITERATIONS ---")
            for gen in history.generations[:-1]:  # Все кроме последней
                parts.append(f"V{gen.version}: {gen.prompt[:100]}...")
                if gen.feedback:
                    parts.append(f"  Issue: {gen.feedback.free_text[:100]}")

        # 4. Текущий фидбэк (самое важное)
        latest = history.get_latest()
        if latest and latest.feedback:
            feedback = latest.feedback
            parts.append("\n--- REVISION REQUIREMENTS ---")

            # Структурированные проблемы
            if feedback.issues:
                problem_descriptions = [
                    ISSUE_DESCRIPTIONS.get(issue, str(issue))
                    for issue in feedback.issues
                ]
                parts.append(f"Fix these issues: {'; '.join(problem_descriptions)}")

            # Конкретные запросы
            if feedback.specific_requests:
                parts.append("Specific changes required:")
                for req in feedback.specific_requests:
                    where = f" ({req.where})" if req.where else ""
                    parts.append(f"  - {req.action.upper()} {req.what}{where}")

            # Свободный текст
            if feedback.free_text:
                parts.append(f"\nAdditional feedback: {feedback.free_text}")

            # Интенсивность изменений
            instruction = INTENSITY_INSTRUCTIONS.get(
                feedback.change_intensity,
                INTENSITY_INSTRUCTIONS[ChangeIntensity.MODERATE]
            )
            parts.append(f"\n{instruction}")

        return "\n".join(parts)

    def extract_specific_requests(self, text: str) -> List[Dict[str, str]]:
        """
        Извлечь конкретные запросы из свободного текста.

        Args:
            text: Текст фидбэка

        Returns:
            Список запросов в формате {action, what, where}
        """
        requests = []

        # Простой парсинг ключевых слов
        text_lower = text.lower()

        # Паттерны добавления
        add_keywords = ["добавить", "добавь", "нужно больше", "add", "more"]
        for kw in add_keywords:
            if kw in text_lower:
                # Находим что добавить (слово после ключевого)
                idx = text_lower.find(kw)
                after = text[idx + len(kw):].strip()
                words = after.split()[:3]  # Берём до 3 слов
                if words:
                    requests.append({
                        "action": "add",
                        "what": " ".join(words),
                        "where": ""
                    })

        # Паттерны увеличения
        increase_keywords = ["ярче", "светлее", "больше", "увеличить", "brighter", "more"]
        for kw in increase_keywords:
            if kw in text_lower:
                idx = text_lower.find(kw)
                after = text[idx + len(kw):].strip()
                words = after.split()[:2]
                if words:
                    requests.append({
                        "action": "increase",
                        "what": " ".join(words),
                        "where": ""
                    })

        # Паттерны уменьшения
        decrease_keywords = ["темнее", "меньше", "убрать", "уменьшить", "darker", "less", "remove"]
        for kw in decrease_keywords:
            if kw in text_lower:
                idx = text_lower.find(kw)
                after = text[idx + len(kw):].strip()
                words = after.split()[:2]
                if words:
                    requests.append({
                        "action": "decrease" if kw not in ["убрать", "remove"] else "remove",
                        "what": " ".join(words),
                        "where": ""
                    })

        return requests

    def analyze_feedback_text(self, text: str) -> List[FeedbackIssue]:
        """
        Анализировать текст фидбэка и определить проблемы.

        Args:
            text: Текст фидбэка

        Returns:
            Список выявленных проблем
        """
        issues = []
        text_lower = text.lower()

        # Маппинг ключевых слов на проблемы
        keyword_map = {
            FeedbackIssue.TOO_DARK: ["тёмн", "темн", "dark", "мрачн", "gloomy"],
            FeedbackIssue.TOO_BRIGHT: ["ярк", "светл", "bright", "слепит"],
            FeedbackIssue.TOO_GLOOMY: ["мрачн", "депрессивн", "gloomy", "sad"],
            FeedbackIssue.LOW_CONTRAST: ["контраст", "contrast", "не видно"],
            FeedbackIssue.TOO_EMPTY: ["пуст", "empty", "мало", "не хватает"],
            FeedbackIssue.TOO_CLUTTERED: ["много", "перегруж", "cluttered", "messy"],
            FeedbackIssue.NEED_MORE_ELEMENTS: ["добавить", "больше", "add", "more"],
            FeedbackIssue.NOT_PIXEL_ART: ["не пиксел", "not pixel", "гладк"],
            FeedbackIssue.TOO_DETAILED: ["детализ", "detailed", "сложн"],
            FeedbackIssue.WRONG_STYLE: ["стиль", "style", "не подходит", "doesn't match"],
        }

        for issue, keywords in keyword_map.items():
            for kw in keywords:
                if kw in text_lower:
                    issues.append(issue)
                    break

        return list(set(issues))  # Убираем дубликаты

    def create_feedback_from_text(self, asset_id: str, version: int,
                                   text: str, reviewer: str = "user") -> AssetFeedback:
        """
        Создать структурированный фидбэк из текста.

        Args:
            asset_id: ID ассета
            version: Версия
            text: Текст фидбэка от человека
            reviewer: Кто оставил фидбэк

        Returns:
            Структурированный объект фидбэка
        """
        from .asset_feedback import SpecificRequest, ReviewDecision

        # Анализируем текст
        issues = self.analyze_feedback_text(text)
        specific_requests = self.extract_specific_requests(text)

        # Определяем интенсивность
        text_lower = text.lower()
        if any(w in text_lower for w in ["заново", "полностью", "completely", "from scratch"]):
            intensity = ChangeIntensity.MAJOR
        elif any(w in text_lower for w in ["немного", "чуть", "slightly", "a bit"]):
            intensity = ChangeIntensity.MINIMAL
        else:
            intensity = ChangeIntensity.MODERATE

        return AssetFeedback(
            version=version,
            asset_id=asset_id,
            reviewer=reviewer,
            decision=ReviewDecision.REVISION_REQUESTED,
            issues=issues,
            free_text=text,
            specific_requests=[SpecificRequest(**r) for r in specific_requests],
            change_intensity=intensity
        )


def format_prompt_for_pixellab(prompt: str, no_background: bool = False) -> str:
    """
    Форматировать промпт для PixelLab API.

    Args:
        prompt: Исходный промпт
        no_background: Нужен ли прозрачный фон

    Returns:
        Оптимизированный промпт
    """
    # PixelLab лучше работает с короткими промптами
    # Убираем лишние инструкции, оставляем суть

    # Берём основное описание (до первого ---)
    if "---" in prompt:
        main_part = prompt.split("---")[0].strip()
    else:
        main_part = prompt

    # Убираем "Generate:" и подобные префиксы
    prefixes_to_remove = ["Generate:", "Create:", "Make:"]
    for prefix in prefixes_to_remove:
        if main_part.startswith(prefix):
            main_part = main_part[len(prefix):].strip()

    # Добавляем стилистические теги для PixelLab
    style_tags = ["16-bit", "pixel art", "game asset"]

    result_parts = [main_part]

    # Проверяем есть ли уже эти теги
    main_lower = main_part.lower()
    for tag in style_tags:
        if tag.lower() not in main_lower:
            result_parts.append(tag)

    if no_background:
        result_parts.append("transparent background")

    return ", ".join(result_parts)
