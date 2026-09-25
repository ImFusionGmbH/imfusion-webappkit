"""Generate the documentation screenshots from the bundled example applications.

Run from the repository root::

    uv run playwright install chromium
    uv run python tools/generate_screenshots.py
    uv run python tools/generate_screenshots.py workflow

Every scenario starts an example application in a subprocess, drives the
browser client with Playwright, and writes PNG files into
``docs/assets/screenshots``. The viewer renders through WebGL: pass ``--headed``
when the headless software renderer produces an empty viewport.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator, Sequence, Union

if TYPE_CHECKING:  # Imported lazily so `--serve` does not require Playwright.
    from playwright.sync_api import Locator, Page

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "assets" / "screenshots"

VIEWPORT = {"width": 1440, "height": 900}
SAMPLE_DATASET = "Sample Image"
SEGMENTATION_THRESHOLD = "200"


def _display_path(path: Path) -> str:
    """Path relative to the repository, or absolute if it lies outside it."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


SERVER_STARTUP_TIMEOUT = 240.0
SDK_READY_TIMEOUT = 240_000
STEP_TIMEOUT = 120_000
# The registration pair is 40 MB, and fetching plus loading it in the browser
# takes far longer than a step on a machine that is busy with anything else.
SAMPLE_LOAD_TIMEOUT = 300_000
# Model inference over a whole volume, which runs patch by patch on the CPU when
# no GPU is available.
INFERENCE_TIMEOUT = 1_800_000
# The Web SDK renders asynchronously, so give the views time to settle before
# capturing anything that contains the viewer.
RENDER_SETTLE_MS = 2_500

BROWSER_ARGS = [
    "--hide-scrollbars",
    "--force-color-profile=srgb",
    "--font-render-hinting=none",
    # Allow the software rasterizer when the machine exposes no usable GPU.
    "--enable-unsafe-swiftshader",
]

# Animations and text carets are the only sources of noise between two
# otherwise identical runs.
STABLE_STYLE = """
*, *::before, *::after {
  animation-duration: 0s !important;
  animation-delay: -0.1s !important;
  transition-duration: 0s !important;
  transition-delay: 0s !important;
  caret-color: transparent !important;
}
"""


# --------------------------------------------------------------------------
# Applications served for the scenarios
# --------------------------------------------------------------------------


def _sample_datasets() -> list:
    from imfusion_webappkit import SampleDataset
    from imfusion_webappkit.examples._assets import (
        SAMPLE_IMAGE,
        SAMPLE_IMAGE_THUMBNAIL,
    )

    return [SampleDataset(SAMPLE_DATASET, SAMPLE_IMAGE, SAMPLE_IMAGE_THUMBNAIL)]


def serve_actions(host: str, port: int) -> None:
    """Serve the action, algorithm, and export demo."""
    from imfusion_webappkit.examples.webapp_demo import main

    main(host=host, port=port)


def serve_workflow(host: str, port: int) -> None:
    """Serve the guided segmentation workflow demo."""
    from imfusion_webappkit.examples.workflow_demo import main

    main(host=host, port=port)


def _serve_themed(host: str, port: int, preset: str) -> None:
    from imfusion_webappkit import (
        ImFusionWebApp,
        SidebarConfig,
        ThemeConfig,
        ThemePreset,
    )
    from imfusion_webappkit.examples.webapp_demo import invert_intensity

    webapp = ImFusionWebApp(
        title="Image Tools",
        sidebar=SidebarConfig(),
        show_export_button=True,
        theme=ThemeConfig(preset=ThemePreset(preset)),
        sample_datasets=_sample_datasets(),
    )
    webapp.register("Invert Intensity", invert_intensity)
    webapp.run(host=host, port=port)


def serve_dark_theme(host: str, port: int) -> None:
    """Serve the theme comparison application with the dark preset."""
    _serve_themed(host, port, "dark")


def serve_gray_theme(host: str, port: int) -> None:
    """Serve the theme comparison application with the gray preset."""
    _serve_themed(host, port, "gray")


