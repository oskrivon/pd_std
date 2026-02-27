"""
Markdown Task Parser

Parses task definitions from .md files with support for references (images, files).

Format:
```markdown
# Задача: Task Title

**Проект:** project_name
**Приоритет:** critical|high|normal|low

## Описание
Task description here.

## Референсы
![Description](path/to/image.png)
[Document](path/to/file.pdf)

## Контекст
- Additional context
- File hints
```

Usage:
    from core.md_tasks import parse_task_md, import_tasks_from_inbox

    task = parse_task_md("tasks_inbox/new_feature.md")
    imported = import_tasks_from_inbox("tasks_inbox/")
"""

import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger("studio.md_tasks")


@dataclass
class MdTask:
    """Parsed markdown task."""
    title: str
    project: str
    priority: str = "normal"
    description: str = ""
    references: List[str] = field(default_factory=list)
    context: str = ""
    source_file: Optional[Path] = None

    def to_prompt(self) -> str:
        """Convert to worker prompt with reference instructions."""
        parts = [self.description]

        if self.references:
            parts.append("\n\nРЕФЕРЕНСЫ (изучи перед выполнением):")
            for ref in self.references:
                parts.append(f"  - {ref}")

        if self.context:
            parts.append(f"\n\nКОНТЕКСТ:\n{self.context}")

        return "\n".join(parts)


def parse_task_md(file_path: Path | str) -> Optional[MdTask]:
    """
    Parse a markdown task file.

    Args:
        file_path: Path to .md file

    Returns:
        MdTask or None if parsing failed
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.error(f"Task file not found: {file_path}")
        return None

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")
        return None

    # Parse title
    title_match = re.search(r'^#\s+(?:Задача:\s*)?(.+)$', content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else file_path.stem

    # Parse project
    project_match = re.search(r'\*\*Проект:\*\*\s*(\S+)', content)
    if not project_match:
        logger.error(f"No project specified in {file_path}")
        return None
    project = project_match.group(1).strip()

    # Parse priority
    priority_match = re.search(r'\*\*Приоритет:\*\*\s*(\S+)', content)
    priority = priority_match.group(1).strip().lower() if priority_match else "normal"

    # Map Russian priorities
    priority_map = {
        "критический": "critical",
        "высокий": "high",
        "нормальный": "normal",
        "низкий": "low"
    }
    priority = priority_map.get(priority, priority)

    # Parse description section
    description = ""
    desc_match = re.search(r'##\s*Описание\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
    if desc_match:
        description = desc_match.group(1).strip()

    # Parse references (images and links)
    references = []
    # Images: ![alt](path)
    for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', content):
        ref_path = match.group(2)
        # Make path relative to task file if not absolute
        if not Path(ref_path).is_absolute():
            ref_path = str(file_path.parent / ref_path)
        references.append(ref_path)

    # Links: [text](path) - only local files
    for match in re.finditer(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)', content):
        ref_path = match.group(2)
        if not ref_path.startswith(('http://', 'https://')):
            if not Path(ref_path).is_absolute():
                ref_path = str(file_path.parent / ref_path)
            references.append(ref_path)

    # Parse context section
    context = ""
    ctx_match = re.search(r'##\s*Контекст\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
    if ctx_match:
        context = ctx_match.group(1).strip()

    return MdTask(
        title=title,
        project=project,
        priority=priority,
        description=description,
        references=references,
        context=context,
        source_file=file_path
    )


def import_tasks_from_inbox(
    inbox_path: Path | str,
    archive: bool = True
) -> List[MdTask]:
    """
    Import all .md tasks from inbox folder.

    Args:
        inbox_path: Path to inbox folder
        archive: Move processed files to archive/ subfolder

    Returns:
        List of parsed tasks
    """
    inbox_path = Path(inbox_path)

    if not inbox_path.exists():
        logger.warning(f"Inbox folder not found: {inbox_path}")
        return []

    tasks = []
    archive_path = inbox_path / "archive"

    for md_file in inbox_path.glob("*.md"):
        if md_file.name.startswith("_"):  # Skip templates
            continue

        task = parse_task_md(md_file)
        if task:
            tasks.append(task)
            logger.info(f"Parsed task: {task.title} ({task.project})")

            # Archive processed file
            if archive:
                archive_path.mkdir(exist_ok=True)
                archived = archive_path / md_file.name
                md_file.rename(archived)
                logger.info(f"Archived: {md_file.name}")

    return tasks


# Template for new tasks
TASK_TEMPLATE = """# Задача: {title}

**Проект:** {project}
**Приоритет:** normal

## Описание
{description}

## Референсы
<!-- Добавь изображения: ![описание](refs/image.png) -->

## Контекст
<!-- Укажи файлы, функции, дополнительную информацию -->
"""


def create_task_template(
    inbox_path: Path | str,
    title: str = "Новая задача",
    project: str = "backpack_hero"
) -> Path:
    """Create a new task template file."""
    inbox_path = Path(inbox_path)
    inbox_path.mkdir(parents=True, exist_ok=True)

    # Generate filename
    safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:30]
    filename = f"{safe_title}.md"
    file_path = inbox_path / filename

    # Handle duplicates
    counter = 1
    while file_path.exists():
        file_path = inbox_path / f"{safe_title}_{counter}.md"
        counter += 1

    content = TASK_TEMPLATE.format(
        title=title,
        project=project,
        description="Опиши задачу здесь..."
    )

    file_path.write_text(content, encoding="utf-8")
    return file_path


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        task = parse_task_md(sys.argv[1])
        if task:
            print(f"Title: {task.title}")
            print(f"Project: {task.project}")
            print(f"Priority: {task.priority}")
            print(f"References: {task.references}")
            print(f"\nPrompt:\n{task.to_prompt()}")
