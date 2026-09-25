"""Load a dataset into everything we ship to be run, and check nothing threw.

Elsewhere the examples are imported and their steps exercised in this process,
and the templates are scaffolded and imported. Neither can see the failure mode
that matters here. The browser loads a file itself and only then tells the
server, so for that window the data model on screen is ahead of the one on the
server. Anything the client sends against an index in between — a compatibility
probe, an algorithm discovery — names a dataset the server does not hold yet,
and raises.

Reproducing that needs both halves really running, so each application is
started as a subprocess and driven by a real browser. The assertion is
deliberately broad: not what the page looks like, only that loading data raised
nothing on either side. That keeps this from becoming a UI test while still
covering the seam the other tests structurally cannot reach.

Skipped unless Playwright's browsers are installed.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "imfusion_webappkit" / "examples" / "sample_image.nii.gz"

# Starting one of these pays for the SDK import and the WebAssembly runtime, and
# the viewer renders through a software rasteriser on a machine with no GPU.
SERVER_TIMEOUT = 240.0
READY_TIMEOUT = 240_000
SETTLE_TIMEOUT = 300_000

# Two datasets, because an example whose action takes a fixed and a moving image
# only sends the indices this guards against once both roles can be filled.
EXAMPLES = {
    "webapp_demo": 1,
    "workflow_demo": 1,
    "annotation_demo": 1,
    "annotation_workflow_demo": 1,
    "registration_demo": 2,
    "registration_workflow_demo": 2,
}

# One image each. No template turns on the algorithm selector or a controller,
# so none of them can send the indices that first motivated this file; what it
# covers for them is the broader claim that importing data raises nothing. The
# MONAI one only reaches for its model behind a Run button, so it stays cheap.
TEMPLATES = {"simple": 1, "workflow": 1, "monai": 1}

FAILURE_MARKERS = ("Traceback (most recent call last)", "Error processing message")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def browser():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            launched = playwright.chromium.launch(
                args=["--use-gl=angle", "--use-angle=swiftshader"]
            )
        except Exception as error:  # noqa: BLE001 - the message names the cause
            pytest.skip(f"Chromium is not installed for Playwright: {error}")
        yield launched
        launched.close()


def _serve(name: str, log: Path, cwd: Path, statement: str):
    """Start an application on a port of its own and wait for it to answer.

    `statement` is the Python that launches it, with a `port` field to fill in,
    so that an example and a scaffolded project can each be started the way its
    own entry point would.
    """
    port = _free_port()
    command = [sys.executable, "-c", statement.format(port=port)]
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT
        )
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + SERVER_TIMEOUT
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    f"{name} exited with {process.returncode}:\n"
                    f"{log.read_text(encoding='utf-8', errors='replace')}"
                )
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return process, url
            except OSError:
                time.sleep(0.5)
        process.kill()
        raise RuntimeError(f"{name} did not start within {SERVER_TIMEOUT}s")


def _reach_import(page) -> None:
    """Advance to wherever this example accepts a dataset.

    A plain application offers its drop zone on the landing page, and the
    toolbar's Import dialog once that page has given way to the viewer. A
    workflow reaches the same control a step or two in, behind a welcome screen.
    Pressing whichever of the three is on offer covers all of them.
    """
    for _ in range(6):
        page.wait_for_timeout(1_000)
        if page.locator("input[type='file']").count():
            return
        for control in (
            page.get_by_role("button", name="Import"),
            page.locator("button.button--workflow-next"),
        ):
            if control.count() and control.first.is_enabled():
                control.first.click()
                break
    raise AssertionError("No import control became reachable")


def _load_datasets(page, count: int) -> None:
    """Import the sample dataset `count` times, waiting out each transfer.

    Waiting matters: the point is to let the client reach the state where it
    believes the server has the data, because that is when it starts sending
    indices for it.
    """
    for _ in range(count):
        _reach_import(page)
        page.locator("input[type='file']").first.set_input_files(str(SAMPLE))
        page.wait_for_function(
            "() => document.querySelector('.busy-bar')?.dataset.active === 'false'",
            timeout=SETTLE_TIMEOUT,
        )
    # Discovery and compatibility probes go out once the transfer lands, so the
    # answer this is watching for arrives after the interface looks idle.
    page.wait_for_timeout(3_000)


def _assert_importing_data_raises_nothing(
    name: str, browser, log: Path, cwd: Path, statement: str, datasets: int
) -> None:
    process, url = _serve(name, log, cwd, statement)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("#header", timeout=READY_TIMEOUT)
        _load_datasets(page, datasets)
    finally:
        page.close()
        process.terminate()
        process.wait(timeout=30)

    output = log.read_text(encoding="utf-8", errors="replace")
    raised = [marker for marker in FAILURE_MARKERS if marker in output]
    assert not raised, f"{name} logged {raised}:\n{output}"
    assert not page_errors, f"{name} reported browser errors: {page_errors}"


@pytest.mark.parametrize("module", sorted(EXAMPLES))
def test_loading_data_into_the_example_raises_nothing(module, browser, tmp_path):
    _assert_importing_data_raises_nothing(
        module,
        browser,
        log=tmp_path / f"{module}.log",
        cwd=REPO,
        statement=(
            f"from imfusion_webappkit.examples.{module} import main; "
            "main(host='127.0.0.1', port={port})"
        ),
        datasets=EXAMPLES[module],
    )


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_loading_data_into_the_scaffolded_template_raises_nothing(
    template, browser, tmp_path
):
    """Run what `webappkit init` hands a new user, not a copy of it.

    A template is the first thing anyone runs, so scaffolding it here and
    serving the generated `app.py` keeps the guard on the same footing as the
    examples: whatever ships is what gets started.
    """
    from imfusion_webappkit.cli import scaffold_project

    project = tmp_path / template
    scaffold_project(project, template=template, title=f"{template.title()} Smoke Test")
    _assert_importing_data_raises_nothing(
        template,
        browser,
        log=tmp_path / f"{template}.log",
        cwd=project,
        statement="import app; app.webapp.run(host='127.0.0.1', port={port})",
        datasets=TEMPLATES[template],
    )