def serve_light_theme(host: str, port: int) -> None:
    """Serve the theme comparison application with the light preset."""
    _serve_themed(host, port, "light")


def _serve_template(host: str, port: int, template: str, title: str) -> None:
    """Scaffold a bundled template into a temporary project and serve it.

    Templates ship without sample datasets, and the workflow ones hide the load
    button, so a fresh session would have nothing to show. Seeding
    ``initial_data`` hands every session a copy of the bundled image instead,
    which is all these screenshots need.

    The MONAI template serves without torch or MONAI installed because its
    inference imports sit inside the functions that use them; only pressing its
    run button would reach them.
    """
    import importlib
    import tempfile

    import imfusion

    from imfusion_webappkit.cli.scaffold import scaffold_project
    from imfusion_webappkit.examples._assets import SAMPLE_IMAGE

    project = Path(tempfile.mkdtemp(prefix=f"webappkit-{template}-")) / template
    scaffold_project(project, template=template, title=title)

    sys.path.insert(0, str(project))
    module = importlib.import_module("app")
    module.webapp.initial_data.add(
        imfusion.io.load(str(SAMPLE_IMAGE))[0], SAMPLE_DATASET
    )
    module.webapp.run(host=host, port=port)


def serve_simple_template(host: str, port: int) -> None:
    """Serve the `simple` template: one action with a declared parameter."""
    _serve_template(host, port, "simple", "Image Processor")


def serve_workflow_template(host: str, port: int) -> None:
    """Serve the `workflow` template: a guided segmentation."""
    _serve_template(host, port, "workflow", "Segmentation Study")


def serve_monai_template(host: str, port: int) -> None:
    """Serve the `monai` template: inference from the MONAI Model Zoo."""
    _serve_template(host, port, "monai", "MONAI Inference")


def serve_chat_template(host: str, port: int) -> None:
    """Serve the `chat` template: an assistant grounded in the viewer."""
    _serve_template(host, port, "chat", "Imaging Assistant")


def serve_registration(host: str, port: int) -> None:
    """Serve the guided two-image registration demo."""
    from imfusion_webappkit.examples.registration_workflow_demo import main

    main(host=host, port=port)


# --------------------------------------------------------------------------
# Browser session
# --------------------------------------------------------------------------


class Session:
    """Drive one browser page and write its screenshots."""

    def __init__(self, page: "Page", url: str, output_dir: Path):
        self.page = page
        self.url = url
        self.output_dir = output_dir

    # Navigation and state ---------------------------------------------------

    def open(self) -> None:
        """Load the application and wait until the client is connected."""
        self.page.goto(self.url, wait_until="domcontentloaded")
        # The header exists only once the Web SDK WASM module is ready.
        self.page.wait_for_selector("#header", timeout=SDK_READY_TIMEOUT)
        self.page.wait_for_selector(
            ".status-indicator.status-connected", timeout=STEP_TIMEOUT
        )
        self.page.add_style_tag(content=STABLE_STYLE)

    def load_sample_dataset(self, name: str = SAMPLE_DATASET) -> None:
        """Load a bundled sample dataset from its sample-dataset card.

        The card is matched on its text rather than by role, because its
        accessible name also takes in the thumbnail.
        """
        self.page.locator(".landing-page__examples-panel button").filter(
            has_text=name
        ).click()
        self.page.wait_for_selector(".data-item", timeout=SAMPLE_LOAD_TIMEOUT)
        self.page.wait_for_selector(
            ".loading-overlay", state="detached", timeout=SAMPLE_LOAD_TIMEOUT
        )
        self.settle()

    def settle(self, milliseconds: int = RENDER_SETTLE_MS) -> None:
        """Wait for the viewer and any pending state update to catch up."""
        self.page.wait_for_timeout(milliseconds)

    def next_step(self, title: str) -> None:
        """Advance the workflow and wait for the expected step to be shown."""
        self.page.wait_for_selector(
            ".button--workflow-next:not([disabled])",
            timeout=STEP_TIMEOUT,
        )
        self.page.locator(".button--workflow-next").click()
        self.page.wait_for_selector(
            f'.workflow-panel__step-title:text-is("{title}")', timeout=STEP_TIMEOUT
        )

    @contextmanager
    def dialog(self, button: str) -> Iterator["Locator"]:
        """Open a header dialog, yield it, and close it again.

        Header buttons carry an icon whose glyph is part of their accessible
        name, so they are matched by substring rather than exactly.
        """
        self.page.locator("#header").get_by_role("button", name=button).click()
        modal = self.page.locator(".modal[role='dialog']")
        modal.wait_for(state="visible", timeout=STEP_TIMEOUT)
        self.settle(400)
        try:
            yield modal
        finally:
            self.page.keyboard.press("Escape")
            modal.wait_for(state="detached", timeout=STEP_TIMEOUT)

    def sidebar_section(self, title: str) -> "Locator":
        """Return the sidebar section with the given title."""
        return self.page.locator(".sidebar__section").filter(
            has=self.page.locator(f'.sidebar__title:text-is("{title}")')
        )

    # Capture ---------------------------------------------------------------

    def shot(self, name: str) -> None:
        """Capture the whole viewport."""
        path = self._path(name)
        self.page.screenshot(path=path)
        print(f"  wrote {_display_path(path)}")

    def shot_element(self, target: Union[str, "Locator"], name: str) -> None:
        """Capture a single element, cropped to its bounding box."""
        locator = self.page.locator(target) if isinstance(target, str) else target
        path = self._path(name)
        locator.screenshot(path=path)
        print(f"  wrote {_display_path(path)}")

    def _path(self, name: str) -> Path:
        return self.output_dir / f"{name}.png"


