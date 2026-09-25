"""Command-line tools for diagnosing, trying, and scaffolding WebAppKit apps."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from imfusion_webappkit.config import ThemePreset

from ._constants import (
    AVAILABLE_TEMPLATES,
    DEFAULT_HOST,
    DEFAULT_PORT,
    PACKAGE_NAME,
    TEMPLATE_DESCRIPTIONS,
)
from .demo import run_demo
from .doctor import CheckResult, run_doctor
from .record import run_record
from .scaffold import run_init, scaffold_project, scaffold_simple_project

__all__ = [
    "AVAILABLE_TEMPLATES",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "PACKAGE_NAME",
    "TEMPLATE_DESCRIPTIONS",
    "CheckResult",
    "run_doctor",
    "run_demo",
    "run_init",
    "run_record",
    "scaffold_project",
    "scaffold_simple_project",
    "build_parser",
    "main",
]


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="imfusion-webappkit",
        description="Build and diagnose ImFusion WebAppKit applications.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check the local environment")
    doctor.add_argument("--host", default=DEFAULT_HOST)
    doctor.add_argument("--port", type=int, default=DEFAULT_PORT)

    demo = subparsers.add_parser(
        "demo", help="Launch the bundled demo against a live Python process"
    )
    demo.add_argument("--host", default=DEFAULT_HOST)
    demo.add_argument("--port", type=int, default=DEFAULT_PORT)
    demo.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the demo in the default browser",
    )
    demo.add_argument(
        "--workflow",
        action="store_true",
        help="Launch the guided workflow demo instead of the action demo",
    )

    record = subparsers.add_parser(
        "record",
        help="Record an application as a static demo that needs no Python",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "The demo reference names a StaticDemoSpec, either as an importable\n"
            "'module:attribute' or as a 'path/to/file.py:attribute'. The attribute\n"
            "may be left out when the module defines exactly one spec.\n"
            "\n"
            "Example:\n"
            "  imfusion-webappkit record demos/threshold.py -o dist/threshold"
        ),
    )
    record.add_argument("demo", help="Reference to the StaticDemoSpec to record")
    record.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Directory to write the demo into. It is replaced if it exists.",
    )
    record.add_argument("--title", help="Title for the recorded page")
    record.add_argument(
        "--bundle",
        type=Path,
        help="Use an already built client bundle instead of building one",
    )
    record.add_argument(
        "--skip-client-build",
        action="store_true",
        help="Reuse the last client build, for repeated recordings",
    )

    initialize = subparsers.add_parser(
        "init",
        help="Create an application starter project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Available templates:\n"
        + "\n".join(
            f"  {name:<13} {description}"
            for name, description in TEMPLATE_DESCRIPTIONS.items()
        ),
    )
    initialize.add_argument("destination", type=Path)
    initialize.add_argument(
        "--template",
        choices=AVAILABLE_TEMPLATES,
        default="simple",
        help="Starter application style (default: simple)",
    )
    initialize.add_argument("--title", help="Application title shown in the browser")
    initialize.add_argument(
        "--theme",
        choices=[preset.value for preset in ThemePreset],
        default=ThemePreset.DARK.value,
        help="Visual theme preset (default: dark)",
    )
    initialize.add_argument(
        "--force",
        action="store_true",
        help="Overwrite known template files that already exist",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the selected CLI command."""
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return run_doctor(args.host, args.port)
    if args.command == "demo":
        return run_demo(
            args.host,
            args.port,
            open_browser=not args.no_open,
            workflow=args.workflow,
        )
    if args.command == "record":
        return run_record(
            args.demo,
            args.output,
            bundle=args.bundle,
            skip_client_build=args.skip_client_build,
            title=args.title,
        )
    if args.command == "init":
        return run_init(
            args.destination,
            template=args.template,
            title=args.title,
            theme=args.theme,
            force=args.force,
        )
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
