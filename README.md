# ImFusion WebAppKit

[![CI](https://github.com/ImFusionGmbH/imfusion-webappkit/actions/workflows/ci.yml/badge.svg)](https://github.com/ImFusionGmbH/imfusion-webappkit/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/imfusion-webappkit)](https://pypi.org/project/imfusion-webappkit/)
[![Documentation](https://img.shields.io/badge/docs-imfusiongmbh.github.io-blue)](https://imfusiongmbh.github.io/imfusion-webappkit/docs/)

The ImFusion WebAppKit serves Python imaging algorithms in a medical web viewer
over HTTP, so you can demo them to colleagues and clinicians without writing any
web code. You register a function, the kit builds the matching button and
controls, and whatever you return shows up in the viewer.

The kit already includes the viewer, the HTTP server, and a session model that
isolates each browser connection. What you write is the imaging logic, which
runs on the ImFusion Python SDK thread rather than in the browser.

This is an early prototype, so interfaces may
still change between versions. The kit itself is MIT-licensed, but it runs on
the ImFusion SDK, which is free for non-commercial use and needs a commercial
licence otherwise.

![The WebAppKit demo in a browser: a CT volume in three orthogonal views and a 3D rendering, with a sidebar of datasets, layout and display controls and a row of algorithm buttons in the header.](https://raw.githubusercontent.com/ImFusionGmbH/imfusion-webappkit/HEAD/docs/assets/screenshots/app-overview.png)

## Creating an app

Annotate a function and give it the name you want on the button, and WebAppKit
builds the matching controls and runs the call on the ImFusion SDK thread.
Argument types pick the controls, so a float with bounds arrives as a slider
and an image argument as a dataset selector. You can also expose an existing
ImFusion algorithm by name.

```python
import numpy as np
import imfusion

from imfusion_webappkit import FloatParameter, ImFusionWebApp

app = ImFusionWebApp(title="Image Tools")


@app.register(
    "Threshold",
    parameters=[
        FloatParameter(
            "threshold", default=100.0, minimum=0.0, maximum=1000.0,
        ),
    ],
)
def apply_threshold(
    imageset: imfusion.SharedImageSet,
    *,
    threshold: float,
) -> imfusion.SharedImageSet:
    image = imageset[0]
    label = imfusion.SharedImage((image.numpy() >= threshold).astype(np.uint8))
    label.image_to_world_matrix = image.image_to_world_matrix
    label.spacing = image.spacing

    mask = imfusion.SharedImageSet()
    mask.add(label)
    mask.modality = imfusion.Data.Modality.LABEL
    return mask


app.run()
```

Open <http://127.0.0.1:8000>, load an image, select it, and run the action.

## What's included

The imaging work stays in Python, while the kit owns the parts that usually
force you into a frontend project.

**The viewer.** MPR, 3D, and 2D views with the display options and interactions
people already know from ImFusion Suite. Layout and which views are visible are
set from Python (`ViewLayout`, `LayoutConfig`).

**The data model.** Add, rename, or clear data through `app.data_model`, and the
browser follows without any message passing of your own.

**A session per visitor.** Every browser connection gets its own data and
workflow state, so several people can open the app at once.

**Your branding.** Logo, colors, panel widths, an About dialog, and bundled
sample datasets can be configured (`BrandingConfig`, `ThemeConfig`).

**A command line.** `doctor` checks the environment, `demo` runs a sample app,
`init` scaffolds a project, and `record` writes a snapshot you can host with no
backend.

## Guided workflows

If a study has to run in a fixed order, define a workflow as a list of steps.
The kit handles the UI and keeps state per session, including progress and
cancellation. A reviewer can reject a result and step back without restarting.

The built-in steps cover loading and input roles, parameters, processing, brush
correction, annotations, validation, and export, and a `CustomStep` composes a
panel of your own when none of them fits.

```python
app.set_workflow([
    MessageStep("Welcome", "Load, segment, correct, export."),
    InputSelectionStep("Select Image", inputs=[image]),
    ParameterStep("Configure", parameters=[threshold]),
    ProcessingStep("Segment", callback=threshold_segment),
    BrushStep("Correct Segmentation", radius_mm=5.0),
    SegmentationSummaryStep(label_map_from="process"),
    ValidationStep("Review", "Is this acceptable?"),
    ExportStep("Export Segmentation"),
])
```

The snippet is the segmentation example, with eight steps in the order they run
and a validation step that can send the operator back to the brush.
`SegmentationSummaryStep` is not one of the built-ins: the example defines it as
a `CustomStep`, which is how a workflow gets a panel the kit does not ship.

![The registration example at its input step: three orthogonal views and a 3D rendering of two brain MRI sessions loaded but not yet aligned, a data model listing both sessions, and a workflow panel for assigning the fixed and moving roles.](https://raw.githubusercontent.com/ImFusionGmbH/imfusion-webappkit/HEAD/docs/assets/screenshots/registration.png)

The screenshot is a different workflow from the snippet above, where two steps
assign fixed and moving images by role and the registered result then lands in
the data model.

## Start from a template

`imfusion-webappkit init` creates a runnable project. The default is a single
action; the other flags pick a different shape.

**`--template simple`.** A button, the parameters you declared, and your
function behind them.

**`--template workflow`.** Load, process, brush-correct, and a review the
operator has to accept before export.

**`--template monai`.** The spleen bundle from the MONAI Model Zoo, run on the
sample CT. The download, tensor layout, and coordinate conversions are already
in the template.

**`--template chat`.** A dataset-aware chat panel with a placeholder reply
function, ready to connect to your own model provider.

## Get started

The kit needs Python 3.10 or newer, [uv](https://docs.astral.sh/uv/), and valid
ImFusion Suite and Web SDK licenses. Releases are published to PyPI, but the
ImFusion SDK underneath them comes from the ImFusion index instead, so an
install has to name both:

```bash
uv pip install imfusion-webappkit --extra-index-url https://pypi.imfusion.com/simple
imfusion-webappkit demo
```

From a checkout of this repository the index is already configured in
`pyproject.toml`, so `uv sync` resolves everything on its own:

```bash
uv sync
uv run imfusion-webappkit demo
```

That starts the packaged demo with a small bundled NIfTI image at
<http://127.0.0.1:8000>. Add `--workflow` to launch the guided, multi-step demo
instead.

The checkout includes the compiled browser client, so Node.js and npm are not
needed to run it. They are only required to modify the frontend; see the
[development guide](https://github.com/ImFusionGmbH/imfusion-webappkit/blob/HEAD/docs/development.md).

To scaffold your own project:

```bash
uv run imfusion-webappkit init my-demo
cd my-demo
uv sync
uv run python app.py
```

The generated project runs as soon as it is created, with `app.py` holding the
application, `algorithm.py` the processing function you replace, and `AGENTS.md`
the session, threading, and geometry conventions that coding agents need. Pass
`--theme gray` for the gray theme instead of the default dark one, and see the
[command-line documentation](https://github.com/ImFusionGmbH/imfusion-webappkit/blob/HEAD/docs/cli.md) for the other templates and flags.

## Documentation

- [User guide](https://github.com/ImFusionGmbH/imfusion-webappkit/blob/HEAD/docs/index.md)
- [Getting started](https://github.com/ImFusionGmbH/imfusion-webappkit/blob/HEAD/docs/getting-started.md)
- [Command-line tools](https://github.com/ImFusionGmbH/imfusion-webappkit/blob/HEAD/docs/cli.md)
- [API reference](https://github.com/ImFusionGmbH/imfusion-webappkit/blob/HEAD/docs/api/application.md)
- [Runnable examples](https://github.com/ImFusionGmbH/imfusion-webappkit/blob/HEAD/imfusion_webappkit/examples)
- [Development guide](https://github.com/ImFusionGmbH/imfusion-webappkit/blob/HEAD/docs/development.md)

If the kit does not fit how you work, or you need a commercial ImFusion SDK
licence, email
[info@imfusion.com](mailto:info@imfusion.com?subject=ImFusion%20WebAppKit).