# --------------------------------------------------------------------------
# Scenario captures
# --------------------------------------------------------------------------


def capture_actions(session: Session) -> None:
    """Capture the landing page, viewer, sidebar, and header dialogs."""
    session.open()
    session.shot("landing-page")
    session.shot_element(".landing-page__examples-panel", "sample-datasets")

    session.load_sample_dataset()
    session.shot("app-overview")
    session.shot_element("#header", "header")
    session.shot_element(".sidebar", "sidebar")
    session.shot_element(session.sidebar_section("Algorithms"), "algorithms-panel")

    with session.dialog("Slow Processing") as modal:
        session.shot_element(modal, "action-parameters")
    with session.dialog("Morphological Operations") as modal:
        session.shot_element(modal, "algorithm-controls")
    with session.dialog("About") as modal:
        session.shot_element(modal, "info-dialog")
    with session.dialog("Export") as modal:
        session.shot_element(modal, "export-dialog")


def capture_workflow(session: Session) -> None:
    """Walk through the guided workflow and capture every step type."""
    session.open()
    session.shot("workflow-welcome")

    session.next_step("Select Image")
    session.shot_element(".workflow-panel", "workflow-input-selection")
    session.load_sample_dataset()

    session.next_step("Configure Segmentation")
    session.page.locator(".workflow-panel input[type='number']").fill(
        SEGMENTATION_THRESHOLD
    )
    session.settle(500)
    session.shot_element(".workflow-panel", "workflow-parameters")

    session.next_step("Segment Image")
    session.page.wait_for_selector(
        ".workflow-step-processing--complete", timeout=STEP_TIMEOUT
    )

    session.next_step("Correct Segmentation")
    session.settle()
    session.shot("workflow-brush")

    session.next_step("Segmentation Summary")
    session.shot_element(".workflow-panel", "workflow-custom-step")

    session.next_step("Review Result")
    session.shot_element(".workflow-panel", "workflow-validation")
    session.page.get_by_role("button", name="Accept").click()

    session.next_step("Export Segmentation")
    session.shot_element(".workflow-panel", "workflow-export")


def _capture_theme(session: Session, name: str) -> None:
    session.open()
    session.load_sample_dataset()
    session.shot(name)


def capture_dark_theme(session: Session) -> None:
    """Capture the dark preset with data loaded."""
    _capture_theme(session, "theme-dark")


