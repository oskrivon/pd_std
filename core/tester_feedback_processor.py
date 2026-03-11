"""
Tester Feedback Processor

Преобразует фидбек от тестеров в Task для демона.
"""

import logging
from pathlib import Path
from typing import Optional

from core.tester_feedback import (
    TesterFeedback,
    TesterFeedbackType,
    TesterFeedbackStatus,
    TesterFeedbackStorage,
    BugSeverity,
    BalanceArea,
    AIGenerationIssue,
    AI_ISSUE_DESCRIPTIONS
)
from core.task_db import Task, TaskPriority, get_task_db

logger = logging.getLogger("studio.tester_feedback")


# Маппинг severity → priority
SEVERITY_TO_PRIORITY = {
    BugSeverity.CRITICAL: TaskPriority.CRITICAL,
    BugSeverity.MAJOR: TaskPriority.HIGH,
    BugSeverity.MINOR: TaskPriority.NORMAL,
    BugSeverity.COSMETIC: TaskPriority.LOW,
}


class TesterFeedbackProcessor:
    """Процессор фидбеков от тестеров."""

    def __init__(self, storage: TesterFeedbackStorage, workspace_path: Path):
        self.storage = storage
        self.workspace_path = Path(workspace_path)
        self.task_db = get_task_db(workspace_path / "studio" / "tasks.db")

    def process(self, feedback: TesterFeedback) -> Optional[Task]:
        """
        Обработать фидбек и создать Task.

        Args:
            feedback: Фидбек от тестера

        Returns:
            Созданный Task или None при ошибке
        """
        if feedback.feedback_type == TesterFeedbackType.GAME_BUG:
            return self._process_game_bug(feedback)
        elif feedback.feedback_type == TesterFeedbackType.BALANCE:
            return self._process_balance(feedback)
        elif feedback.feedback_type == TesterFeedbackType.AI_GENERATION:
            return self._process_ai_generation(feedback)

        return None

    def _process_game_bug(self, feedback: TesterFeedback) -> Task:
        """Обработать баг-репорт."""
        # Определяем приоритет по severity
        priority = TaskPriority.NORMAL
        if feedback.bug_severity:
            priority = SEVERITY_TO_PRIORITY.get(feedback.bug_severity, TaskPriority.NORMAL)

        # Формируем описание
        description = self._build_bug_description(feedback)

        # Создаём Task
        task = Task(
            project=feedback.project,
            description=description,
            priority=priority
        )

        self.task_db.add(task)

        # Обновляем статус фидбека
        self.storage.update_status(
            feedback.id,
            TesterFeedbackStatus.TRIAGED,
            task_id=task.id
        )

        logger.info(f"Created bug task {task.id} from feedback {feedback.id}")
        return task

    def _process_balance(self, feedback: TesterFeedback) -> Task:
        """Обработать фидбек по балансу."""
        # Формируем описание
        description = self._build_balance_description(feedback)

        # Баланс обычно имеет нормальный приоритет
        task = Task(
            project=feedback.project,
            description=description,
            priority=TaskPriority.NORMAL
        )

        self.task_db.add(task)

        # Обновляем статус фидбека
        self.storage.update_status(
            feedback.id,
            TesterFeedbackStatus.TRIAGED,
            task_id=task.id
        )

        logger.info(f"Created balance task {task.id} from feedback {feedback.id}")
        return task

    def _process_ai_generation(self, feedback: TesterFeedback) -> Task:
        """Обработать проблему с AI-генерацией."""
        # Формируем описание
        description = self._build_ai_generation_description(feedback)

        # Приоритет зависит от количества проблем
        priority = TaskPriority.NORMAL
        if len(feedback.ai_issues) >= 3:
            priority = TaskPriority.HIGH

        task = Task(
            project=feedback.project,
            description=description,
            priority=priority
        )

        self.task_db.add(task)

        # Обновляем статус фидбека
        self.storage.update_status(
            feedback.id,
            TesterFeedbackStatus.TRIAGED,
            task_id=task.id
        )

        # Если указан asset_id, пытаемся обновить историю ассета
        if feedback.asset_id:
            self._update_asset_feedback(feedback)

        logger.info(f"Created AI generation task {task.id} from feedback {feedback.id}")
        return task

    def _build_bug_description(self, feedback: TesterFeedback) -> str:
        """Сформировать описание бага для Task."""
        lines = [
            f"[BUG] {feedback.title}",
            "",
            feedback.description
        ]

        if feedback.steps_to_reproduce:
            lines.extend([
                "",
                "ШАГИ ВОСПРОИЗВЕДЕНИЯ:",
                feedback.steps_to_reproduce
            ])

        if feedback.expected_behavior:
            lines.extend([
                "",
                "ОЖИДАЕМОЕ ПОВЕДЕНИЕ:",
                feedback.expected_behavior
            ])

        if feedback.actual_behavior:
            lines.extend([
                "",
                "ФАКТИЧЕСКОЕ ПОВЕДЕНИЕ:",
                feedback.actual_behavior
            ])

        if feedback.bug_severity:
            lines.extend([
                "",
                f"КРИТИЧНОСТЬ: {feedback.bug_severity.value.upper()}"
            ])

        if feedback.screenshots:
            lines.extend([
                "",
                "СКРИНШОТЫ:",
                *[f"  - {s.path}" for s in feedback.screenshots]
            ])

        lines.extend([
            "",
            f"Фидбек от тестера: {feedback.tester_name or 'Anonymous'}",
            f"ID фидбека: {feedback.id}"
        ])

        return "\n".join(lines)

    def _build_balance_description(self, feedback: TesterFeedback) -> str:
        """Сформировать описание проблемы баланса для Task."""
        area_name = ""
        if feedback.balance_area:
            area_map = {
                BalanceArea.DIFFICULTY: "сложность",
                BalanceArea.PROGRESSION: "прогрессия",
                BalanceArea.ECONOMY: "экономика",
                BalanceArea.COMBAT: "боевая система",
                BalanceArea.OTHER: "другое",
            }
            area_name = area_map.get(feedback.balance_area, "")

        lines = [
            f"[BALANCE] {feedback.title}",
            ""
        ]

        if area_name:
            lines.append(f"Область: {area_name}")
            lines.append("")

        lines.append(feedback.description)

        if feedback.screenshots:
            lines.extend([
                "",
                "СКРИНШОТЫ:",
                *[f"  - {s.path}" for s in feedback.screenshots]
            ])

        lines.extend([
            "",
            f"Фидбек от тестера: {feedback.tester_name or 'Anonymous'}",
            f"ID фидбека: {feedback.id}"
        ])

        return "\n".join(lines)

    def _build_ai_generation_description(self, feedback: TesterFeedback) -> str:
        """Сформировать описание проблемы AI-генерации для Task."""
        lines = [
            f"[AI-ART] {feedback.title}",
            ""
        ]

        if feedback.asset_id:
            lines.append(f"Asset ID: {feedback.asset_id}")
            lines.append("")

        lines.append(feedback.description)

        if feedback.ai_issues:
            lines.extend([
                "",
                "ПРОБЛЕМЫ:",
                *[f"  - {AI_ISSUE_DESCRIPTIONS.get(issue, issue.value)}"
                  for issue in feedback.ai_issues]
            ])

        if feedback.screenshots:
            lines.extend([
                "",
                "СКРИНШОТЫ:",
                *[f"  - {s.path}" for s in feedback.screenshots]
            ])

        lines.extend([
            "",
            f"Фидбек от тестера: {feedback.tester_name or 'Anonymous'}",
            f"ID фидбека: {feedback.id}"
        ])

        return "\n".join(lines)

    def _update_asset_feedback(self, feedback: TesterFeedback):
        """Обновить историю ассета с фидбеком от тестера."""
        try:
            from core.asset_feedback import (
                AssetHistoryManager,
                AssetFeedback,
                FeedbackIssue,
                ReviewDecision,
                ChangeIntensity
            )

            # Находим путь к проекту
            project_path = self.workspace_path / feedback.project
            if not project_path.exists():
                logger.warning(f"Project path not found: {project_path}")
                return

            studio_path = self.workspace_path / "studio"
            history_mgr = AssetHistoryManager(project_path, studio_path)
            history = history_mgr.load_history(feedback.asset_id)

            if not history.generations:
                logger.warning(f"No generations found for asset: {feedback.asset_id}")
                return

            # Маппинг AI issues -> FeedbackIssue
            ai_to_feedback_issue = {
                AIGenerationIssue.WRONG_STYLE: FeedbackIssue.WRONG_STYLE,
                AIGenerationIssue.WRONG_COLORS: FeedbackIssue.WRONG_PALETTE,
                AIGenerationIssue.MISSING_ELEMENTS: FeedbackIssue.MISSING_ELEMENTS,
                AIGenerationIssue.EXTRA_ELEMENTS: FeedbackIssue.REMOVE_OBJECTS,
                AIGenerationIssue.LOW_QUALITY: FeedbackIssue.NOT_DETAILED_ENOUGH,
            }

            issues = []
            for ai_issue in feedback.ai_issues:
                if ai_issue in ai_to_feedback_issue:
                    issues.append(ai_to_feedback_issue[ai_issue])

            # Создаём AssetFeedback
            asset_feedback = AssetFeedback(
                version=history.current_version,
                asset_id=feedback.asset_id,
                reviewer=feedback.tester_name or "tester",
                decision=ReviewDecision.REVISION_REQUESTED,
                issues=issues,
                free_text=feedback.description,
                change_intensity=ChangeIntensity.MODERATE
            )

            # Сохраняем
            history_mgr.submit_feedback(feedback.asset_id, asset_feedback)
            logger.info(f"Updated asset history for {feedback.asset_id}")

        except ImportError:
            logger.warning("asset_feedback module not available")
        except Exception as e:
            logger.error(f"Failed to update asset feedback: {e}")

    def sync_statuses(self):
        """Синхронизировать статусы фидбеков со статусами Task."""
        for feedback in self.storage.list_by_status(TesterFeedbackStatus.TRIAGED):
            if feedback.task_id:
                task = self.task_db.get(feedback.task_id)
                if task:
                    # Обновляем статус фидбека на основе статуса задачи
                    from core.task_db import TaskStatus
                    if task.status == TaskStatus.COMPLETED:
                        self.storage.update_status(
                            feedback.id,
                            TesterFeedbackStatus.RESOLVED
                        )
                    elif task.status == TaskStatus.IN_PROGRESS:
                        self.storage.update_status(
                            feedback.id,
                            TesterFeedbackStatus.IN_PROGRESS
                        )

        # То же для IN_PROGRESS
        for feedback in self.storage.list_by_status(TesterFeedbackStatus.IN_PROGRESS):
            if feedback.task_id:
                task = self.task_db.get(feedback.task_id)
                if task:
                    from core.task_db import TaskStatus
                    if task.status == TaskStatus.COMPLETED:
                        self.storage.update_status(
                            feedback.id,
                            TesterFeedbackStatus.RESOLVED
                        )
