"""Build a static demo end to end: compile the client, record, write the site."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
import subprocess
import sys
from typing import Callable, List, Optional

from .recorder import inspect_app, record
from .spec import StaticDemoSpec
from .writer import write

logger = logging.getLogger(__name__)

CLIENT_DIR = Path(__file__).resolve().parent.parent / "static"
# A demo lives in a subdirectory or an iframe, so its asset URLs have to be
# relative. Keeping that in its own output directory means the bundle the Python
# server serves does not quietly change the next time someone records a demo.
CLIENT_BUNDLE = "dist-demo"


def build_client(*, quiet: bool = False) -> Path:
    """Compile the client with relative asset URLs and return its directory."""
    if not quiet:
        logger.info("Building the client bundle")
    subprocess.run(
        ["npm", "run", "build", "--", "--base=./", f"--outDir={CLIENT_BUNDLE}"],
        cwd=CLIENT_DIR,
        check=True,
        shell=sys.platform == "win32",
    )
    return CLIENT_DIR / CLIENT_BUNDLE


def load_spec(target: str) -> StaticDemoSpec:
    """Import a ``module:attribute`` reference to a :class:`StaticDemoSpec`.

    A plain module reference is also accepted when it defines exactly one spec.
    """
    # Split on the last colon, and only when what follows could name something.
    # A Windows path starts with one, so splitting on the first would leave the
    # drive letter as the module.
    module_name, separator, attribute = target.rpartition(":")
    if not separator or not attribute.isidentifier():
        module_name, attribute = target, ""
    if not module_name:
        raise ValueError(f"Invalid demo reference: {target!r}")

    path = Path(module_name)
    if path.suffix == ".py":
        # A file path is friendlier than a dotted name for a project's own
        # build script, which is usually not on the import path.
        if not path.is_file():
            raise FileNotFoundError(f"No such file: {path}")
        sys.path.insert(0, str(path.resolve().parent))
        module = importlib.import_module(path.stem)
    else:
        module = importlib.import_module(module_name)

    if attribute:
        spec = getattr(module, attribute, None)
        if spec is None:
            raise AttributeError(f"{module_name} has no attribute {attribute!r}")
    else:
        candidates = [
            value
            for value in vars(module).values()
            if isinstance(value, StaticDemoSpec)
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"{module_name} defines {len(candidates)} demo specs; name one "
                f"explicitly as '{module_name}:spec'"
            )
        spec = candidates[0]

    if not isinstance(spec, StaticDemoSpec):
        raise TypeError(f"{target} is not a StaticDemoSpec")
    return spec


def build(
    spec: StaticDemoSpec,
    output: Path,
    *,
    bundle: Optional[Path] = None,
    skip_client_build: bool = False,
    title: Optional[str] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> List[str]:
    """Record `spec` and assemble a publishable demo at `output`.

    Returns the size report, and logs any warning the recording raised about
    interactions that will not work on a static host.
    """
    report = progress or (lambda message: logger.info("%s", message))

    client = bundle or (CLIENT_DIR / CLIENT_BUNDLE)
    if not skip_client_build and bundle is None:
        client = build_client()

    report("Reading the application configuration")
    metadata = inspect_app(spec)

    report("Recording interactions from a real application")
    graph = record(spec, metadata, progress=report)

    report(f"Writing the demo to {output}")
    lines = write(
        graph,
        metadata,
        client,
        output,
        notice=spec.notice,
        title=title,
    )
    for warning in graph.warnings:
        logger.warning("%s", warning)
    return lines
