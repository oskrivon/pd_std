"""
Asset Feedback System

Управление историей генераций и обработка фидбэка от людей.
"""

import json
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any


class FeedbackCategory(str, Enum):
    """Категории структурированного фидбэка."""
    COLORS = "colors"
    COMPOSITION = "composition"
    STYLE = "style"
    DETAILS = "details"


class FeedbackIssue(str, Enum):
    """Конкретные проблемы для фидбэка."""
    # Colors
    TOO_DARK = "too_dark"
    TOO_BRIGHT = "too_bright"
    TOO_GLOOMY = "too_gloomy"
    WRONG_PALETTE = "wrong_palette"
    LOW_CONTRAST = "low_contrast"
    COLORS_DONT_MATCH = "colors_dont_match"

    # Composition
    TOO_EMPTY = "too_empty"
    TOO_CLUTTERED = "too_cluttered"
    NEED_MORE_ELEMENTS = "need_more_elements"
    WRONG_FOCUS = "wrong_focus"
    BAD_BALANCE = "bad_balance"

    # Style
    NOT_PIXEL_ART = "not_pixel_art"
    TOO_DETAILED = "too_detailed"
    NOT_DETAILED_ENOUGH = "not_detailed_enough"
    WRONG_STYLE = "wrong_style"
    INCONSISTENT = "inconsistent"

    # Details
    ADD_OBJECTS = "add_objects"
    REMOVE_OBJECTS = "remove_objects"
    WRONG_PROPORTIONS = "wrong_proportions"
    MISSING_ELEMENTS = "missing_elements"


class ChangeIntensity(str, Enum):
    """Интенсивность требуемых изменений."""
    MINIMAL = "minimal"      # Небольшие корректировки
    MODERATE = "moderate"    # Переработка части
    MAJOR = "major"          # Генерация заново


class ReviewDecision(str, Enum):
    """Решение ревьюера."""
    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    REJECTED = "rejected"


@dataclass
class SpecificRequest:
    """Конкретный запрос на изменение."""
    action: str      # add, remove, increase, decrease, change
    what: str        # что именно
    where: str = ""  # где (опционально)

    def to_dict(self) -> dict:
        return {"action": self.action, "what": self.what, "where": self.where}

    @classmethod
    def from_dict(cls, d: dict) -> "SpecificRequest":
        return cls(action=d["action"], what=d["what"], where=d.get("where", ""))


@dataclass
class AssetFeedback:
    """Фидбэк на версию ассета."""
    version: int
    asset_id: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    reviewer: str = "anonymous"
    decision: ReviewDecision = ReviewDecision.REVISION_REQUESTED

    # Структурированный фидбэк
    issues: List[FeedbackIssue] = field(default_factory=list)

    # Свободный текст
    free_text: str = ""

    # Конкретные запросы
    specific_requests: List[SpecificRequest] = field(default_factory=list)

    # Референсы
    reference_images: List[str] = field(default_factory=list)

    # Интенсивность изменений
    change_intensity: ChangeIntensity = ChangeIntensity.MODERATE

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "asset_id": self.asset_id,
            "timestamp": self.timestamp,
            "reviewer": self.reviewer,
            "decision": self.decision.value,
            "issues": [i.value for i in self.issues],
            "free_text": self.free_text,
            "specific_requests": [r.to_dict() for r in self.specific_requests],
            "reference_images": self.reference_images,
            "change_intensity": self.change_intensity.value
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AssetFeedback":
        return cls(
            version=d["version"],
            asset_id=d["asset_id"],
            timestamp=d.get("timestamp", ""),
            reviewer=d.get("reviewer", "anonymous"),
            decision=ReviewDecision(d.get("decision", "revision_requested")),
            issues=[FeedbackIssue(i) for i in d.get("issues", [])],
            free_text=d.get("free_text", ""),
            specific_requests=[SpecificRequest.from_dict(r) for r in d.get("specific_requests", [])],
            reference_images=d.get("reference_images", []),
            change_intensity=ChangeIntensity(d.get("change_intensity", "moderate"))
        )


@dataclass
class GenerationRecord:
    """Запись об одной генерации."""
    version: int
    timestamp: str
    prompt: str
    result_path: str
    feedback: Optional[AssetFeedback] = None

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "prompt": self.prompt,
            "result_path": self.result_path,
            "feedback": self.feedback.to_dict() if self.feedback else None
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GenerationRecord":
        return cls(
            version=d["version"],
            timestamp=d["timestamp"],
            prompt=d["prompt"],
            result_path=d["result_path"],
            feedback=AssetFeedback.from_dict(d["feedback"]) if d.get("feedback") else None
        )


