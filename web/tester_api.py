"""
Tester Feedback API

FastAPI роутер для формы фидбека тестеров.
"""

import os
import sys
from pathlib import Path
from typing import Optional, List
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.tester_feedback import (
    TesterFeedback,
    TesterFeedbackType,
    TesterFeedbackStatus,
    TesterFeedbackStorage,
    TesterScreenshot,
    BugSeverity,
    BalanceArea,
    AIGenerationIssue,
    SEVERITY_LABELS,
    BALANCE_AREA_LABELS,
    AI_ISSUE_DESCRIPTIONS
)
from core.tester_feedback_processor import TesterFeedbackProcessor
from core.project import discover_projects

# Globals
WORKSPACE = Path(os.environ.get("PTERO_WORKSPACE", "C:/Ptero Dactyl Games"))
STORAGE_PATH = WORKSPACE / "studio" / "tester_feedback"

router = APIRouter(prefix="/tester", tags=["tester"])

# Templates
web_dir = Path(__file__).parent
templates = Jinja2Templates(directory=web_dir / "templates")


def get_storage() -> TesterFeedbackStorage:
    """Get or create storage instance."""
    return TesterFeedbackStorage(STORAGE_PATH)


def get_processor() -> TesterFeedbackProcessor:
    """Get or create processor instance."""
    return TesterFeedbackProcessor(get_storage(), WORKSPACE)


def get_projects() -> dict:
    """Get discovered projects."""
    return {p.name: p for p in discover_projects(WORKSPACE)}


# ============ HTML Pages ============

@router.get("/feedback", response_class=HTMLResponse)
async def feedback_form(request: Request, project: Optional[str] = None):
    """HTML форма для отправки фидбека."""
    projects = get_projects()

    return templates.TemplateResponse("tester/feedback_form.html", {
        "request": request,
        "projects": list(projects.values()),
        "selected_project": project,
        "feedback_types": [
            {"value": TesterFeedbackType.GAME_BUG.value, "label": "Баг в игре"},
            {"value": TesterFeedbackType.BALANCE.value, "label": "Проблема баланса"},
            {"value": TesterFeedbackType.AI_GENERATION.value, "label": "Проблема AI-арта"},
        ],
        "severities": [
            {"value": s.value, "label": SEVERITY_LABELS[s]}
            for s in BugSeverity
        ],
        "balance_areas": [
            {"value": a.value, "label": BALANCE_AREA_LABELS[a]}
            for a in BalanceArea
        ],
        "ai_issues": [
            {"value": i.value, "label": AI_ISSUE_DESCRIPTIONS[i]}
            for i in AIGenerationIssue
        ]
    })


@router.post("/feedback/submit", response_class=HTMLResponse)
async def submit_feedback_form(
    request: Request,
    project: str = Form(...),
    feedback_type: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    tester_name: str = Form(default=""),
    tester_email: str = Form(default=""),
    # Bug fields
    steps_to_reproduce: str = Form(default=""),
    expected_behavior: str = Form(default=""),
    actual_behavior: str = Form(default=""),
    bug_severity: str = Form(default=""),
    # Balance fields
    balance_area: str = Form(default=""),
    # AI fields
    ai_issues: List[str] = Form(default=[]),
    asset_id: str = Form(default=""),
    # Screenshots
    screenshots: List[UploadFile] = File(default=[])
):
    """Обработка отправки формы фидбека."""
    storage = get_storage()
    processor = get_processor()

    # Сохраняем скриншоты
    screenshot_objects = []
    if screenshots and screenshots[0].filename:
        screenshots_dir = STORAGE_PATH / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        for screenshot in screenshots:
            if screenshot.filename:
                # Генерируем уникальное имя
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{timestamp}_{screenshot.filename}"
                filepath = screenshots_dir / filename

                content = await screenshot.read()
                filepath.write_bytes(content)

                screenshot_objects.append(TesterScreenshot(
                    filename=filename,
                    path=str(filepath),
                    description=""
                ))

    # Создаём фидбек
    feedback = TesterFeedback(
        project=project,
        feedback_type=TesterFeedbackType(feedback_type),
        title=title,
        description=description,
        tester_name=tester_name,
        tester_email=tester_email,
        steps_to_reproduce=steps_to_reproduce,
        expected_behavior=expected_behavior,
        actual_behavior=actual_behavior,
        bug_severity=BugSeverity(bug_severity) if bug_severity else None,
        balance_area=BalanceArea(balance_area) if balance_area else None,
        ai_issues=[AIGenerationIssue(i) for i in ai_issues] if ai_issues else [],
        asset_id=asset_id,
        screenshots=screenshot_objects
    )

    # Сохраняем
    storage.save(feedback)

    # Обрабатываем (создаём Task)
    task = processor.process(feedback)

    return templates.TemplateResponse("tester/feedback_success.html", {
        "request": request,
        "feedback": feedback,
        "task": task
    })


