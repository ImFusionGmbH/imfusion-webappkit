"""Open the recorded landing-page demo in a browser and use it.

Everything else about a static demo can be checked without a browser, except
the one thing that matters: whether the published directory actually works when
a visitor loads it. This drives the real bundle against the real recording over
HTTP, so a break in the manifest, the payload URLs, or the replay shows up here
rather than on the website.

Skipped unless the demo has been built (``uv run python
tools/build_static_demo.py``) and Playwright's browsers are installed.
"""

import functools
import http.server
from pathlib import Path
import threading

import pytest

DEMO = Path(__file__).resolve().parent.parent / "landing" / "public" / "demo"

pytestmark = pytest.mark.skipif(
    not (DEMO / "fixtures" / "manifest.json").is_file(),
    reason="The landing demo has not been recorded",
)


@pytest.fixture(scope="module")
def demo_url():
    """Serve the recorded demo the way a static host would."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(DEMO.parent)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/demo/"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def page(demo_url):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                args=["--use-gl=angle", "--use-angle=swiftshader"]
            )
        except Exception as error:  # noqa: BLE001 - the message names the cause
            pytest.skip(f"Chromium is not installed for Playwright: {error}")
        opened = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        opened.on("pageerror", lambda error: errors.append(str(error)))
        opened.goto(demo_url)
        # The WebAssembly SDK is 15 MB and decodes a volume before the data
        # model has anything in it.
        opened.wait_for_selector("text=Sample Image", timeout=180_000)
        yield opened
        assert not errors, f"The page reported errors: {errors}"
        browser.close()


def _run_threshold(page, dataset=None):
    page.get_by_role("button", name="Threshold").first.click()
    dialog = page.locator(".modal")
    if dataset is not None:
        # The picker is a web-ui Select, a combobox button rather than a <select>.
        dialog.get_by_role("combobox", name="Image").click()
        page.get_by_role("option", name=dataset, exact=True).click()
    dialog.get_by_role("button", name="Run").click()


def test_the_recording_loads_its_dataset(page):
    assert page.locator(".demo-badge").is_visible()
    assert page.locator("text=Sample Image").count() >= 1


def test_threshold_runs_in_the_browser(page):
    _run_threshold(page)

    # Named the way the server would have named it, because the handler asks the
    # same helper the client uses for a live result.
    page.wait_for_selector("text=Sample Image — Threshold", timeout=120_000)


def test_a_result_can_be_used_as_the_next_input(page):
    """A recorded demo whose action runs here is not limited to one step."""
    # The page fixture is shared, and reloading the SDK under software rendering
    # costs minutes, so a result left by an earlier test is reused.
    if not page.locator("text=Sample Image — Threshold").count():
        _run_threshold(page, dataset="Sample Image")
        page.wait_for_selector("text=Sample Image — Threshold", timeout=120_000)
    _run_threshold(page, dataset="Sample Image — Threshold")
    page.wait_for_selector("text=Sample Image — Threshold — Threshold", timeout=120_000)
