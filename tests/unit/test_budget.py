"""
Unit Tests for Budget

Tests cover:
- Recording task usage
- Daily/monthly calculations
- Limit checking
- Persistence
"""

import json
from datetime import datetime, date, timedelta
from pathlib import Path

import pytest

from core.budget import Budget, UsageRecord, DailyUsage


class TestUsageRecord:
    """Tests for UsageRecord dataclass."""

    def test_creation(self):
        """Should create record with all fields."""
        record = UsageRecord(
            timestamp="2025-01-15T10:30:00",
            task_id="task-123",
            project="test",
            tokens_input=1000,
            tokens_output=500,
            cost_estimate=0.05,
            duration_seconds=30.5,
            description="Test task"
        )

        assert record.task_id == "task-123"
        assert record.tokens_input == 1000
        assert record.cost_estimate == 0.05

    def test_serialization_roundtrip(self):
        """Should serialize and deserialize correctly."""
        original = UsageRecord(
            timestamp="2025-01-15T10:30:00",
            task_id="task-123",
            project="test",
            tokens_input=1000,
            tokens_output=500,
            cost_estimate=0.05,
            duration_seconds=30.5,
            description="Test task"
        )

        data = original.to_dict()
        restored = UsageRecord.from_dict(data)

        assert restored.task_id == original.task_id
        assert restored.tokens_input == original.tokens_input
        assert restored.cost_estimate == original.cost_estimate


class TestBudgetBasic:
    """Basic Budget operations."""

    def test_record_task(self, empty_budget: Budget):
        """Should record task and estimate tokens/cost."""
        record = empty_budget.record_task(
            task_id="task-1",
            project="test",
            description="Test task",
            output_length=1000,
            duration_seconds=30,
            success=True
        )

        assert record.task_id == "task-1"
        assert record.project == "test"
        assert record.tokens_input > 0
        assert record.tokens_output > 0
        assert record.cost_estimate > 0

    def test_record_task_adds_to_records(self, empty_budget: Budget):
        """Recording should add to records list."""
        assert len(empty_budget.records) == 0

        empty_budget.record_task("t1", "p1", "Task 1", 100)
        empty_budget.record_task("t2", "p1", "Task 2", 200)

        assert len(empty_budget.records) == 2

    def test_record_task_truncates_description(self, empty_budget: Budget):
        """Long descriptions should be truncated."""
        long_desc = "A" * 500
        record = empty_budget.record_task("t1", "p1", long_desc, 100)

        assert len(record.description) == 100


class TestBudgetDailyUsage:
    """Daily usage calculations."""

    def test_today_usage_empty(self, empty_budget: Budget):
        """Empty budget should return zero usage."""
        usage = empty_budget.today_usage()

        assert usage.tokens_input == 0
        assert usage.tokens_output == 0
        assert usage.cost_estimate == 0
        assert usage.tasks_completed == 0

    def test_today_usage_with_tasks(self, empty_budget: Budget):
        """Should aggregate today's tasks."""
        empty_budget.record_task("t1", "p1", "Task 1", 100, success=True)
        empty_budget.record_task("t2", "p1", "Task 2", 200, success=True)
        empty_budget.record_task("t3", "p1", "Task 3", 300, success=False)

        usage = empty_budget.today_usage()

        assert usage.tasks_completed == 2
        assert usage.tasks_failed == 1
        assert usage.cost_estimate > 0


class TestBudgetLimits:
    """Limit checking."""

    def test_over_daily_limit(self, temp_dir: Path):
        """Should detect when daily limit exceeded."""
        budget = Budget(temp_dir / "budget.json", daily_limit=0.01)

        # Record enough to exceed limit
        for i in range(10):
            budget.record_task(f"t{i}", "p1", "Task", 10000)

        assert budget.over_daily_limit()

    def test_not_over_daily_limit(self, empty_budget: Budget):
        """Should not trigger limit for small usage."""
        empty_budget.record_task("t1", "p1", "Task", 100)

        assert not empty_budget.over_daily_limit()

    def test_remaining_today(self, temp_dir: Path):
        """Should calculate remaining budget."""
        budget = Budget(temp_dir / "budget.json", daily_limit=1.00)

        assert budget.remaining_today() == 1.00

        budget.record_task("t1", "p1", "Task", 1000)

        remaining = budget.remaining_today()
        assert remaining < 1.00
        assert remaining > 0

    def test_over_limit_combined(self, temp_dir: Path):
        """over_limit should check both daily and monthly."""
        budget = Budget(temp_dir / "budget.json", daily_limit=10.0, monthly_limit=0.01)

        for i in range(5):
            budget.record_task(f"t{i}", "p1", "Task", 10000)

        # Should be over monthly even if under daily
        assert budget.over_limit()