@dataclass
class AssetHistory:
    """Полная история генераций ассета."""
    asset_id: str
    project: str
    spec: dict                  # Оригинальная спецификация из manifest
    generations: List[GenerationRecord] = field(default_factory=list)
    current_version: int = 0
    status: str = "pending"     # pending, generating, pending_review, approved, rejected

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "project": self.project,
            "spec": self.spec,
            "generations": [g.to_dict() for g in self.generations],
            "current_version": self.current_version,
            "status": self.status
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AssetHistory":
        return cls(
            asset_id=d["asset_id"],
            project=d["project"],
            spec=d["spec"],
            generations=[GenerationRecord.from_dict(g) for g in d.get("generations", [])],
            current_version=d.get("current_version", 0),
            status=d.get("status", "pending")
        )

    def add_generation(self, prompt: str, result_path: str) -> GenerationRecord:
        """Добавить новую генерацию."""
        self.current_version += 1
        record = GenerationRecord(
            version=self.current_version,
            timestamp=datetime.now().isoformat(),
            prompt=prompt,
            result_path=result_path
        )
        self.generations.append(record)
        self.status = "pending_review"
        return record

    def add_feedback(self, feedback: AssetFeedback) -> None:
        """Добавить фидбэк к текущей версии."""
        if self.generations:
            self.generations[-1].feedback = feedback
            if feedback.decision == ReviewDecision.APPROVED:
                self.status = "approved"
            elif feedback.decision == ReviewDecision.REJECTED:
                self.status = "rejected"
            else:
                self.status = "pending"  # Готов к новой генерации

    def get_latest(self) -> Optional[GenerationRecord]:
        """Получить последнюю генерацию."""
        return self.generations[-1] if self.generations else None

    def get_all_feedback(self) -> List[AssetFeedback]:
        """Получить весь фидбэк."""
        return [g.feedback for g in self.generations if g.feedback]


class AssetHistoryManager:
    """Менеджер истории генераций."""

    def __init__(self, project_path: Path, studio_path: Path = None):
        self.project_path = Path(project_path)
        self.project_name = self.project_path.name

        # История хранится в studio/generations/{project}/, не в проекте
        if studio_path is None:
            # Предполагаем стандартную структуру workspace
            studio_path = self.project_path.parent / "studio"

        self.studio_path = Path(studio_path)
        self.generations_dir = self.studio_path / "generations" / self.project_name
        self.generations_dir.mkdir(parents=True, exist_ok=True)

    def _get_asset_dir(self, asset_id: str) -> Path:
        """Получить директорию для ассета."""
        asset_dir = self.generations_dir / asset_id
        asset_dir.mkdir(parents=True, exist_ok=True)
        return asset_dir

    def _get_history_path(self, asset_id: str) -> Path:
        """Путь к файлу истории."""
        return self._get_asset_dir(asset_id) / "history.json"

    def load_history(self, asset_id: str, spec: Optional[dict] = None) -> AssetHistory:
        """Загрузить или создать историю ассета."""
        history_path = self._get_history_path(asset_id)

        if history_path.exists():
            with open(history_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return AssetHistory.from_dict(data)

        # Создаём новую историю
        return AssetHistory(
            asset_id=asset_id,
            project=self.project_path.name,
            spec=spec or {}
        )

    def save_history(self, history: AssetHistory) -> None:
        """Сохранить историю."""
        history_path = self._get_history_path(history.asset_id)
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history.to_dict(), f, ensure_ascii=False, indent=2)

    def save_generation(self, asset_id: str, prompt: str,
                        image_path: Path, spec: Optional[dict] = None) -> AssetHistory:
        """
        Сохранить результат генерации.

        Args:
            asset_id: ID ассета
            prompt: Использованный промпт
            image_path: Путь к сгенерированному изображению
            spec: Спецификация из manifest (для новых ассетов)

        Returns:
            Обновлённая история
        """
        history = self.load_history(asset_id, spec)

        # Создаём директорию для версии
        version = history.current_version + 1
        version_dir = self._get_asset_dir(asset_id) / f"v{version}"
        version_dir.mkdir(parents=True, exist_ok=True)

        # Копируем изображение
        result_path = version_dir / "result.png"
        shutil.copy(image_path, result_path)

        # Сохраняем промпт
        prompt_path = version_dir / "prompt.txt"
        prompt_path.write_text(prompt, encoding='utf-8')

        # Добавляем запись
        history.add_generation(prompt, str(result_path))
        self.save_history(history)

        return history

    def submit_feedback(self, asset_id: str, feedback: AssetFeedback) -> AssetHistory:
        """
        Добавить фидбэк к ассету.

        Args:
            asset_id: ID ассета
            feedback: Объект фидбэка

        Returns:
            Обновлённая история
        """
        history = self.load_history(asset_id)
        history.add_feedback(feedback)

        # Сохраняем фидбэк в файл версии
        if history.generations:
            version = history.generations[-1].version
            version_dir = self._get_asset_dir(asset_id) / f"v{version}"
            feedback_path = version_dir / "feedback.json"
            with open(feedback_path, 'w', encoding='utf-8') as f:
                json.dump(feedback.to_dict(), f, ensure_ascii=False, indent=2)

        self.save_history(history)
        return history

    def approve_asset(self, asset_id: str, target_path: Path) -> bool:
        """
        Одобрить ассет и скопировать в целевую папку.

        Args:
            asset_id: ID ассета
            target_path: Куда копировать финальный файл

        Returns:
            True если успешно
        """
        history = self.load_history(asset_id)
        latest = history.get_latest()

        if not latest:
            return False

        # Копируем файл
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(latest.result_path, target_path)

        # Обновляем статус
        history.status = "approved"
        self.save_history(history)

        return True

    def list_pending_review(self) -> List[AssetHistory]:
        """Получить все ассеты, ожидающие ревью."""
        pending = []

        for asset_dir in self.generations_dir.iterdir():
            if asset_dir.is_dir():
                history = self.load_history(asset_dir.name)
                if history.status == "pending_review":
                    pending.append(history)

        return pending

    def list_all(self) -> List[AssetHistory]:
        """Получить все ассеты с историей."""
        all_assets = []

        for asset_dir in self.generations_dir.iterdir():
            if asset_dir.is_dir() and (asset_dir / "history.json").exists():
                history = self.load_history(asset_dir.name)
                all_assets.append(history)

        return all_assets