@router.get("/feedback/success/{feedback_id}", response_class=HTMLResponse)
async def feedback_success(request: Request, feedback_id: str):
    """Страница успеха после отправки."""
    storage = get_storage()
    feedback = storage.get(feedback_id)

    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    return templates.TemplateResponse("tester/feedback_success.html", {
        "request": request,
        "feedback": feedback
    })


@router.get("/feedback/list", response_class=HTMLResponse)
async def feedback_list(
    request: Request,
    project: Optional[str] = None,
    status: Optional[str] = None
):
    """Список фидбеков."""
    storage = get_storage()
    projects = get_projects()

    if project:
        feedbacks = storage.list_by_project(project)
    elif status:
        feedbacks = storage.list_by_status(TesterFeedbackStatus(status))
    else:
        feedbacks = storage.list_all()

    return templates.TemplateResponse("tester/feedback_list.html", {
        "request": request,
        "feedbacks": feedbacks,
        "projects": list(projects.values()),
        "selected_project": project,
        "selected_status": status,
        "stats": storage.stats()
    })


# ============ JSON API ============

@router.post("/api/feedback")
async def api_submit_feedback(
    project: str,
    feedback_type: str,
    title: str,
    description: str,
    tester_name: str = "",
    tester_email: str = "",
    steps_to_reproduce: str = "",
    expected_behavior: str = "",
    actual_behavior: str = "",
    bug_severity: Optional[str] = None,
    balance_area: Optional[str] = None,
    ai_issues: List[str] = [],
    asset_id: str = ""
):
    """JSON API для отправки фидбека."""
    storage = get_storage()
    processor = get_processor()

    feedback = TesterFeedback(
        project=project,
        feedback_type=TesterFeedbackType(feedback_type),
        title=title,
        description=description,
        tester_name=tester_name,
        tester_email=tester_email,
        steps_to_reproduce=steps_to_reproduce,
        expected_behavior=expected_behavior,
        actual_behavior=actual_behavior,
        bug_severity=BugSeverity(bug_severity) if bug_severity else None,
        balance_area=BalanceArea(balance_area) if balance_area else None,
        ai_issues=[AIGenerationIssue(i) for i in ai_issues] if ai_issues else [],
        asset_id=asset_id
    )

    storage.save(feedback)
    task = processor.process(feedback)

    return {
        "success": True,
        "feedback_id": feedback.id,
        "task_id": task.id if task else None
    }


@router.get("/api/feedback/{feedback_id}")
async def api_get_feedback(feedback_id: str):
    """Получить фидбек по ID."""
    storage = get_storage()
    feedback = storage.get(feedback_id)

    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    return feedback.to_dict()


@router.get("/api/feedback")
async def api_list_feedbacks(
    project: Optional[str] = None,
    status: Optional[str] = None,
    feedback_type: Optional[str] = None
):
    """Список фидбеков с фильтрами."""
    storage = get_storage()

    if project:
        feedbacks = storage.list_by_project(project)
    elif status:
        feedbacks = storage.list_by_status(TesterFeedbackStatus(status))
    elif feedback_type:
        feedbacks = storage.list_by_type(TesterFeedbackType(feedback_type))
    else:
        feedbacks = storage.list_all()

    return {
        "feedbacks": [f.to_dict() for f in feedbacks],
        "count": len(feedbacks)
    }


@router.get("/api/stats")
async def api_stats():
    """Статистика по фидбекам."""
    storage = get_storage()
    return storage.stats()


@router.post("/api/feedback/{feedback_id}/status")
async def api_update_status(
    feedback_id: str,
    status: str,
    task_id: Optional[str] = None
):
    """Обновить статус фидбека."""
    storage = get_storage()

    feedback = storage.update_status(
        feedback_id,
        TesterFeedbackStatus(status),
        task_id
    )

    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    return {"success": True, "feedback": feedback.to_dict()}