class TestBudgetPersistence:
    """Save/load operations."""

    def test_save_and_load(self, temp_dir: Path):
        """Should persist and restore correctly."""
        path = temp_dir / "budget.json"

        # Create and save
        budget1 = Budget(path, daily_limit=5.0, monthly_limit=50.0)
        budget1.record_task("t1", "p1", "Task 1", 500)
        budget1.record_task("t2", "p2", "Task 2", 1000)
        budget1.save()

        # Load in new instance
        budget2 = Budget.load(path)

        assert len(budget2.records) == 2
        assert budget2.daily_limit == 5.0
        assert budget2.monthly_limit == 50.0

    def test_load_nonexistent(self, temp_dir: Path):
        """Loading nonexistent file should return empty budget."""
        budget = Budget.load(temp_dir / "nonexistent.json")

        assert len(budget.records) == 0
        assert budget.daily_limit == 5.0  # default

    def test_load_preserves_limits(self, temp_dir: Path):
        """Should preserve saved limits."""
        path = temp_dir / "budget.json"

        Budget(path, daily_limit=10.0, monthly_limit=200.0).save()

        loaded = Budget.load(path)
        assert loaded.daily_limit == 10.0
        assert loaded.monthly_limit == 200.0


class TestBudgetStatus:
    """Status and reporting."""

    def test_status_structure(self, empty_budget: Budget):
        """status should return complete structure."""
        status = empty_budget.status()

        assert "today" in status
        assert "month" in status
        assert "over_limit" in status

        assert "cost" in status["today"]
        assert "limit" in status["today"]
        assert "remaining" in status["today"]
        assert "tasks" in status["today"]

    def test_report_format(self, empty_budget: Budget):
        """report should return formatted string."""
        empty_budget.record_task("t1", "p1", "Task", 500)

        report = empty_budget.report()

        assert "Budget Status" in report
        assert "Today:" in report
        assert "Month:" in report
        assert "$" in report


class TestBudgetCalculations:
    """Token and cost calculations."""

    def test_token_estimation_scales_with_output(self, empty_budget: Budget):
        """More output should mean more tokens."""
        r1 = empty_budget.record_task("t1", "p1", "Short", 100)
        r2 = empty_budget.record_task("t2", "p1", "Long", 10000)

        assert r2.tokens_output > r1.tokens_output

    def test_cost_scales_with_tokens(self, empty_budget: Budget):
        """More tokens should mean higher cost."""
        r1 = empty_budget.record_task("t1", "p1", "Short", 100)
        r2 = empty_budget.record_task("t2", "p1", "Long", 10000)

        assert r2.cost_estimate > r1.cost_estimate

    def test_cost_is_reasonable(self, empty_budget: Budget):
        """Cost should be in reasonable range."""
        record = empty_budget.record_task("t1", "p1", "Task", 1000)

        # Base ~2000 input tokens + ~250 output tokens
        # Should be less than $0.10 for this size
        assert record.cost_estimate < 0.10
        assert record.cost_estimate > 0.001


class TestBudgetMonthlyUsage:
    """Monthly usage calculations."""

    def test_month_usage(self, budget_with_records: Budget):
        """Should calculate current month's usage."""
        usage = budget_with_records.month_usage()

        assert usage > 0

    def test_remaining_month(self, temp_dir: Path):
        """Should calculate remaining monthly budget."""
        budget = Budget(temp_dir / "budget.json", monthly_limit=100.0)

        assert budget.remaining_month() == 100.0

        budget.record_task("t1", "p1", "Task", 1000)

        remaining = budget.remaining_month()
        assert remaining < 100.0
        assert remaining > 0