# Маппинг проблем в описания для промпта
ISSUE_DESCRIPTIONS = {
    FeedbackIssue.TOO_DARK: "image is too dark, increase overall brightness",
    FeedbackIssue.TOO_BRIGHT: "image is too bright, reduce brightness",
    FeedbackIssue.TOO_GLOOMY: "mood is too gloomy, add warmer colors and light sources",
    FeedbackIssue.WRONG_PALETTE: "colors don't match the design palette",
    FeedbackIssue.LOW_CONTRAST: "increase contrast between elements",
    FeedbackIssue.COLORS_DONT_MATCH: "colors are inconsistent with the game style",

    FeedbackIssue.TOO_EMPTY: "composition feels empty, add more visual elements",
    FeedbackIssue.TOO_CLUTTERED: "too many elements, simplify the composition",
    FeedbackIssue.NEED_MORE_ELEMENTS: "add more objects and details to the scene",
    FeedbackIssue.WRONG_FOCUS: "visual focus is in the wrong place",
    FeedbackIssue.BAD_BALANCE: "improve visual balance of the composition",

    FeedbackIssue.NOT_PIXEL_ART: "style should be pixel art, add visible pixels",
    FeedbackIssue.TOO_DETAILED: "too much detail, simplify for pixel art style",
    FeedbackIssue.NOT_DETAILED_ENOUGH: "add more details and textures",
    FeedbackIssue.WRONG_STYLE: "style doesn't match the game aesthetic",
    FeedbackIssue.INCONSISTENT: "style is inconsistent with other assets",

    FeedbackIssue.ADD_OBJECTS: "add specific objects as requested",
    FeedbackIssue.REMOVE_OBJECTS: "remove unwanted objects",
    FeedbackIssue.WRONG_PROPORTIONS: "fix proportions of elements",
    FeedbackIssue.MISSING_ELEMENTS: "add missing required elements",
}

INTENSITY_INSTRUCTIONS = {
    ChangeIntensity.MINIMAL: "Make small adjustments while keeping the overall image intact",
    ChangeIntensity.MODERATE: "Rework specific elements while preserving the base structure",
    ChangeIntensity.MAJOR: "Generate a fresh version addressing all feedback from scratch",
}
