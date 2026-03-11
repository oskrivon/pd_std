"""
Asset Scanner

Сканирует manifest.json проектов и находит ассеты для генерации.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum


class AssetStatus(str, Enum):
    """Статусы ассетов в manifest."""
    PLANNED = "planned"           # Нужно сгенерировать
    GENERATING = "generating"     # Генерируется сейчас
    PENDING_REVIEW = "pending_review"  # Ждёт ревью
    APPROVED = "approved"         # Одобрен, готов
    REJECTED = "rejected"         # Отклонён
    READY = "ready"               # Готов (уже был в проекте)
    NEEDS_MANUAL = "needs_manual" # Требует ручной работы


@dataclass
class AssetSpec:
    """Спецификация ассета из manifest."""
    asset_id: str
    category: str
    status: AssetStatus
    spec: dict
    path: Optional[str] = None
    project: str = ""

    @property
    def needs_generation(self) -> bool:
        """Нужна ли генерация?"""
        return self.status in [AssetStatus.PLANNED, AssetStatus.REJECTED]

    @property
    def needs_review(self) -> bool:
        """Нужен ли ревью?"""
        return self.status == AssetStatus.PENDING_REVIEW

    def to_dict(self) -> dict:
        """Конвертировать в словарь."""
        return {
            "asset_id": self.asset_id,
            "category": self.category,
            "status": self.status.value if isinstance(self.status, AssetStatus) else self.status,
            "spec": self.spec,
            "path": self.path,
            "project": self.project
        }


class AssetScanner:
    """Сканер ассетов проекта."""

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.manifest_path = self.project_path / "assets" / "manifest.json"
        self.tokens_path = self.project_path / "assets" / "design_tokens.json"

    def load_manifest(self) -> dict:
        """Загрузить manifest.json."""
        if not self.manifest_path.exists():
            return {"assets": {}}

        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_manifest(self, manifest: dict) -> None:
        """Сохранить manifest.json."""
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def load_design_tokens(self) -> dict:
        """Загрузить design tokens."""
        if not self.tokens_path.exists():
            return {}

        with open(self.tokens_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def scan_all(self) -> List[AssetSpec]:
        """
        Сканировать все ассеты в manifest.

        Returns:
            Список спецификаций ассетов
        """
        manifest = self.load_manifest()
        assets = []

        for category, category_assets in manifest.get("assets", {}).items():
            # Skip non-dict categories
            if not isinstance(category_assets, dict):
                continue

            for asset_id, spec in category_assets.items():
                # Skip metadata fields like _readme
                if asset_id.startswith("_") or not isinstance(spec, dict):
                    continue

                status_str = spec.get("status", "ready")  # Default to ready if no status
                try:
                    status = AssetStatus(status_str)
                except ValueError:
                    status = AssetStatus.READY

                assets.append(AssetSpec(
                    asset_id=asset_id,
                    category=category,
                    status=status,
                    spec=spec,
                    path=spec.get("path"),
                    project=self.project_path.name
                ))

        return assets

    def scan_for_generation(self) -> List[AssetSpec]:
        """
        Найти ассеты, требующие генерации.

        Returns:
            Список ассетов со статусом planned или rejected
        """
        return [a for a in self.scan_all() if a.needs_generation]

    def scan_for_review(self) -> List[AssetSpec]:
        """
        Найти ассеты, ожидающие ревью.

        Returns:
            Список ассетов со статусом pending_review
        """
        return [a for a in self.scan_all() if a.needs_review]

    def update_status(self, asset_id: str, category: str,
                      new_status: AssetStatus, **extra_fields) -> bool:
        """
        Обновить статус ассета в manifest.

        Args:
            asset_id: ID ассета
            category: Категория
            new_status: Новый статус
            **extra_fields: Дополнительные поля (path, feedback и т.д.)

        Returns:
            True если успешно
        """
        manifest = self.load_manifest()

        if category not in manifest.get("assets", {}):
            return False

        if asset_id not in manifest["assets"][category]:
            return False

        manifest["assets"][category][asset_id]["status"] = new_status.value

        for key, value in extra_fields.items():
            manifest["assets"][category][asset_id][key] = value

        self.save_manifest(manifest)
        return True

    def add_asset(self, asset_id: str, category: str, spec: dict) -> bool:
        """
        Добавить новый ассет в manifest.

        Args:
            asset_id: ID ассета
            category: Категория (backgrounds, ui, sprites и т.д.)
            spec: Спецификация

        Returns:
            True если успешно
        """
        manifest = self.load_manifest()

        if "assets" not in manifest:
            manifest["assets"] = {}

        if category not in manifest["assets"]:
            manifest["assets"][category] = {}

        # Добавляем статус если нет
        if "status" not in spec:
            spec["status"] = AssetStatus.PLANNED.value

        manifest["assets"][category][asset_id] = spec
        self.save_manifest(manifest)
        return True

    def get_asset_spec(self, asset_id: str, category: str) -> Optional[AssetSpec]:
        """
        Получить спецификацию конкретного ассета.

        Args:
            asset_id: ID ассета
            category: Категория

        Returns:
            AssetSpec или None
        """
        manifest = self.load_manifest()

        if category not in manifest.get("assets", {}):
            return None

        if asset_id not in manifest["assets"][category]:
            return None

        spec = manifest["assets"][category][asset_id]
        status_str = spec.get("status", "planned")
        try:
            status = AssetStatus(status_str)
        except ValueError:
            status = AssetStatus.PLANNED

        return AssetSpec(
            asset_id=asset_id,
            category=category,
            status=status,
            spec=spec,
            path=spec.get("path"),
            project=self.project_path.name
        )


def scan_all_projects(workspace: Path) -> Dict[str, List[AssetSpec]]:
    """
    Сканировать все проекты в workspace.

    Args:
        workspace: Корневая папка workspace

    Returns:
        Словарь {project_name: [AssetSpec, ...]}
    """
    results = {}

    for project_dir in workspace.iterdir():
        if not project_dir.is_dir():
            continue

        manifest_path = project_dir / "assets" / "manifest.json"
        if manifest_path.exists():
            scanner = AssetScanner(project_dir)
            assets = scanner.scan_all()
            if assets:
                results[project_dir.name] = assets

    return results


def get_pending_review_all(workspace: Path) -> List[AssetSpec]:
    """
    Получить все ассеты, ожидающие ревью, из всех проектов.

    Args:
        workspace: Корневая папка workspace

    Returns:
        Список ассетов pending_review
    """
    pending = []

    all_assets = scan_all_projects(workspace)
    for project, assets in all_assets.items():
        for asset in assets:
            if asset.needs_review:
                pending.append(asset)

    return pending
