"""
Budget Tracking

Track token/cost usage for the studio.
Since Claude Code CLI doesn't expose token counts directly,
we estimate based on task execution and track overall usage.

Usage:
    from core.budget import Budget

    budget = Budget.load("budget.json")
    budget.record_task(task_id="abc", tokens_estimate=1500, cost_estimate=0.02)
    budget.save()

    if budget.over_limit():
        print("Budget exceeded!")
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger("studio.budget")

# Rough estimates for Claude Code operations
TOKEN_ESTIMATES = {
    "task_base": 2000,      # Base context per task
    "read_file": 500,       # Reading a file
    "write_file": 300,      # Writing a file
    "search": 200,          # Search operation
    "response_per_100_chars": 25,  # Output tokens estimate
}

# Cost per 1M tokens (approximate, Sonnet pricing)
COST_PER_MTK_INPUT = 3.0   # $3 per 1M input tokens
COST_PER_MTK_OUTPUT = 15.0  # $15 per 1M output tokens


@dataclass
class UsageRecord:
    """Single usage record."""
    timestamp: str
    task_id: str
    project: str
    tokens_input: int = 0
    tokens_output: int = 0
    cost_estimate: float = 0.0
    duration_seconds: float = 0.0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "project": self.project,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "cost_estimate": self.cost_estimate,
            "duration_seconds": self.duration_seconds,
            "description": self.description
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UsageRecord":
        return cls(**data)


@dataclass
class DailyUsage:
    """Aggregated daily usage."""
    date: str
    tokens_input: int = 0
    tokens_output: int = 0
    cost_estimate: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0


class Budget:
    """
    Budget tracker for studio operations.
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        daily_limit: float = 5.0,  # $5/day default
        monthly_limit: float = 100.0  # $100/month default
    ):
        self.path = path
        self.daily_limit = daily_limit
        self.monthly_limit = monthly_limit

        self.records: List[UsageRecord] = []
        self._daily_cache: Dict[str, DailyUsage] = {}

    @classmethod
    def load(cls, path: str | Path, **kwargs) -> "Budget":
        """Load budget from JSON file."""
        path = Path(path)
        budget = cls(path, **kwargs)

        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                budget.daily_limit = data.get("daily_limit", budget.daily_limit)
                budget.monthly_limit = data.get("monthly_limit", budget.monthly_limit)

                for record_data in data.get("records", []):
                    budget.records.append(UsageRecord.from_dict(record_data))

                budget._rebuild_cache()
                logger.info(f"Loaded budget with {len(budget.records)} records")
            except Exception as e:
                logger.error(f"Failed to load budget: {e}")

        return budget

    def save(self) -> None:
        """Save budget to JSON file."""
        if not self.path:
            return

        data = {
            "daily_limit": self.daily_limit,
            "monthly_limit": self.monthly_limit,
            "records": [r.to_dict() for r in self.records],
            "updated_at": datetime.now().isoformat()
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def record_task(
        self,
        task_id: str,
        project: str,
        description: str = "",
        output_length: int = 0,
        duration_seconds: float = 0.0,
        success: bool = True
    ) -> UsageRecord:
        """
        Record a task execution.
        Estimates tokens based on output length.
        """
        # Estimate tokens
        tokens_input = TOKEN_ESTIMATES["task_base"]
        tokens_output = max(100, output_length // 4)  # ~4 chars per token

        # Estimate cost
        cost = (
            (tokens_input / 1_000_000) * COST_PER_MTK_INPUT +
            (tokens_output / 1_000_000) * COST_PER_MTK_OUTPUT
        )

        record = UsageRecord(
            timestamp=datetime.now().isoformat(),
            task_id=task_id,
            project=project,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_estimate=round(cost, 4),
            duration_seconds=duration_seconds,
            description=description[:100]
        )

        self.records.append(record)
        self._update_cache(record, success)

        logger.info(f"Recorded task {task_id}: ~{tokens_input + tokens_output} tokens, ${cost:.4f}")
        return record

    def _rebuild_cache(self) -> None:
        """Rebuild daily usage cache."""
        self._daily_cache.clear()
        for record in self.records:
            date_str = record.timestamp[:10]
            if date_str not in self._daily_cache:
                self._daily_cache[date_str] = DailyUsage(date=date_str)

            daily = self._daily_cache[date_str]
            daily.tokens_input += record.tokens_input
            daily.tokens_output += record.tokens_output
            daily.cost_estimate += record.cost_estimate
            daily.tasks_completed += 1

    def _update_cache(self, record: UsageRecord, success: bool) -> None:
        """Update cache with new record."""
        date_str = record.timestamp[:10]
        if date_str not in self._daily_cache:
            self._daily_cache[date_str] = DailyUsage(date=date_str)

        daily = self._daily_cache[date_str]
        daily.tokens_input += record.tokens_input
        daily.tokens_output += record.tokens_output
        daily.cost_estimate += record.cost_estimate
        if success:
            daily.tasks_completed += 1
        else:
            daily.tasks_failed += 1

    def today_usage(self) -> DailyUsage:
        """Get today's usage."""
        today = date.today().isoformat()
        return self._daily_cache.get(today, DailyUsage(date=today))

    def month_usage(self) -> float:
        """Get current month's total cost."""
        month_prefix = date.today().strftime("%Y-%m")
        total = 0.0
        for date_str, daily in self._daily_cache.items():
            if date_str.startswith(month_prefix):
                total += daily.cost_estimate
        return total

    def over_daily_limit(self) -> bool:
        """Check if daily limit exceeded."""
        return self.today_usage().cost_estimate >= self.daily_limit

    def over_monthly_limit(self) -> bool:
        """Check if monthly limit exceeded."""
        return self.month_usage() >= self.monthly_limit

    def over_limit(self) -> bool:
        """Check if any limit exceeded."""
        return self.over_daily_limit() or self.over_monthly_limit()

    def remaining_today(self) -> float:
        """Remaining budget for today."""
        return max(0, self.daily_limit - self.today_usage().cost_estimate)

    def remaining_month(self) -> float:
        """Remaining budget for this month."""
        return max(0, self.monthly_limit - self.month_usage())

    def status(self) -> Dict[str, Any]:
        """Get budget status."""
        today = self.today_usage()
        return {
            "today": {
                "cost": round(today.cost_estimate, 2),
                "limit": self.daily_limit,
                "remaining": round(self.remaining_today(), 2),
                "tasks": today.tasks_completed
            },
            "month": {
                "cost": round(self.month_usage(), 2),
                "limit": self.monthly_limit,
                "remaining": round(self.remaining_month(), 2)
            },
            "over_limit": self.over_limit()
        }

    def report(self) -> str:
        """Generate text report."""
        status = self.status()
        lines = [
            "Budget Status",
            "=" * 40,
            f"Today: ${status['today']['cost']:.2f} / ${status['today']['limit']:.2f}",
            f"  Tasks: {status['today']['tasks']}",
            f"  Remaining: ${status['today']['remaining']:.2f}",
            "",
            f"Month: ${status['month']['cost']:.2f} / ${status['month']['limit']:.2f}",
            f"  Remaining: ${status['month']['remaining']:.2f}",
            "",
            f"Over limit: {'YES' if status['over_limit'] else 'No'}"
        ]
        return "\n".join(lines)


# Module test
if __name__ == "__main__":
    budget = Budget()

    # Simulate some tasks
    budget.record_task("t1", "hamster", "Add feature", output_length=500)
    budget.record_task("t2", "hamster", "Fix bug", output_length=200)
    budget.record_task("t3", "backpack_hero", "Update UI", output_length=1000)

    print(budget.report())
    print("\nStatus:", budget.status())
