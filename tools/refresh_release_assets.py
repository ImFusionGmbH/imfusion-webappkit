"""Regenerate every committed asset that is derived from the running client.

Before a release, the compiled client, the documentation screenshots, the
landing page images, and the landing page's recorded demo all have to match the
current code. Each has its own tool; this runs them in the order they depend on
each other, stopping at the first failure::

    uv run python tools/refresh_release_assets.py

Pass step names to run a subset, for example after a change that only affects
the landing page::

    uv run python tools/refresh_release_assets.py landing demo

The screenshot steps need ``uv run playwright install chromium`` once, and the
``template-monai`` scenario needs ``monai`` and ``torch`` available.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence, Union

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"
CLIENT_DIR = REPO_ROOT / "imfusion_webappkit" / "static"
LANDING_SHOTS = REPO_ROOT / "shots2x"

# The captures `landing_assets.py` converts; keep in step with its ASSETS.
LANDING_SCENARIOS = (
    "actions",
    "template-simple",
    "template-workflow",
    "template-monai",
    "template-chat",
    "registration",
)

# The screenshot servers serve the compiled client, so it is rebuilt first.
STEPS = ("client", "docs", "landing", "demo")


def run(command: Sequence[str], cwd: Path = REPO_ROOT) -> None:
    print(f"\n$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True, shell=sys.platform == "win32")


def python(script: str, *arguments: str) -> list[str]:
    return [sys.executable, str(TOOLS / script), *arguments]


def main(argv: Union[Sequence[str], None] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "steps",
        nargs="*",
        choices=STEPS,
        help=(
            "client: rebuild imfusion_webappkit/static/dist; "
            "docs: docs/assets/screenshots; "
            "landing: landing/assets images; "
            "demo: landing/public/demo and its poster "
            "(default: all, in this order)"
        ),
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the browser while capturing screenshots",
    )
    args = parser.parse_args(argv)

    selected = [step for step in STEPS if not args.steps or step in args.steps]
    headed = ["--headed"] if args.headed else []

    try:
        if "client" in selected:
            run(["npm", "run", "build"], cwd=CLIENT_DIR)
        if "docs" in selected:
            run(python("generate_screenshots.py", *headed))
        if "landing" in selected:
            run(
                python(
                    "generate_screenshots.py",
                    *LANDING_SCENARIOS,
                    "--scale",
                    "2",
                    "--output",
                    str(LANDING_SHOTS),
                    *headed,
                )
            )
            run(python("landing_assets.py", str(LANDING_SHOTS)))
        if "demo" in selected:
            run(python("build_static_demo.py", "--poster"))
    except subprocess.CalledProcessError as error:
        print(f"\nStopped: exit code {error.returncode}", file=sys.stderr)
        return error.returncode

    print(f"\nRefreshed: {', '.join(selected)}. Review the diff before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
