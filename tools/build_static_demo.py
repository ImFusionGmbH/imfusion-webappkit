"""Record the backend-free demo embedded in the landing page.

This is the recorder from ``imfusion_webappkit.static_demo`` pointed at the
application below, plus the poster the landing page shows before the visitor
presses play. Everything that is not specific to this page lives in the
package, so a reader who wants their own demo can follow the same shape.

Run from the repository root::

    uv run python tools/build_static_demo.py

Output lands in ``landing/public/demo`` and is picked up by the landing build.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import imfusion
import numpy as np

REPO = Path(__file__).resolve().parent.parent
OUTPUT = REPO / "landing" / "public" / "demo"
POSTER = REPO / "landing" / "assets" / "demo-poster.webp"

# Matches the hero screenshot, so the poster and the live frame share a ratio
# and swapping one for the other shifts nothing on the page.
POSTER_SIZE = (1440, 900)

sys.path.insert(0, str(REPO))

from imfusion_webappkit import (  # noqa: E402
    BrandingConfig,
    FloatParameter,
    ImFusionWebApp,
    InfoConfig,
    LayoutConfig,
    SidebarConfig,
    SidePosition,
    ThemeConfig,
    ThemePreset,
    ViewLayout,
    ViewType,
)
from imfusion_webappkit.examples._assets import DEFAULT_LOGO, SAMPLE_IMAGE  # noqa: E402
from imfusion_webappkit.static_demo import ActionScenario, StaticDemoSpec  # noqa: E402
from imfusion_webappkit.static_demo.build import build  # noqa: E402


def apply_threshold(
    imageset: imfusion.SharedImageSet, *, threshold: float
) -> imfusion.SharedImageSet:
    """Label every voxel at or above `threshold`.

    Mirrors the snippet the landing page shows in "What you write", so the
    button in the demo is the one the reader has just read the source of.
    """
    image = imageset[0]
    label = imfusion.SharedImage((image.numpy() >= threshold).astype(np.uint8))
    label.image_to_world_matrix = image.image_to_world_matrix
    label.spacing = image.spacing

    mask = imfusion.SharedImageSet()
    mask.add(label)
    mask.modality = imfusion.Data.Modality.LABEL
    return mask


def build_demo_app() -> ImFusionWebApp:
    """Create the application the demo is recorded from."""
    webapp = ImFusionWebApp(
        title="Image Tools",
        sidebar=SidebarConfig(
            show_datamodel=True, show_views=True, show_display_options=True
        ),
        # Both buttons would need a Python process, and the point of the demo is
        # to have exactly one dead end, clearly explained.
        show_load_button=False,
        show_export_button=False,
        branding=BrandingConfig(logo=DEFAULT_LOGO, favicon=DEFAULT_LOGO),
        info=InfoConfig(
            title="About this demo",
            content=(
                "This is the ImFusion WebAppKit client running with no server "
                "behind it. Viewing, layout and display controls work because "
                "rendering happens in your browser, and **Threshold** runs "
                "here too, through the same WebAssembly SDK.\n\n"
                "- [Documentation](https://imfusiongmbh.github.io/imfusion-webappkit)\n"
                "- [Source](https://github.com/ImFusionGmbH/imfusion-webappkit)\n"
            ),
        ),
        theme=ThemeConfig(preset=ThemePreset.DARK),
        layout=LayoutConfig(
            sidebar_position=SidePosition.LEFT,
            sidebar_width=300,
            initial_view_layout=ViewLayout.AUTO,
            initial_visible_views=(ViewType.MPR, ViewType.THREE_D),
        ),
    )
    webapp.register(
        "Threshold",
        apply_threshold,
        parameters=[
            FloatParameter(
                "threshold", default=100.0, minimum=0.0, maximum=1000.0, step=1.0
            )
        ],
    )

    images = imfusion.io.load(str(SAMPLE_IMAGE))
    webapp.initial_data.add(images[0], "Sample Image")
    return webapp


# Thresholding is a comparison per voxel, which the SDK in the browser can do as
# well as Python can. Handing it to a client-side handler keeps the slider
# continuous, so the demo answers a value nobody thought to record.
spec = StaticDemoSpec(
    app=build_demo_app,
    actions={"Threshold": ActionScenario(handler="threshold")},
    notice=(
        "This page is a recording. The application normally talks to a Python "
        "process, and there is none behind this page, so anything that needs "
        "one has no answer here. Everything else — viewing, layout, display, "
        "and Threshold — is running in your browser."
    ),
)


def capture_poster() -> None:
    """Photograph the assembled demo for the landing page's click-to-load frame.

    Keeping this beside the build means the still the visitor sees is always the
    demo they get when they press play, rather than an older screenshot of a
    differently configured app.
    """
    import functools
    import http.server
    import threading

    from PIL import Image
    from playwright.sync_api import sync_playwright

    root = OUTPUT.parent
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(root)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    width, height = POSTER_SIZE
    raw = POSTER.with_suffix(".png")
    print("Capturing the poster…")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            args=["--use-gl=angle", "--use-angle=swiftshader"]
        )
        page = browser.new_page(
            viewport={"width": width, "height": height}, device_scale_factor=2
        )
        page.goto(f"http://127.0.0.1:{port}/demo/", wait_until="networkidle")
        # The volume renderer keeps refining after the network goes quiet.
        page.wait_for_timeout(15000)
        page.evaluate("() => document.querySelector('.demo-badge')?.remove()")
        page.screenshot(path=str(raw))
        browser.close()
    server.shutdown()

    POSTER.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(raw) as image:
        # Quality 78 to match tools/landing_assets.py: the page shows this at
        # half its pixel size, which hides more compression than it looks like.
        image.convert("RGB").save(POSTER, "WEBP", quality=78, method=6)
    raw.unlink()
    print(
        f"  poster: {POSTER.relative_to(REPO)} ({POSTER.stat().st_size / 1024:.0f} KB)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Reuse the existing client bundle instead of rebuilding it.",
    )
    parser.add_argument(
        "--poster",
        action="store_true",
        help="Also re-capture the landing page poster (needs Playwright and Pillow).",
    )
    arguments = parser.parse_args()

    report = build(
        spec,
        OUTPUT,
        skip_client_build=arguments.skip_build,
        title="Image Tools — ImFusion WebAppKit demo",
        progress=lambda message: print(f"  {message}"),
    )
    print(f"\nDemo written to {OUTPUT.relative_to(REPO)}")
    print("\n".join(f"  {line}" for line in report))

    if arguments.poster:
        capture_poster()


if __name__ == "__main__":
    main()