def capture_gray_theme(session: Session) -> None:
    """Capture the gray preset with data loaded."""
    _capture_theme(session, "theme-gray")


def capture_light_theme(session: Session) -> None:
    """Capture the light preset with data loaded."""
    _capture_theme(session, "theme-light")


def capture_simple_template(session: Session) -> None:
    """Capture the parameter dialog the `simple` template declares."""
    session.open()
    session.settle()
    with session.dialog("Segment Image") as modal:
        session.shot_element(modal, "template-simple")


def capture_workflow_template(session: Session) -> None:
    """Capture the `workflow` template at its review step.

    The review step is reached rather than shown directly because it depends on
    a corrected label map, so the segmentation has to run on the way there.
    """
    session.open()
    session.next_step("Select Image")
    session.next_step("Configure Segmentation")
    session.next_step("Segment Image")
    session.page.wait_for_selector(
        ".workflow-step-processing--complete", timeout=STEP_TIMEOUT
    )
    session.next_step("Correct Segmentation")
    session.next_step("Review Result")
    session.settle(500)
    session.shot_element(".workflow-panel", "template-workflow")


def capture_monai_template(session: Session) -> None:
    """Capture the `monai` template at its input step, then at its result.

    The model runs for real, so the result view shows its label map over the
    source CT. The run is started from its own button because the template's
    processing step sets `auto_run=False`, and it is given a longer timeout than
    other steps because inference falls back to the CPU without a GPU.
    """
    session.open()
    session.next_step("Select Model Input")
    session.settle(500)
    session.shot_element(".workflow-panel", "template-monai")

    session.next_step("Run Model")
    try:
        import monai  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        print("  skipping template-monai-result: torch/monai are not installed")
        return
    session.page.get_by_role("button", name="Run Segmentation").click()
    session.page.wait_for_selector(
        ".workflow-step-processing--complete", timeout=INFERENCE_TIMEOUT
    )
    session.next_step("Review Result")
    session.settle()
    session.shot("template-monai-result")


def capture_chat_template(session: Session) -> None:
    """Capture the `chat` template after a short exchange about the sample."""
    session.open()
    session.page.wait_for_selector(".data-item", timeout=SAMPLE_LOAD_TIMEOUT)
    session.next_step("Assistant")
    prompt = session.page.get_by_placeholder("Type your message here")
    prompt.fill("Describe the selected dataset.")
    session.settle(400)
    prompt.press("Enter")
    session.page.get_by_text("This starter replies without a model.").wait_for(
        timeout=STEP_TIMEOUT
    )
    session.settle(500)
    session.shot_element(".workflow-panel", "template-chat")


def capture_registration(session: Session) -> None:
    """Capture the two-image registration demo before and after it runs.

    ``registration-before`` shows the loaded, still-unregistered pair on its
    own so the landing page can illustrate the starting point with just two
    images. ``registration`` is the same demo after it runs, for the guide.
    """
    session.open()
    session.load_sample_dataset("Brain MRI pair")
    # The sample card plus two role selectors overflow the panel at this
    # viewport, so bring the assignment stage into view: that is the part the
    # guide is documenting.
    session.page.locator(".workflow-step-stage").last.scroll_into_view_if_needed()
    session.settle(400)
    session.shot_element(".workflow-panel", "registration-inputs")
    session.shot("registration-before")

    session.next_step("Register Images")
    session.page.wait_for_selector(
        ".workflow-step-processing--complete", timeout=STEP_TIMEOUT
    )
    session.settle()
    session.shot("registration")


@dataclass(frozen=True)
class Scenario:
    """An application to serve and the screenshots to take from it."""

    name: str
    description: str
    serve: Callable[[str, int], None]
    capture: Callable[[Session], None]


