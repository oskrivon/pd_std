"""
Integration Tests for Analyzer

Tests task classification logic.
Includes both mocked tests and optional real Claude tests.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.analyzer import (
    analyze_task,
    _parse_analysis,
    TaskType,
    AnalysisResult
)


class TestParseAnalysis:
    """Test JSON parsing logic (no Claude needed)."""

    def test_parse_simple_json(self):
        """Should parse simple JSON response."""
        output = '{"task_type": "simple", "confidence": 0.9, "reasoning": "One line change"}'

        result = _parse_analysis(output)

        assert result.task_type == TaskType.SIMPLE
        assert result.confidence == 0.9
        assert "One line" in result.reasoning

    def test_parse_json_with_markdown(self):
        """Should extract JSON from markdown code block."""
        output = '''Here is the analysis:
```json
{"task_type": "complex", "confidence": 0.8, "reasoning": "Multiple systems", "subtasks": ["Task 1", "Task 2"]}
```'''

        result = _parse_analysis(output)

        assert result.task_type == TaskType.COMPLEX
        assert result.subtasks == ["Task 1", "Task 2"]

    def test_parse_complex_with_subtasks(self):
        """Should parse complex task with subtasks."""
        output = json.dumps({
            "task_type": "complex",
            "confidence": 0.85,
            "reasoning": "Requires new systems",
            "subtasks": [
                "Create room layout",
                "Add objects",
                "Add transitions"
            ],
            "context_files": ["rooms.lua", "objects.lua"]
        })

        result = _parse_analysis(output)

        assert result.task_type == TaskType.COMPLEX
        assert len(result.subtasks) == 3
        assert result.context_needed == ["rooms.lua", "objects.lua"]

    def test_parse_unclear_with_feedback(self):
        """Should parse unclear task with feedback."""
        output = json.dumps({
            "task_type": "unclear",
            "confidence": 0.7,
            "reasoning": "Too vague",
            "feedback": "Please specify what 'better' means"
        })

        result = _parse_analysis(output)

        assert result.task_type == TaskType.UNCLEAR
        assert "specify" in result.feedback

    def test_parse_invalid_json_fallback(self):
        """Should fallback on invalid JSON."""
        output = "This is not JSON at all"

        result = _parse_analysis(output)

        assert result.task_type == TaskType.CLEAR
        assert result.confidence == 0.5
        assert "parse" in result.reasoning.lower()

    def test_parse_extracts_json_from_text(self):
        """Should find JSON embedded in text."""
        output = '''I analyzed the task and here is my assessment:

{"task_type": "clear", "confidence": 0.8, "reasoning": "Standard feature"}

Let me know if you need more details.'''

        result = _parse_analysis(output)

        assert result.task_type == TaskType.CLEAR
        assert result.confidence == 0.8


class TestAnalyzeTaskMocked:
    """Test analyze_task with mocked Claude CLI."""

    def test_analyze_returns_result(self, temp_workspace: Path):
        """Should return AnalysisResult."""
        with patch('core.analyzer.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout='{"task_type": "simple", "confidence": 0.9, "reasoning": "Simple change"}',
                returncode=0
            )

            result = analyze_task(
                project="test",
                description="Fix typo",
                project_path=temp_workspace
            )

            assert isinstance(result, AnalysisResult)
            assert result.task_type == TaskType.SIMPLE

    def test_analyze_timeout_fallback(self, temp_workspace: Path):
        """Should fallback on timeout."""
        import subprocess

        with patch('core.analyzer.subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("claude", 120)

            result = analyze_task(
                project="test",
                description="Complex task",
                project_path=temp_workspace
            )

            assert result.task_type == TaskType.CLEAR
            assert result.confidence == 0.5
            assert "timeout" in result.reasoning.lower()

    def test_analyze_error_fallback(self, temp_workspace: Path):
        """Should fallback on error."""
        with patch('core.analyzer.subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Test error")

            result = analyze_task(
                project="test",
                description="Some task",
                project_path=temp_workspace
            )

            assert result.task_type == TaskType.CLEAR
            assert result.confidence == 0.5

    def test_analyze_uses_opus(self, temp_workspace: Path):
        """Should use Opus model."""
        with patch('core.analyzer.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout='{"task_type": "clear", "confidence": 0.8, "reasoning": "OK"}',
                returncode=0
            )

            analyze_task(
                project="test",
                description="Task",
                project_path=temp_workspace
            )

            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "--model" in cmd
            assert "opus" in cmd


class TestTaskTypeClassification:
    """Test classification logic through parsing."""

    def test_simple_tasks(self):
        """Simple tasks should be classified correctly."""
        simple_responses = [
            '{"task_type": "simple", "confidence": 0.95, "reasoning": "Typo fix"}',
            '{"task_type": "simple", "confidence": 0.9, "reasoning": "Change constant"}',
        ]

        for response in simple_responses:
            result = _parse_analysis(response)
            assert result.task_type == TaskType.SIMPLE

    def test_complex_tasks_have_subtasks(self):
        """Complex tasks should have subtasks."""
        response = json.dumps({
            "task_type": "complex",
            "confidence": 0.85,
            "reasoning": "New game area needed",
            "subtasks": [
                "Create park room file",
                "Add park objects",
                "Connect to map",
                "Add transitions"
            ]
        })

        result = _parse_analysis(response)

        assert result.task_type == TaskType.COMPLEX
        assert result.subtasks is not None
        assert len(result.subtasks) >= 2

    def test_unclear_tasks_have_feedback(self):
        """Unclear tasks should have feedback."""
        response = json.dumps({
            "task_type": "unclear",
            "confidence": 0.6,
            "reasoning": "Ambiguous request",
            "feedback": "What does 'make it better' mean specifically?"
        })

        result = _parse_analysis(response)

        assert result.task_type == TaskType.UNCLEAR
        assert result.feedback is not None
        assert len(result.feedback) > 0


class TestModelRecommendation:
    """Test model recommendation logic."""

    def test_simple_uses_sonnet(self):
        """Simple tasks should use Sonnet."""
        response = '{"task_type": "simple", "confidence": 0.9, "reasoning": "Simple"}'
        result = _parse_analysis(response)
        assert result.model_recommendation == "sonnet"

    def test_clear_uses_sonnet(self):
        """Clear tasks should use Sonnet."""
        response = '{"task_type": "clear", "confidence": 0.8, "reasoning": "Clear"}'
        result = _parse_analysis(response)
        assert result.model_recommendation == "sonnet"

    def test_complex_uses_sonnet_for_execution(self):
        """Complex tasks use Sonnet for execution (Opus only for analysis)."""
        response = '{"task_type": "complex", "confidence": 0.7, "reasoning": "Complex", "subtasks": ["a", "b"]}'
        result = _parse_analysis(response)
        assert result.model_recommendation == "sonnet"


@pytest.mark.integration
class TestAnalyzerWithClaude:
    """Tests that require real Claude CLI with Opus."""

    @pytest.mark.skipif(
        not pytest.importorskip("shutil").which("claude"),
        reason="Claude CLI not available"
    )
    @pytest.mark.slow
    def test_analyze_simple_task_real(self, temp_workspace: Path):
        """Analyze a simple task with real Opus."""
        result = analyze_task(
            project="test",
            description="исправить опечатку в README.md",
            project_path=temp_workspace,
            project_engine="love"
        )

        # Should be simple or clear
        assert result.task_type in [TaskType.SIMPLE, TaskType.CLEAR]
        assert result.confidence > 0.5

    @pytest.mark.skipif(
        not pytest.importorskip("shutil").which("claude"),
        reason="Claude CLI not available"
    )
    @pytest.mark.slow
    def test_analyze_unclear_task_real(self, temp_workspace: Path):
        """Analyze an unclear task with real Opus."""
        result = analyze_task(
            project="test",
            description="сделай лучше",
            project_path=temp_workspace,
            project_engine="love"
        )

        # Should be unclear
        assert result.task_type == TaskType.UNCLEAR
        assert result.feedback is not None
