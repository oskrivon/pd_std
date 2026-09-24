"""
Project Model

Represents a game project managed by the studio.
Handles project discovery, configuration, and scaffolding.

Usage:
    from core.project import Project, discover_projects

    # Load existing project
    project = Project.load("./workspace/backpack_hero")

    # Discover all projects in workspace
    projects = discover_projects("./workspace")

    # Create new project
    project = Project.scaffold("my_game", engine="love")
"""

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger("studio.project")


class Engine(str, Enum):
    """Supported game engines."""
    LOVE = "love"
    UNREAL = "unreal"
    UNKNOWN = "unknown"


class ProjectStatus(str, Enum):
    """Project status."""
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


@dataclass
class Project:
    """Game project managed by the studio."""

    name: str
    path: Path
    engine: Engine = Engine.UNKNOWN
    status: ProjectStatus = ProjectStatus.ACTIVE
    description: str = ""
    created_at: Optional[str] = None

    # Cached metadata
    _claude_md: Optional[str] = field(default=None, repr=False)

    def __post_init__(self):
        if isinstance(self.path, str):
            self.path = Path(self.path)
        if isinstance(self.engine, str):
            self.engine = Engine(self.engine)
        if isinstance(self.status, str):
            self.status = ProjectStatus(self.status)

    @classmethod
    def load(cls, path: str | Path) -> Optional["Project"]:
        """
        Load project from path.
        Reads CLAUDE.md or project config to determine engine and metadata.
        """
        path = Path(path)

        if not path.exists():
            logger.error(f"Project path does not exist: {path}")
            return None

        name = path.name
        engine = detect_engine(path)
        description = ""

        # Try to read description from CLAUDE.md
        claude_md = path / "CLAUDE.md"
        if claude_md.exists():
            content = claude_md.read_text(encoding="utf-8", errors="ignore")
            # Extract first paragraph as description
            lines = content.split("\n")
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    description = line[:200]
                    break

        return cls(
            name=name,
            path=path,
            engine=engine,
            description=description
        )

    @classmethod
    def scaffold(
        cls,
        name: str,
        engine: Engine | str = Engine.LOVE,
        workspace: str | Path = "./workspace"
    ) -> "Project":
        """
        Create new project with standard structure.
        """
        if isinstance(engine, str):
            engine = Engine(engine)

        workspace = Path(workspace)
        project_path = workspace / name

        if project_path.exists():
            raise ValueError(f"Project already exists: {project_path}")

        # Create directory structure
        project_path.mkdir(parents=True)

        if engine == Engine.LOVE:
            _scaffold_love(project_path, name)
        elif engine == Engine.UNREAL:
            _scaffold_unreal(project_path, name)

        # Create CLAUDE.md
        _create_claude_md(project_path, name, engine)

        # Create docs/
        docs_path = project_path / "docs"
        docs_path.mkdir(exist_ok=True)
        (docs_path / "PLAN.md").write_text("# Plan\n\n## TODO\n\n## Done\n", encoding="utf-8")

        # Git init
        import subprocess
        subprocess.run(["git", "init"], cwd=project_path, capture_output=True)

        # Create .gitignore
        gitignore = _get_gitignore(engine)
        (project_path / ".gitignore").write_text(gitignore, encoding="utf-8")

        # Initial commit
        subprocess.run(["git", "add", "."], cwd=project_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"Initial commit: {name}"],
            cwd=project_path,
            capture_output=True
        )

        logger.info(f"Created project: {project_path}")

        return cls(
            name=name,
            path=project_path,
            engine=engine,
            created_at=datetime.now().isoformat()
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "path": str(self.path),
            "engine": self.engine.value,
            "status": self.status.value,
            "description": self.description,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            path=Path(data["path"]),
            engine=Engine(data.get("engine", "unknown")),
            status=ProjectStatus(data.get("status", "active")),
            description=data.get("description", ""),
            created_at=data.get("created_at")
        )


