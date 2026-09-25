"""Example: recording the bundled demos as backend-free static demos.

Two specifications, one per bundled demo, showing what an application has to
give up to be publishable without Python and how to describe the interactions
worth recording::

    imfusion-webappkit record imfusion_webappkit.examples.static_demos:actions \\
        -o dist/actions
    imfusion-webappkit record imfusion_webappkit.examples.static_demos:workflow \\
        -o dist/workflow

The attribute has to be named because this module defines two specs. Running the
module records both into ``dist/``::

    python imfusion_webappkit/examples/static_demos.py

Then serve the output; the SDK is loaded as a module, so opening the file
directly will not work::

    python -m http.server -d dist/actions

The processing functions come from ``webapp_demo`` and ``workflow_demo``
unchanged. What differs is the configuration around them, and every difference
is the same kind: a recording can only answer for what was recorded, so anything
that accepts arbitrary input has to go.

- Data is preloaded through ``initial_data`` instead of being offered as a
  sample dataset or a drop zone, because a dataset the visitor supplies is one
  no recorded result was computed from.
- Loading and exporting are turned off for the same reason. Export in particular
  needs Python for every format but IMF.
- Algorithm discovery is turned off, because the panel is populated by the
  server on demand and nothing populates it here.

See ``docs/guides/static-demos.md`` for the full picture.
"""

from imfusion_webappkit import (
    BrandingConfig,
    FloatParameter,
    ImFusionWebApp,
    InfoConfig,
    InputSelectionStep,
    InputSpec,
    IntParameter,
    LayoutConfig,
    MessageStep,
    ParameterStep,
    ProcessingStep,
    SidebarConfig,
    SidePosition,
    ThemeConfig,
    ThemePreset,
    ValidationStep,
    ViewLayout,
    ViewType,
)
from imfusion_webappkit.static_demo import (
    ActionScenario,
    DemoLimits,
    StaticDemoSpec,
    WorkflowScenario,
)

from imfusion_webappkit.examples._assets import DEFAULT_LOGO, SAMPLE_IMAGE
from imfusion_webappkit.examples.webapp_demo import (
    duplicate_data,
    invert_intensity,
    slow_processing,
)
from imfusion_webappkit.examples.workflow_demo import (
    SegmentationSummaryStep,
    apply_intensity_threshold,
)


def _sample():
    import imfusion

    return imfusion.io.load(str(SAMPLE_IMAGE))[0]


def _recordable(title: str, **overrides) -> ImFusionWebApp:
    """An application configured so that everything it offers can be recorded."""
    settings = dict(
        title=title,
        branding=BrandingConfig(logo=DEFAULT_LOGO, favicon=DEFAULT_LOGO),
        sidebar=SidebarConfig(
            show_datamodel=True, show_views=True, show_display_options=True
        ),
        show_load_button=False,
        show_export_button=False,
        theme=ThemeConfig(preset=ThemePreset.DARK),
        layout=LayoutConfig(
            sidebar_position=SidePosition.LEFT,
            sidebar_width=300,
            initial_view_layout=ViewLayout.AUTO,
            initial_visible_views=(ViewType.MPR, ViewType.THREE_D),
        ),
    )
    settings.update(overrides)
    return ImFusionWebApp(**settings)


# --------------------------------------------------------------------------
# The action demo
# --------------------------------------------------------------------------


def build_action_app() -> ImFusionWebApp:
    """The action demo, minus what a recording cannot answer for.

    The factory is called once per recorded transition, so it has to build the
    same application every time: same data, same actions, no state carried over
    from a previous call.
    """
    webapp = _recordable(
        "Image Tools",
        info=InfoConfig(
            title="About this demo",
            content=(
                "The ImFusion WebAppKit client with a recording where the Python "
                "process would be. Viewing, layout and display work because they "
                "always ran in your browser.\n"
            ),
        ),
    )
    webapp.register("Invert Intensity", invert_intensity)
    webapp.register("Duplicate Data", duplicate_data)
    webapp.register(
        "Slow Processing",
        slow_processing,
        parameters=[
            IntParameter("steps", default=10, minimum=1, maximum=20),
            FloatParameter(
                "delay", label="Delay per step", default=0.3, minimum=0.0, maximum=2.0
            ),
        ],
    )
    webapp.register(
        "Threshold",
        apply_intensity_threshold,
        parameters=[
            FloatParameter(
                "threshold", default=100.0, minimum=-1000.0, maximum=4096.0, step=1.0
            )
        ],
    )
    webapp.initial_data.add(_sample(), "Sample Image")
    return webapp


