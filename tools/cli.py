#!/usr/bin/env python3
"""
Ptero-Tool CLI

Единая точка входа для всех инструментов студии.

Usage:
    ptero-tool capture --window "TITLE"
    ptero-tool validate image.png --prompt "Is it working?"
    ptero-tool run project --engine love
    ptero-tool asset --type sprite --prompt "Fire mage"

Install:
    pip install -e .
    # или
    python -m studio.tools.cli
"""

import sys
import argparse


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="ptero-tool",
        description="Ptero Dactyl Studio Toolbox",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  capture   Capture window screenshot
  validate  Check image via Vision AI
  run       Run game project
  asset     Generate assets (WIP)

Examples:
  ptero-tool capture --window "LOVE" --output game.png
  ptero-tool validate game.png --prompt "Is the game running?"
  ptero-tool run backpack_hero --wait 2 --capture
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # === CAPTURE ===
    capture_parser = subparsers.add_parser(
        "capture",
        help="Capture window screenshot"
    )
    capture_parser.add_argument(
        "-w", "--window",
        help="Part of window title"
    )
    capture_parser.add_argument(
        "-o", "--output",
        help="Output path"
    )
    capture_parser.add_argument(
        "--resize",
        help="Resize (WxH)"
    )
    capture_parser.add_argument(
        "--format",
        choices=["png", "jpg"],
        default="png"
    )
    capture_parser.add_argument(
        "--list",
        action="store_true",
        help="Show available windows"
    )
    capture_parser.add_argument(
        "--filter",
        help="Filter for window list"
    )

    # === VALIDATE ===
    validate_parser = subparsers.add_parser(
        "validate",
        help="Check image via Vision AI"
    )
    validate_parser.add_argument(
        "image",
        help="Path to image"
    )
    validate_parser.add_argument(
        "-p", "--prompt",
        required=True,
        help="Question for validation"
    )
    validate_parser.add_argument(
        "-m", "--model",
        choices=["haiku", "sonnet", "opus"],
        default="haiku"
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="JSON output"
    )

    # === RUN ===
    run_parser = subparsers.add_parser(
        "run",
        help="Run game project"
    )
    run_parser.add_argument(
        "project",
        help="Путь к проекту"
    )
    run_parser.add_argument(
        "-e", "--engine",
        choices=["love", "unreal"]
    )
    run_parser.add_argument(
        "-w", "--wait",
        type=float,
        default=0
    )
    run_parser.add_argument(
        "-c", "--capture",
        action="store_true"
    )
    run_parser.add_argument(
        "-o", "--output",
        help="Путь для скриншота"
    )
    run_parser.add_argument(
        "-k", "--kill",
        action="store_true"
    )
    run_parser.add_argument(
        "--timeout",
        type=float,
        default=30
    )
    run_parser.add_argument(
        "--json",
        action="store_true"
    )

    # === ASSET ===
    asset_parser = subparsers.add_parser(
        "asset",
        help="Generate assets (WIP)"
    )
    asset_parser.add_argument(
        "--type",
        choices=["sprite", "tile", "background", "placeholder"],
        default="placeholder"
    )
    asset_parser.add_argument(
        "--prompt",
        help="Description for generation"
    )
    asset_parser.add_argument(
        "-o", "--output",
        help="Output path"
    )

    # Parse args
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Dispatch to tools
    if args.command == "capture":
        from .window_capture.capture import main as capture_main
        # Reconstruct argv for subcommand
        sys.argv = ["ptero-tool capture"]
        if args.window:
            sys.argv.extend(["--window", args.window])
        if args.output:
            sys.argv.extend(["--output", args.output])
        if args.resize:
            sys.argv.extend(["--resize", args.resize])
        if args.format:
            sys.argv.extend(["--format", args.format])
        if args.list:
            sys.argv.append("--list")
        if args.filter:
            sys.argv.extend(["--filter", args.filter])
        return capture_main()

    elif args.command == "validate":
        from .vision_validator.validator import main as validate_main
        sys.argv = ["ptero-tool validate", args.image, "--prompt", args.prompt]
        if args.model:
            sys.argv.extend(["--model", args.model])
        if args.json:
            sys.argv.append("--json")
        return validate_main()

    elif args.command == "run":
        from .game_runner.runner import main as run_main
        sys.argv = ["ptero-tool run", args.project]
        if args.engine:
            sys.argv.extend(["--engine", args.engine])
        if args.wait:
            sys.argv.extend(["--wait", str(args.wait)])
        if args.capture:
            sys.argv.append("--capture")
        if args.output:
            sys.argv.extend(["--output", args.output])
        if args.kill:
            sys.argv.append("--kill")
        if args.timeout:
            sys.argv.extend(["--timeout", str(args.timeout)])
        if args.json:
            sys.argv.append("--json")
        return run_main()

    elif args.command == "asset":
        print("Asset generation not implemented yet")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
