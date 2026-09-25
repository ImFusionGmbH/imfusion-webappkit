"""Bundled demo launcher for the `demo` command."""

from __future__ import annotations

import threading
import webbrowser


def _open_browser_later(url: str) -> None:
    timer = threading.Timer(1.0, webbrowser.open, args=(url,))
    timer.daemon = True
    timer.start()


def run_demo(
    host: str,
    port: int,
    *,
    open_browser: bool = True,
    workflow: bool = False,
) -> int:
    """Launch a bundled demo.

    By default this starts the parameterized-action demo. Pass ``workflow=True``
    to launch the guided workflow demo instead.
    """
    if workflow:
        from ..examples.workflow_demo import main as run_example

        label = "bundled workflow demo"
    else:
        from ..examples.webapp_demo import main as run_example

        label = "bundled demo"

    url = f"http://{host}:{port}"
    print(f"Starting the {label} at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        _open_browser_later(url)
    run_example(host=host, port=port)
    return 0
