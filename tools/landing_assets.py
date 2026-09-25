"""Derive the landing page's images from generated screenshots.

The landing page shows every image at half its pixel size so it stays sharp on
high-density displays, and shows several of them as small thumbnails that only
work when cropped to the part carrying content. Both of those are decisions
about the page rather than about the documentation, so they live here instead of
in the screenshot generator.

Capture the sources at twice the display size first, then convert them::

    uv run python tools/generate_screenshots.py actions template-simple \\
        template-workflow template-monai template-chat registration \\
        --scale 2 --output shots2x
    uv run python tools/landing_assets.py shots2x

Sources missing from the input directory are reported and skipped, so a single
image can be refreshed without recapturing the rest.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = REPO_ROOT / "landing" / "assets"

# Boxes are in captured pixels, so they assume `--scale 2`.
CROP_SCALE = 2


@dataclass(frozen=True)
class Asset:
    """One landing page image and the capture it comes from."""

    source: str
    name: str
    # Left, top, right, bottom in captured pixels; None keeps the whole frame.
    crop: Optional[tuple[int, int, int, int]] = None
    # Large images are downscaled by half in the page, which hides more
    # compression than a thumbnail can afford.
    quality: int = 78
    note: str = ""


ASSETS = (
    Asset(
        "app-overview",
        "app-overview",
        note="the demo with the sample CT loaded, in the showcase frame",
    ),
    Asset(
        "registration-before",
        "registration",
        note="the loaded, unregistered pair, below the workflow section",
    ),
    Asset(
        "template-simple",
        "template-simple",
        quality=88,
        note="the dialog the simple template declares",
    ),
    Asset(
        "template-workflow",
        "template-workflow",
        crop=(0, 0, 640, 440),
        quality=88,
        note="the review step, cropped off the tall panel it sits in",
    ),
    Asset(
        "template-monai-result",
        "template-monai",
        crop=(2008, 948, 2660, 1600),
        quality=88,
        note="the 3D view with the model's label map, cropped above the watermark",
    ),
    Asset(
        "template-chat",
        "template-chat",
        crop=(0, 0, 720, 880),
        quality=88,
        note="the assistant panel after a short exchange, cropped off the tall panel",
    ),
)


def convert(asset: Asset, source_dir: Path, dest_dir: Path) -> bool:
    """Write one asset, returning whether its source was there to convert."""
    from PIL import Image

    source = source_dir / f"{asset.source}.png"
    if not source.is_file():
        print(f"  {asset.name}: no {source.name} in {source_dir}, skipped")
        return False

    with Image.open(source) as opened:
        captured = opened.size
        image = opened.convert("RGB")
    if asset.crop:
        image = image.crop(asset.crop)

    destination = dest_dir / f"{asset.name}.webp"
    image.save(destination, "WEBP", quality=asset.quality, method=6)
    size_kb = destination.stat().st_size / 1024
    print(
        f"  {asset.name}: {captured[0]}x{captured[1]} -> "
        f"{image.width}x{image.height} ({image.width // CROP_SCALE}px shown), "
        f"{size_kb:.0f}KB"
    )
    return True


def main(argv: Union[Sequence[str], None] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "source",
        type=Path,
        help="Directory of screenshots captured with --scale 2",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help="Directory for the generated WebP files",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        choices=[asset.name for asset in ASSETS],
        help="Convert just these assets (default: all)",
    )
    args = parser.parse_args(argv)

    selected = [asset for asset in ASSETS if not args.only or asset.name in args.only]
    args.dest.mkdir(parents=True, exist_ok=True)
    print(f"landing assets from {args.source}")
    written = sum(convert(asset, args.source, args.dest) for asset in selected)
    print(f"{written} of {len(selected)} written to {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
