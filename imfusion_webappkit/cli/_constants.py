"""Shared constants for the WebAppKit command-line tools."""

PACKAGE_NAME = "imfusion-webappkit"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
TEMPLATE_DESCRIPTIONS = {
    "simple": "Threshold-segmentation action with a browser-editable parameter.",
    "workflow": "Guided load, configure, process, review, and export flow.",
    "monai": "MONAI model workflow with direct PyTorch inference.",
    "chat": "Assistant panel grounded in the selected datasets.",
}
AVAILABLE_TEMPLATES = tuple(TEMPLATE_DESCRIPTIONS)