actions = StaticDemoSpec(
    app=build_action_app,
    actions={
        # Thresholding is a comparison per voxel, which the WebAssembly SDK in
        # the browser does as well as numpy does. A handler runs it there, so the
        # slider stays continuous instead of snapping to recorded values. The
        # handler has to agree with the Python function it stands in for;
        # `handlers.ts` is where that is checked.
        "Threshold": ActionScenario(handler="threshold"),
        # Recording this one is worth it for the progress reporting alone, which
        # replays exactly as the server sent it. One combination is enough: a
        # visitor watching a progress bar is not comparing step counts.
        "Slow Processing": ActionScenario(parameters={"steps": [4], "delay": [0.2]}),
    },
    # "Clear Data" is left out on purpose. It empties the data model, and a
    # recorded demo cannot load anything to recover, so every state after it
    # would be a dead end.
    include_actions=[
        "Invert Intensity",
        "Duplicate Data",
        "Slow Processing",
        "Threshold",
    ],
    # Each recorded result is a whole dataset, so depth is what decides the size
    # of the download. Three interactions deep is already 20 states here.
    limits=DemoLimits(max_nodes=24, max_depth=3),
)


# --------------------------------------------------------------------------
# The guided workflow demo
# --------------------------------------------------------------------------


def build_workflow_app() -> ImFusionWebApp:
    """The segmentation workflow, minus the two steps that cannot be recorded.

    `BrushStep` is gone because freehand strokes are unbounded input, and
    recording refuses it outright rather than publishing a brush that does
    nothing. `ExportStep` is gone because producing a file needs Python. The
    steps that depended on the brush now depend on the processing step.
    """
    webapp = _recordable(
        "Intensity Threshold Segmentation",
        layout=LayoutConfig(
            workflow_panel_position=SidePosition.LEFT,
            workflow_panel_width=320,
            sidebar_position=SidePosition.RIGHT,
            sidebar_width=300,
            initial_visible_views=(ViewType.MPR, ViewType.THREE_D),
        ),
        sidebar=SidebarConfig(
            show_datamodel=True,
            show_views=True,
            show_display_options=True,
            collapsed=True,
        ),
    )
    webapp.set_workflow(
        [
            MessageStep(
                "Welcome",
                "Segment the image, review the result, and see what it measured.",
                step_id="welcome",
            ),
            InputSelectionStep(
                "Select Image",
                inputs=[InputSpec("image", "Image")],
                # No drop zone and no sample cards: the only image here is the
                # one the recording was made from.
                allow_upload=False,
                message="Assign the preloaded image to the input role.",
                step_id="input",
            ),
            ParameterStep(
                "Configure Segmentation",
                parameters=[
                    FloatParameter(
                        "threshold",
                        label="Intensity Threshold",
                        default=100.0,
                        minimum=-1000.0,
                        maximum=4096.0,
                        step=1.0,
                    )
                ],
                step_id="configure",
            ),
            ProcessingStep(
                "Segment Image",
                callback=apply_intensity_threshold,
                inputs_from="input",
                parameters_from="configure",
                step_id="process",
            ),
            SegmentationSummaryStep(label_map_from="process", step_id="summary"),
            ValidationStep(
                "Review Result",
                "Is the segmentation acceptable?",
                step_id="review",
                depends_on=["process"],
            ),
        ]
    )
    webapp.initial_data.add(_sample(), "Sample Image")
    return webapp


workflow = StaticDemoSpec(
    app=build_workflow_app,
    # Applies to any step declaring a parameter of this name, so the threshold
    # step is recorded at both settings and the panel snaps to them.
    parameters={"threshold": [100.0, 300.0]},
    workflow=WorkflowScenario(
        # Going back is a real transition rather than a return: it resets the
        # step being left and invalidates whatever depended on it, so the state
        # it lands in is not the state it came from. That makes it expensive in a
        # branching workflow — with **Back** and three thresholds this one runs
        # past fifty states — and it is the first thing to drop when a recording
        # grows past its limits.
        include_back=False,
    ),
    notice=(
        "This page is a recording of a guided workflow, so only the path that "
        "was captured while building it can be replayed. Run the real thing "
        "with `pip install imfusion-webappkit` and "
        "`imfusion-webappkit demo --workflow`."
    ),
    limits=DemoLimits(max_nodes=48, max_depth=10),
)


def main(output: str = "dist") -> None:
    """Record both demos, the way the `record` command does it internally.

    The command in the module docstring is the shorter way to get one of these.
    Calling :func:`build` is what to reach for when a release script has to
    produce several demos, or wants the size report as data.
    """
    from pathlib import Path

    from imfusion_webappkit.static_demo.build import build

    for name, spec in (("actions", actions), ("workflow", workflow)):
        destination = Path(output) / name
        print(f"\nRecording {name} into {destination}")
        report = build(
            spec, destination, progress=lambda message: print(f"  {message}")
        )
        print("\n".join(report))
        print(f"Serve it with: python -m http.server -d {destination}")


if __name__ == "__main__":
    import sys

    main(*sys.argv[1:2])
