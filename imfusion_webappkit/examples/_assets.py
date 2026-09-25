"""Shared assets used by the bundled demos."""

from pathlib import Path

_EXAMPLES_DIR = Path(__file__).parent

DEFAULT_LOGO = (
    Path(__file__).parent.parent
    / "static"
    / "assets"
    / "icons"
    / "ImFusionLogoWhite.svg"
)
SAMPLE_IMAGE = _EXAMPLES_DIR / "sample_image.nii.gz"
SAMPLE_IMAGE_THUMBNAIL = _EXAMPLES_DIR / "sample_image_thumbnail.png"

# Two T1w brain MRIs of the same subject in different sessions, for the
# registration demo's fixed and moving roles.
BRAIN_PAIR = _EXAMPLES_DIR / "brain_reg.imf"
BRAIN_PAIR_THUMBNAIL = _EXAMPLES_DIR / "brain_reg_thumbnail.png"
