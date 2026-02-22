"""
Game Runner Tool

Запуск и управление игровыми процессами.
Поддерживает LÖVE 2D и Unreal Engine.

Usage:
    from studio.tools.game_runner import run_game

    process = run_game(project="backpack_hero", engine="love")
    process.capture()
    process.kill()
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal
import logging

logger = logging.getLogger("game_runner")

# Пути к движкам (можно переопределить через env)
LOVE_PATH = os.environ.get(
    "LOVE_PATH",
    "C:/Program Files/LOVE/love.exe"
)

EngineType = Literal["love", "unreal"]


@dataclass
class GameProcess:
    """Запущенный игровой процесс."""
    pid: int
    engine: EngineType
    project: str
    project_path: Path
    _process: Optional[subprocess.Popen] = None

    def is_running(self) -> bool:
        """Проверить что процесс запущен."""
        if self._process is None:
            return False
        return self._process.poll() is None

    def capture(self, output: Optional[str] = None) -> Optional[str]:
        """Сделать скриншот окна игры."""
        try:
            from tools.window_capture import capture_window
        except ImportError:
            from ..window_capture import capture_window

        # Определить заголовок окна
        if self.engine == "love":
            window_title = "LÖVE"
        else:
            window_title = self.project

        return capture_window(window=window_title, output=output)

    def kill(self) -> None:
        """Завершить процесс."""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def wait(self, seconds: float) -> None:
        """Подождать N секунд."""
        time.sleep(seconds)


def detect_engine(project_path: Path) -> Optional[EngineType]:
    """Определить движок по структуре проекта."""
    if (project_path / "main.lua").exists():
        return "love"
    if (project_path / "conf.lua").exists():
        return "love"

    # Поиск .uproject
    uproject_files = list(project_path.glob("*.uproject"))
    if uproject_files:
        return "unreal"

    return None


def run_game(
    project: str,
    engine: Optional[EngineType] = None,
    wait: float = 0,
    timeout: float = 30
) -> Optional[GameProcess]:
    """
    Запустить игру.

    Args:
        project: Путь к проекту или имя (будет искать в известных местах)
        engine: Движок (love, unreal) или автоопределение
        wait: Время ожидания после запуска (секунды)
        timeout: Таймаут запуска (секунды)

    Returns:
        GameProcess или None при ошибке
    """
    # Найти проект
    project_path = Path(project)

    if not project_path.is_absolute():
        # Искать в известных местах
        search_paths = [
            Path("C:/Ptero Dactyl Games") / project,
            Path.cwd() / project,
            Path.cwd().parent / project
        ]

        for p in search_paths:
            if p.exists():
                project_path = p
                break

    if not project_path.exists():
        logger.error(f"Project not found: {project}")
        return None

    project_path = project_path.resolve()

    # Определить движок
    if engine is None:
        engine = detect_engine(project_path)
        if engine is None:
            logger.error(f"Cannot detect engine for: {project_path}")
            return None

    # Запустить в зависимости от движка
    if engine == "love":
        return _run_love(project_path, wait, timeout)
    elif engine == "unreal":
        return _run_unreal(project_path, wait, timeout)
    else:
        logger.error(f"Unknown engine: {engine}")
        return None


def _run_love(project_path: Path, wait: float, timeout: float) -> Optional[GameProcess]:
    """Запустить LÖVE проект."""
    if not Path(LOVE_PATH).exists():
        logger.error(f"LÖVE not found at: {LOVE_PATH}")
        logger.error("Set LOVE_PATH environment variable")
        return None

    try:
        process = subprocess.Popen(
            [LOVE_PATH, str(project_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Подождать запуск
        if wait > 0:
            time.sleep(wait)

        # Проверить что процесс запустился
        if process.poll() is not None:
            stderr = process.stderr.read().decode()
            logger.error(f"LÖVE failed to start: {stderr}")
            return None

        return GameProcess(
            pid=process.pid,
            engine="love",
            project=project_path.name,
            project_path=project_path,
            _process=process
        )

    except Exception as e:
        logger.exception(f"Failed to start LÖVE: {e}")
        return None


def _run_unreal(project_path: Path, wait: float, timeout: float) -> Optional[GameProcess]:
    """Запустить Unreal проект через PIE."""
    # Unreal запускается через MCP, не subprocess
    # Просто возвращаем объект для API compatibility

    logger.warning("Unreal support requires MCP server to be running")

    return GameProcess(
        pid=0,  # PIE не имеет отдельного PID
        engine="unreal",
        project=project_path.name,
        project_path=project_path,
        _process=None
    )


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Запуск и управление игровыми процессами",
        prog="ptero-tool run"
    )

    parser.add_argument(
        "project",
        help="Путь к проекту"
    )
    parser.add_argument(
        "-e", "--engine",
        choices=["love", "unreal"],
        help="Движок (по умолчанию автоопределение)"
    )
    parser.add_argument(
        "-w", "--wait",
        type=float,
        default=0,
        help="Ждать N секунд после запуска"
    )
    parser.add_argument(
        "-c", "--capture",
        action="store_true",
        help="Сделать скриншот после wait"
    )
    parser.add_argument(
        "-o", "--output",
        help="Путь для скриншота"
    )
    parser.add_argument(
        "-k", "--kill",
        action="store_true",
        help="Завершить процесс после capture"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="Таймаут запуска"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывод в JSON формате"
    )

    args = parser.parse_args()

    # Запустить
    process = run_game(
        project=args.project,
        engine=args.engine,
        wait=args.wait,
        timeout=args.timeout
    )

    if process is None:
        print("Failed to start game", file=sys.stderr)
        return 1

    result = {
        "pid": process.pid,
        "engine": process.engine,
        "project": process.project,
        "running": process.is_running()
    }

    # Захват
    if args.capture:
        screenshot = process.capture(output=args.output)
        if screenshot:
            result["screenshot"] = screenshot

    # Завершение
    if args.kill:
        process.kill()
        result["running"] = False

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Started: {process.project} (PID: {process.pid})")
        if "screenshot" in result:
            print(f"Screenshot: {result['screenshot']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
