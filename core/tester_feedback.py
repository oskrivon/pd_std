"""
Tester Feedback System

Модуль для получения фидбека от тестеров.
Фидбек автоматически преобразуется в Task для демона.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any


class TesterFeedbackType(str, Enum):
    """Тип фидбека от тестера."""
    GAME_BUG = "game_bug"              # Баг в игре
    BALANCE = "balance"                 # Проблема баланса
    AI_GENERATION = "ai_generation"     # Проблема с AI-генерацией


class BugSeverity(str, Enum):
    """Критичность бага."""
    CRITICAL = "critical"   # Игра крашится, невозможно играть
    MAJOR = "major"         # Серьёзная проблема, но можно обойти
    MINOR = "minor"         # Мелкая проблема
    COSMETIC = "cosmetic"   # Визуальный дефект


class BalanceArea(str, Enum):
    """Область баланса."""
    DIFFICULTY = "difficulty"       # Сложность
    PROGRESSION = "progression"     # Прогрессия
    ECONOMY = "economy"             # Экономика
    COMBAT = "combat"               # Боевая система
    OTHER = "other"                 # Другое


class AIGenerationIssue(str, Enum):
    """Проблемы с AI-генерацией."""
    WRONG_STYLE = "wrong_style"             # Неправильный стиль
    ARTIFACTS = "artifacts"                  # Артефакты изображения
    WRONG_COLORS = "wrong_colors"            # Неправильные цвета
    MISSING_ELEMENTS = "missing_elements"    # Отсутствуют элементы
    EXTRA_ELEMENTS = "extra_elements"        # Лишние элементы
    WRONG_SIZE = "wrong_size"                # Неправильный размер
    LOW_QUALITY = "low_quality"              # Низкое качество
    NOT_MATCHING = "not_matching"            # Не соответствует описанию


class TesterFeedbackStatus(str, Enum):
    """Статус обработки фидбека."""
    NEW = "new"                 # Новый, не обработан
    TRIAGED = "triaged"         # Рассмотрен, создан Task
    IN_PROGRESS = "in_progress" # Выполняется
    RESOLVED = "resolved"       # Решён
    WONT_FIX = "wont_fix"       # Не будет исправлен
    DUPLICATE = "duplicate"     # Дубликат


@dataclass
class TesterScreenshot:
    """Скриншот от тестера."""
    filename: str
    path: str
    uploaded_at: str = field(default_factory=lambda: datetime.now().isoformat())
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "path": self.path,
            "uploaded_at": self.uploaded_at,
            "description": self.description
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TesterScreenshot":
        return cls(
            filename=d["filename"],
            path=d["path"],
            uploaded_at=d.get("uploaded_at", ""),
            description=d.get("description", "")
        )


@dataclass
class TesterFeedback:
    """Фидбек от тестера."""
    # Идентификация
    id: str = ""
    project: str = ""
    feedback_type: TesterFeedbackType = TesterFeedbackType.GAME_BUG

    # Информация о тестере
    tester_name: str = ""
    tester_email: str = ""
    submitted_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Основная информация
    title: str = ""
    description: str = ""

    # Для багов
    steps_to_reproduce: str = ""
    expected_behavior: str = ""
    actual_behavior: str = ""
    bug_severity: Optional[BugSeverity] = None

    # Для баланса
    balance_area: Optional[BalanceArea] = None

    # Для AI-генерации
    ai_issues: List[AIGenerationIssue] = field(default_factory=list)
    asset_id: str = ""  # ID ассета с проблемой

    # Скриншоты
    screenshots: List[TesterScreenshot] = field(default_factory=list)

    # Статус и связь с Task
    status: TesterFeedbackStatus = TesterFeedbackStatus.NEW
    task_id: Optional[str] = None

    def __post_init__(self):
        if not self.id:
            import hashlib
            import time
            data = f"{self.project}{self.title}{time.time()}"
            self.id = "tf_" + hashlib.md5(data.encode()).hexdigest()[:8]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "feedback_type": self.feedback_type.value,
            "tester_name": self.tester_name,
            "tester_email": self.tester_email,
            "submitted_at": self.submitted_at,
            "title": self.title,
            "description": self.description,
            "steps_to_reproduce": self.steps_to_reproduce,
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
            "bug_severity": self.bug_severity.value if self.bug_severity else None,
            "balance_area": self.balance_area.value if self.balance_area else None,
            "ai_issues": [i.value for i in self.ai_issues],
            "asset_id": self.asset_id,
            "screenshots": [s.to_dict() for s in self.screenshots],
            "status": self.status.value,
            "task_id": self.task_id
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TesterFeedback":
        return cls(
            id=d.get("id", ""),
            project=d.get("project", ""),
            feedback_type=TesterFeedbackType(d.get("feedback_type", "game_bug")),
            tester_name=d.get("tester_name", ""),
            tester_email=d.get("tester_email", ""),
            submitted_at=d.get("submitted_at", ""),
            title=d.get("title", ""),
            description=d.get("description", ""),
            steps_to_reproduce=d.get("steps_to_reproduce", ""),
            expected_behavior=d.get("expected_behavior", ""),
            actual_behavior=d.get("actual_behavior", ""),
            bug_severity=BugSeverity(d["bug_severity"]) if d.get("bug_severity") else None,
            balance_area=BalanceArea(d["balance_area"]) if d.get("balance_area") else None,
            ai_issues=[AIGenerationIssue(i) for i in d.get("ai_issues", [])],
            asset_id=d.get("asset_id", ""),
            screenshots=[TesterScreenshot.from_dict(s) for s in d.get("screenshots", [])],
            status=TesterFeedbackStatus(d.get("status", "new")),
            task_id=d.get("task_id")
        )


class TesterFeedbackStorage:
    """Хранилище фидбеков тестеров в JSON файлах."""

    def __init__(self, storage_path: Path):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.index_path = self.storage_path / "index.json"
        self._ensure_index()

    def _ensure_index(self):
        """Создать индексный файл если не существует."""
        if not self.index_path.exists():
            self._save_index({"feedbacks": []})

    def _load_index(self) -> dict:
        """Загрузить индекс."""
        with open(self.index_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_index(self, index: dict):
        """Сохранить индекс."""
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _get_feedback_path(self, feedback_id: str) -> Path:
        """Получить путь к файлу фидбека."""
        return self.storage_path / f"{feedback_id}.json"

    def save(self, feedback: TesterFeedback) -> TesterFeedback:
        """Сохранить фидбек."""
        # Сохраняем в отдельный файл
        feedback_path = self._get_feedback_path(feedback.id)
        with open(feedback_path, 'w', encoding='utf-8') as f:
            json.dump(feedback.to_dict(), f, ensure_ascii=False, indent=2)

        # Обновляем индекс
        index = self._load_index()
        feedback_ids = index.get("feedbacks", [])

        # Добавляем если новый
        if feedback.id not in feedback_ids:
            feedback_ids.insert(0, feedback.id)  # Новые сверху
            index["feedbacks"] = feedback_ids
            self._save_index(index)

        return feedback

    def get(self, feedback_id: str) -> Optional[TesterFeedback]:
        """Получить фидбек по ID."""
        feedback_path = self._get_feedback_path(feedback_id)
        if not feedback_path.exists():
            return None

        with open(feedback_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return TesterFeedback.from_dict(data)

    def list_all(self) -> List[TesterFeedback]:
        """Получить все фидбеки."""
        index = self._load_index()
        feedbacks = []

        for feedback_id in index.get("feedbacks", []):
            feedback = self.get(feedback_id)
            if feedback:
                feedbacks.append(feedback)

        return feedbacks

    def list_by_status(self, status: TesterFeedbackStatus) -> List[TesterFeedback]:
        """Получить фидбеки по статусу."""
        return [f for f in self.list_all() if f.status == status]

    def list_by_project(self, project: str) -> List[TesterFeedback]:
        """Получить фидбеки по проекту."""
        return [f for f in self.list_all() if f.project == project]

    def list_by_type(self, feedback_type: TesterFeedbackType) -> List[TesterFeedback]:
        """Получить фидбеки по типу."""
        return [f for f in self.list_all() if f.feedback_type == feedback_type]

    def update_status(self, feedback_id: str, status: TesterFeedbackStatus,
                      task_id: Optional[str] = None) -> Optional[TesterFeedback]:
        """Обновить статус фидбека."""
        feedback = self.get(feedback_id)
        if not feedback:
            return None

        feedback.status = status
        if task_id:
            feedback.task_id = task_id

        return self.save(feedback)

    def delete(self, feedback_id: str) -> bool:
        """Удалить фидбек."""
        feedback_path = self._get_feedback_path(feedback_id)
        if not feedback_path.exists():
            return False

        feedback_path.unlink()

        # Обновляем индекс
        index = self._load_index()
        feedbacks = index.get("feedbacks", [])
        if feedback_id in feedbacks:
            feedbacks.remove(feedback_id)
            index["feedbacks"] = feedbacks
            self._save_index(index)

        return True

    def stats(self) -> Dict[str, int]:
        """Статистика по фидбекам."""
        all_feedbacks = self.list_all()

        return {
            "total": len(all_feedbacks),
            "new": len([f for f in all_feedbacks if f.status == TesterFeedbackStatus.NEW]),
            "triaged": len([f for f in all_feedbacks if f.status == TesterFeedbackStatus.TRIAGED]),
            "in_progress": len([f for f in all_feedbacks if f.status == TesterFeedbackStatus.IN_PROGRESS]),
            "resolved": len([f for f in all_feedbacks if f.status == TesterFeedbackStatus.RESOLVED]),
            "by_type": {
                "game_bug": len([f for f in all_feedbacks if f.feedback_type == TesterFeedbackType.GAME_BUG]),
                "balance": len([f for f in all_feedbacks if f.feedback_type == TesterFeedbackType.BALANCE]),
                "ai_generation": len([f for f in all_feedbacks if f.feedback_type == TesterFeedbackType.AI_GENERATION]),
            }
        }


# Маппинг проблем AI-генерации в описания
AI_ISSUE_DESCRIPTIONS = {
    AIGenerationIssue.WRONG_STYLE: "Стиль не соответствует игре",
    AIGenerationIssue.ARTIFACTS: "Есть артефакты/шумы на изображении",
    AIGenerationIssue.WRONG_COLORS: "Неправильные цвета",
    AIGenerationIssue.MISSING_ELEMENTS: "Отсутствуют необходимые элементы",
    AIGenerationIssue.EXTRA_ELEMENTS: "Есть лишние элементы",
    AIGenerationIssue.WRONG_SIZE: "Неправильный размер/пропорции",
    AIGenerationIssue.LOW_QUALITY: "Низкое качество изображения",
    AIGenerationIssue.NOT_MATCHING: "Не соответствует описанию",
}

SEVERITY_LABELS = {
    BugSeverity.CRITICAL: "Критический",
    BugSeverity.MAJOR: "Важный",
    BugSeverity.MINOR: "Незначительный",
    BugSeverity.COSMETIC: "Косметический",
}

BALANCE_AREA_LABELS = {
    BalanceArea.DIFFICULTY: "Сложность",
    BalanceArea.PROGRESSION: "Прогрессия",
    BalanceArea.ECONOMY: "Экономика",
    BalanceArea.COMBAT: "Боевая система",
    BalanceArea.OTHER: "Другое",
}
