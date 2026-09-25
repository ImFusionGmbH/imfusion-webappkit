"""
Example: WebApp Demo

This example demonstrates how to use the imfusion_webappkit package to create
a web-based viewer with custom server-side image processing actions.

This demo shows custom actions, synchronized data-model access, and both generic
and dedicated ImFusion algorithm controls.
"""

import time

import numpy as np
import imfusion
from imfusion_webappkit import (
    BrandingConfig,
    FloatParameter,
    ImFusionWebApp,
    InfoConfig,
    IntParameter,
    LayoutConfig,
    SampleDataset,
    SidebarConfig,
    SidePosition,
    ThemeConfig,
    ThemePreset,
    ViewLayout,
    ViewType,
    WebApplicationController,
)

from imfusion_webappkit.examples._assets import (
    DEFAULT_LOGO,
    SAMPLE_IMAGE,
    SAMPLE_IMAGE_THUMBNAIL,
)


def invert_intensity(imageset: imfusion.SharedImageSet) -> imfusion.SharedImageSet:
    """
    Invert image intensity.

    Args:
        imageset: Input image set

    Returns:
        Modified image set with inverted intensities
    """
    image = imageset[0]

    # Get numpy array (with copy to apply shift/scale)
    # arr = image.numpy()
    arr = np.array(image, copy=True)

    # Invert
    max_val = arr.max()
    min_val = arr.min()
    inverted = max_val + min_val - arr

    # Assign back to image
    image.assign_array(inverted)

    return imageset


def duplicate_data(
    imageset: imfusion.SharedImageSet, app: WebApplicationController
) -> imfusion.SharedImageSet:
    """
    Duplicate the selected image and add the copy to the data model.

    This demonstrates how to create new data on the server and register it
    with ``app.data_model.add()`` so it appears in the web UI.
    """
    copy = imageset.clone()
    source_name = app.data_model.get_name(imageset)
    app.data_model.add(copy, f"{source_name} (copy)")

    return imageset


def clear_data(app: WebApplicationController) -> None:
    """
    Clear all data from the data model.
    """
    app.data_model.clear()


def slow_processing(
    imageset: imfusion.SharedImageSet,
    *,
    steps: int,
    delay: float,
    app: WebApplicationController,
) -> imfusion.SharedImageSet:
    """
    Demo action that simulates slow processing with progress updates.

    This demonstrates the use of app.update_progress() to report
    computation progress to the web UI.

    Args:
        imageset: Input image set
        steps: Number of simulated processing stages
        delay: Delay per stage in seconds
        app: Session-scoped application controller

    Returns:
        The processed image set
    """
    for i in range(steps):
        # Simulate some processing work
        time.sleep(delay)

        # Report progress (0.0 to 1.0)
        progress = (i + 1) / steps
        app.update_progress(progress, f"Processing step {i + 1}/{steps}")

    # Return the image unchanged (this is just a demo)
    return imageset


def main(host: str = "127.0.0.1", port: int = 8001):
    """Run the server with example actions."""

    sample_datasets = (
        [
            SampleDataset(
                "Sample Image",
                SAMPLE_IMAGE,
                SAMPLE_IMAGE_THUMBNAIL if SAMPLE_IMAGE_THUMBNAIL.is_file() else None,
            )
        ]
        if SAMPLE_IMAGE.is_file()
        else []
    )

    # Create app instance
    webapp = ImFusionWebApp(
        title="My ImFusion WebApp",
        sidebar=SidebarConfig(
            show_datamodel=True, show_views=True, show_display_options=True
        ),
        show_load_button=True,
        show_export_button=True,  # Enable export button to download all data as IMF
        branding=BrandingConfig(
            logo=DEFAULT_LOGO,
            favicon=DEFAULT_LOGO,
            landing_page_title="Welcome to My ImFusion WebApp",
            landing_page_message="Choose an image or drag it here",
        ),
        info=InfoConfig(
            title="About this demo",
            content="""
This example demonstrates an **ImFusion WebAppKit** application with custom
image-processing actions, configurable controls, and data export.

- [ImFusion](https://www.imfusion.com/)
- Contact: research@example.com
""",
        ),
        theme=ThemeConfig(preset=ThemePreset.DARK),
        layout=LayoutConfig(
            sidebar_position=SidePosition.LEFT,
            sidebar_width=300,
            initial_view_layout=ViewLayout.AUTO,
            initial_visible_views=(ViewType.MPR, ViewType.THREE_D),
        ),
        sample_datasets=sample_datasets,
        algorithm_selector="sidebar",
    )

    # Existing callables can be registered directly.
    webapp.register("Invert Intensity", invert_intensity)
    webapp.register(
        "Slow Processing",
        slow_processing,
        parameters=[
            IntParameter("steps", default=10, minimum=1, maximum=20),
            FloatParameter(
                "delay",
                label="Delay per step",
                default=0.3,
                minimum=0.0,
                maximum=2.0,
                step=0.1,
                unit="s",
            ),
        ],
    )
    webapp.register("Duplicate Data", duplicate_data)
    webapp.register("Clear Data", clear_data)

    # Expose one native ImFusion algorithm as a dedicated web operation.
    webapp.register(
        "Morphological Operations",
        algorithm="Base.MorphologicalOperations",
        placement="header",
    )

    # Start the server
    webapp.run(host=host, port=port)


if __name__ == "__main__":
    main()
