"""Environment diagnostics for the `doctor` command."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import json
from pathlib import Path
import socket
import subprocess
import sys
from typing import Callable, Iterable, Optional

from ._constants import DEFAULT_HOST, DEFAULT_PORT, PACKAGE_NAME


@dataclass(frozen=True)
class CheckResult:
    """One environment diagnostic result."""

    status: str
    name: str
    message: str
    hint: Optional[str] = None


def _python_check() -> CheckResult:
    version = ".".join(str(value) for value in sys.version_info[:3])
    if sys.version_info >= (3, 10):
        return CheckResult("ok", "Python", version)
    return CheckResult(
        "fail",
        "Python",
        f"{version} is unsupported",
        "Install Python 3.10 or newer.",
    )


def _package_check() -> CheckResult:
    try:
        version = metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return CheckResult(
            "fail",
            "WebAppKit package",
            "distribution metadata was not found",
            "Install the package with `uv pip install -e .` or from a wheel.",
        )
    return CheckResult("ok", "WebAppKit package", version)


def _frontend_check() -> CheckResult:
    static_dir = Path(__file__).resolve().parent.parent / "static" / "dist"
    index = static_dir / "index.html"
    assets = static_dir / "assets"
    has_javascript = assets.is_dir() and any(assets.glob("main-*.js"))
    has_wasm = assets.is_dir() and any(assets.glob("*.wasm"))
    missing = []
    if not index.is_file():
        missing.append("index.html")
    if not has_javascript:
        missing.append("JavaScript bundle")
    if not has_wasm:
        missing.append("Web SDK WASM")
    if missing:
        return CheckResult(
            "fail",
            "Frontend bundle",
            f"missing {', '.join(missing)}",
            "Run `npm ci` and `npm run build` in imfusion_webappkit/static.",
        )
    return CheckResult("ok", "Frontend bundle", str(static_dir))


def _port_check(host: str, port: int) -> CheckResult:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, port))
    except OSError as exc:
        return CheckResult(
            "fail",
            "Server address",
            f"{host}:{port} is unavailable ({exc})",
            "Stop the process using the port or pass `--port` with another value.",
        )
    return CheckResult("ok", "Server address", f"{host}:{port} is available")


def _imfusion_check() -> CheckResult:
    script = """
import json
import imfusion

features = ["dicom", "registration"]
missing = [name for name in features if not hasattr(imfusion, name)]
algorithms = len(imfusion.algorithm.list_available())
framework_info = imfusion.info()
print(json.dumps({
    "version": getattr(imfusion, "__version__", "unknown"),
    "algorithms": algorithms,
    "missing": missing,
    "opengl": str(getattr(framework_info, "opengl", "unknown")),
}))
"""
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            "fail",
            "ImFusion SDK",
            "initialization timed out",
            "Check GPU/OpenGL availability and the ImFusion license configuration.",
        )
    if completed.returncode:
        details = [
            line.strip()
            for line in (completed.stderr or completed.stdout).splitlines()
            if line.strip()
        ]
        message = details[-1] if details else "initialization failed"
        return CheckResult(
            "fail",
            "ImFusion SDK",
            message,
            "Verify the SDK installation, licenses, and OpenGL context. "
            "Windows RDP and headless Linux sessions may need additional setup.",
        )
    try:
        details = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return CheckResult(
            "fail",
            "ImFusion SDK",
            "returned an unreadable diagnostic response",
        )
    missing = details["missing"]
    if missing:
        return CheckResult(
            "fail",
            "ImFusion SDK",
            f"missing feature modules: {', '.join(missing)}",
            "Install the DICOM, machine-learning, and registration SDK packages.",
        )
    return CheckResult(
        "ok",
        "ImFusion SDK",
        f"version {details['version']}; {details['algorithms']} algorithms; "
        f"OpenGL {details['opengl']}",
    )


def run_doctor(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    checks: Optional[Iterable[Callable[[], CheckResult]]] = None,
) -> int:
    """Run environment checks and return a process exit code."""
    selected_checks = (
        list(checks)
        if checks is not None
        else [
            _python_check,
            _package_check,
            _frontend_check,
            _imfusion_check,
            lambda: _port_check(host, port),
        ]
    )
    results = [check() for check in selected_checks]
    print("ImFusion WebAppKit doctor")
    print()
    for result in results:
        print(f"[{result.status}] {result.name}: {result.message}")
        if result.hint:
            print(f"       Hint: {result.hint}")
    failures = sum(result.status == "fail" for result in results)
    print()
    if failures:
        print(f"{failures} check(s) failed.")
        return 1
    print("All checks passed.")
    return 0