SCENARIOS: dict[str, Scenario] = {
    scenario.name: scenario
    for scenario in (
        Scenario(
            "actions",
            "Action demo: landing page, viewer, sidebar, and dialogs",
            serve_actions,
            capture_actions,
        ),
        Scenario(
            "workflow",
            "Guided workflow demo: one screenshot per step type",
            serve_workflow,
            capture_workflow,
        ),
        Scenario(
            "theme-dark",
            "Dark theme preset",
            serve_dark_theme,
            capture_dark_theme,
        ),
        Scenario(
            "theme-gray",
            "Gray theme preset",
            serve_gray_theme,
            capture_gray_theme,
        ),
        Scenario(
            "theme-light",
            "Light theme preset",
            serve_light_theme,
            capture_light_theme,
        ),
        Scenario(
            "template-simple",
            "Scaffold from the simple template: the declared parameter dialog",
            serve_simple_template,
            capture_simple_template,
        ),
        Scenario(
            "template-workflow",
            "Scaffold from the workflow template: the parameter step",
            serve_workflow_template,
            capture_workflow_template,
        ),
        Scenario(
            "template-monai",
            "Scaffold from the MONAI template: the inference steps",
            serve_monai_template,
            capture_monai_template,
        ),
        Scenario(
            "template-chat",
            "Scaffold from the chat template: a short assistant exchange",
            serve_chat_template,
            capture_chat_template,
        ),
        Scenario(
            "registration",
            "Two-image registration demo: named input roles and the result",
            serve_registration,
            capture_registration,
        ),
    )
}


# --------------------------------------------------------------------------
# Server process
# --------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_for_server(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + SERVER_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"The application exited with code {process.returncode} before "
                "it served a configuration."
            )
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    raise TimeoutError(f"{url} did not respond within {SERVER_STARTUP_TIMEOUT}s")


@contextmanager
def _serve(scenario: Scenario, host: str, port: int) -> Iterator[str]:
    command = [
        sys.executable,
        "-u",
        str(Path(__file__).resolve()),
        "--serve",
        scenario.name,
        "--host",
        host,
        "--port",
        str(port),
    ]
    process = subprocess.Popen(command, cwd=REPO_ROOT)
    try:
        _wait_for_server(f"http://{host}:{port}/config", process)
        yield f"http://{host}:{port}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


def generate(
    scenarios: Sequence[Scenario],
    *,
    output_dir: Path,
    headless: bool,
    scale: float,
    width: int = VIEWPORT["width"],
) -> None:
    """Capture every requested scenario into ``output_dir``."""
    from playwright.sync_api import sync_playwright

    viewport = {**VIEWPORT, "width": width}
    output_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, args=BROWSER_ARGS)
        try:
            for scenario in scenarios:
                print(f"{scenario.name}: {scenario.description}")
                with _serve(scenario, "127.0.0.1", _free_port()) as url:
                    context = browser.new_context(
                        viewport=viewport, device_scale_factor=scale
                    )
                    page = context.new_page()
                    page.set_default_timeout(STEP_TIMEOUT)
                    page.on("pageerror", lambda error: print(f"  [page] {error}"))
                    try:
                        scenario.capture(Session(page, url, output_dir))
                    finally:
                        context.close()
        finally:
            browser.close()


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "scenarios",
        nargs="*",
        choices=list(SCENARIOS),
        help="Scenarios to capture (default: all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the generated PNG files",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the browser window instead of rendering headless",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Device scale factor; 2 produces high-density images",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=VIEWPORT["width"],
        help=(
            "Viewport width in CSS pixels; narrow values are useful for "
            "checking how the layout copes with a cramped window"
        ),
    )
    parser.add_argument("--serve", help=argparse.SUPPRESS)
    parser.add_argument("--host", default="127.0.0.1", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=8000, help=argparse.SUPPRESS)
    return parser


def main(argv: Union[Sequence[str], None] = None) -> int:
    """Serve one scenario or capture the requested scenarios."""
    args = build_parser().parse_args(argv)
    if args.serve:
        SCENARIOS[args.serve].serve(args.host, args.port)
        return 0

    selected = [SCENARIOS[name] for name in args.scenarios or SCENARIOS]
    generate(
        selected,
        output_dir=args.output,
        headless=not args.headed,
        scale=args.scale,
        width=args.width,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