def detect_engine(path: Path) -> Engine:
    """Detect game engine from project structure."""
    # LÖVE 2D
    if (path / "main.lua").exists() or (path / "conf.lua").exists():
        return Engine.LOVE

    # Unreal Engine
    if list(path.glob("*.uproject")):
        return Engine.UNREAL

    return Engine.UNKNOWN


def discover_projects(workspace: str | Path) -> List[Project]:
    """
    Discover all game projects in workspace.
    Returns list of Project objects.
    """
    workspace = Path(workspace)
    projects = []

    if not workspace.exists():
        logger.warning(f"Workspace does not exist: {workspace}")
        return projects

    for child in workspace.iterdir():
        if not child.is_dir():
            continue

        # Skip hidden and special directories
        if child.name.startswith(".") or child.name in ("studio", "__pycache__"):
            continue

        # Check if it's a game project
        engine = detect_engine(child)
        if engine != Engine.UNKNOWN:
            project = Project.load(child)
            if project:
                projects.append(project)

    return projects


def _scaffold_love(path: Path, name: str):
    """Create LÖVE project structure."""

    # main.lua
    main_lua = f'''-- {name}
-- Created by Ptero Dactyl Studio

function love.load()
    love.window.setTitle("{name}")
end

function love.update(dt)
end

function love.draw()
    love.graphics.print("Hello from {name}!", 100, 100)
end
'''
    (path / "main.lua").write_text(main_lua, encoding="utf-8")

    # conf.lua
    conf_lua = f'''function love.conf(t)
    t.title = "{name}"
    t.version = "11.4"
    t.window.width = 800
    t.window.height = 600
end
'''
    (path / "conf.lua").write_text(conf_lua, encoding="utf-8")

    # Create standard directories
    (path / "assets").mkdir()
    (path / "src").mkdir()


def _scaffold_unreal(path: Path, name: str):
    """Create minimal Unreal project marker (actual project created in UE)."""
    readme = f"""# {name}

Unreal Engine project.

## Setup

1. Open Unreal Editor
2. Create new project in this folder
3. Or copy existing .uproject here
"""
    (path / "README.md").write_text(readme, encoding="utf-8")


def _create_claude_md(path: Path, name: str, engine: Engine):
    """Create CLAUDE.md for the project."""

    engine_docs = {
        Engine.LOVE: """## Stack

- LÖVE 2D (Lua)
- Lua 5.1

## Running

```bash
love .
```
""",
        Engine.UNREAL: """## Stack

- Unreal Engine 5
- C++ / Blueprint

## Running

Open .uproject in Unreal Editor
"""
    }

    content = f"""# Project: {name}

[Description here]

{engine_docs.get(engine, "")}

## Structure

```
{name}/
├── CLAUDE.md
├── docs/
│   └── PLAN.md
└── ...
```

## Current State

New project, not yet started.

## Next Step

See docs/PLAN.md
"""
    (path / "CLAUDE.md").write_text(content, encoding="utf-8")


def _get_gitignore(engine: Engine) -> str:
    """Get .gitignore content for engine."""

    common = """# Common
.DS_Store
Thumbs.db
*.log
__pycache__/
*.pyc
.env
"""

    love_ignore = """# LÖVE
*.love
"""

    unreal_ignore = """# Unreal
Binaries/
Build/
DerivedDataCache/
Intermediate/
Saved/
.vs/
*.sln
*.VC.db
"""

    if engine == Engine.LOVE:
        return common + love_ignore
    elif engine == Engine.UNREAL:
        return common + unreal_ignore
    else:
        return common


# Module test
if __name__ == "__main__":
    import sys

    workspace = Path("./workspace")
    print(f"Discovering projects in {workspace}...")

    projects = discover_projects(workspace)

    for p in projects:
        print(f"  {p.name} ({p.engine.value}): {p.description[:50]}...")
