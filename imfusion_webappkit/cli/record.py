"""Recorder entry point for the `record` command.

`demo` runs a bundled application against a live Python process. `record` does
the opposite: it drives an application once while building, and writes what it
answered to a directory that any static host can serve.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional


def run_record(
    target: str,
    output: Path,
    *,
    bundle: Optional[Path] = None,
    skip_client_build: bool = False,
    title: Optional[str] = None,
) -> int:
    """Record the demo named by `target` into `output`."""
    from ..static_demo.build import build, load_spec
    from ..static_demo.recorder import DemoLimitExceeded, UnsupportedDemoInteraction

    # Recording replays the whole application once per transition, so its own
    # logging would bury the progress and the warnings under a line per frame.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    try:
        spec = load_spec(target)
    except (
        AttributeError,
        FileNotFoundError,
        ImportError,
        TypeError,
        ValueError,
    ) as error:
        print(f"Could not load {target}: {error}")
        return 1

    try:
        report = build(
            spec,
            output,
            bundle=bundle,
            skip_client_build=skip_client_build,
            title=title,
            progress=lambda message: print(f"  {message}"),
        )
    except (DemoLimitExceeded, UnsupportedDemoInteraction) as error:
        # Both describe a scenario that has to change, so the message is the
        # whole answer and a traceback would only bury it.
        print(f"\n{error}")
        return 1

    print("\n" + "\n".join(report))
    print(f"\nOpen {output / 'index.html'} through a web server to try it.")
    return 0
