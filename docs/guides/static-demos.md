# Recorded static demos

A WebAppKit application is a browser client talking to a Python process. Some
places cannot host that process: a documentation site, a GitHub Pages branch, a
product page, a link in an email. A recorded demo is the same client answered
from a recording instead, so it can be published as plain files.

Recording drives the real application while building. Every interaction worth
showing is performed, and the messages the server sent back are written to disk
together with the datasets they carried. The published page then replays them.
Nothing is reimplemented, and no fixture is written by hand, so a demo cannot
show behaviour the application does not have.

What still works without Python is everything the browser was already doing:
loading, rendering, slicing, windowing, layout, and the display controls. What
needs recording is anything that reaches the server — actions and workflow
steps.

## Two worked examples

`imfusion_webappkit/examples/static_demos.py` records the two bundled demos, one
built from actions and one from a guided workflow, and can be run without
writing anything first:

```bash
imfusion-webappkit record imfusion_webappkit.examples.static_demos:actions -o dist/actions
python -m http.server -d dist/actions
```

Both reuse the processing functions from `webapp_demo` and `workflow_demo`
unchanged; what the examples show is the configuration around them and the
reasoning behind each difference. The landing page's demo is a third, in
`tools/build_static_demo.py`.

## Describe the demo

A demo is a `StaticDemoSpec` naming a factory for the application and the
interactions to record.

```python
# demos/threshold.py
from imfusion_webappkit import FloatParameter, ImFusionWebApp
from imfusion_webappkit.static_demo import ActionScenario, StaticDemoSpec

from algorithm import apply_threshold


def build_app() -> ImFusionWebApp:
    webapp = ImFusionWebApp(
        title="Image Tools",
        # Both need a Python process, and neither can be recorded.
        show_load_button=False,
        show_export_button=False,
    )
    webapp.register(
        "Threshold",
        apply_threshold,
        parameters=[FloatParameter("threshold", default=100.0, minimum=0.0, maximum=1000.0)],
    )
    webapp.initial_data.add(load_sample(), "Sample Image")
    return webapp


spec = StaticDemoSpec(
    app=build_app,
    actions={"Threshold": ActionScenario(parameters={"threshold": [50, 100, 200, 400]})},
)
```

The factory is called once per recorded transition, so it has to build the same
application every time. Load the same data, register the same actions, and do
not depend on state left behind by an earlier call.

## Record it

```bash
imfusion-webappkit record demos/threshold.py -o dist/threshold
```

The reference is `module:attribute`, or a file path with the same suffix. The
attribute may be left out when the module defines exactly one spec. The command
builds the client, records, and writes a directory that can be served as-is:

```text
dist/threshold/
  index.html
  assets/            the client bundle and the WebAssembly SDK
  branding/          the logo and favicon, copied out of the application
  sample-datasets/   the sample datasets, copied out of the application
  fixtures/
    manifest.json    the recording
    payloads/        one file per recorded dataset
```

Open it through a web server rather than from the filesystem; the SDK is loaded
as a module and needs HTTP. The output has relative URLs throughout, so it works
in a subdirectory and inside an iframe.

## What gets recorded

The recorder treats the application as a state machine. A state is everything
the browser can observe — the datasets it holds, which of them are shown, and
the workflow's position — and every change to one is caused by a single client
message. Recording explores that machine breadth-first: from each state it tries
every interaction the demo declares, and follows the ones that lead somewhere
new.

The result is a graph rather than a transcript, which is what lets a visitor
click in their own order, apply an action twice, or step back through a
workflow, instead of retracing the path whoever built the demo happened to take.
States that turn out to be equivalent collapse onto one another, so going back
and forward again returns to where it was.

Because each recorded result is a complete dataset, the number of interactions
and the size of the download are the same quantity. `DemoLimits` stops a
recording before it becomes unpublishable:

```python
from imfusion_webappkit.static_demo import DemoLimits, StaticDemoSpec

spec = StaticDemoSpec(
    app=build_app,
    limits=DemoLimits(max_nodes=32, max_depth=6, max_bytes=100 * 1024 * 1024),
)
```

Recording prints a size report at the end, and warns about anything that will
disappoint a visitor: an interaction that failed while recording, a state with
no data left, or a button in the interface that a recording cannot answer.

## Actions

Every registered action is recorded at its default parameters unless the spec
says otherwise. `ActionScenario` narrows or widens that:

```python
ActionScenario(
    parameters={"threshold": [50, 100, 200], "smooth": [True, False]},
    inputs=[{"image": 0}],
    repeat=2,
)
```

Every combination of the listed values is recorded, so the count multiplies.
`inputs` pins the role-to-dataset assignments; by default a single-input action
is recorded against each dataset in turn. `repeat` allows the action to be
applied to its own output, which multiplies build time and size again.

Use `include_actions` to record only some of them:

```python
StaticDemoSpec(app=build_app, include_actions=["Threshold", "Smooth"])
```

### Continuous parameters

A recorded action can only answer for the values it was recorded at. Its
controls stay the ones the application declared, but a typed value snaps to the
nearest recorded one when the field is left, and the field says which values
those are — `Recorded: 50, 100, 200` under a threshold field, or `12 recorded
values` when there are too many to list. Choices are narrowed to the recorded
options, and a parameter recorded at a single value is shown but cannot be
changed. Nothing in the interface offers a value that leads nowhere.

### Running an action in the browser instead

Snapping is a compromise, and some actions do not need it. What a static host
lacks is Python, not the imaging library: the WebAssembly SDK the viewer already
uses can do a per-voxel comparison as well as `numpy` can. An action can opt
into a client-side handler, which computes in the browser and answers with the
same messages the server would have:

```python
ActionScenario(handler="threshold")
```

A handler-backed action is not recorded at all, and keeps its slider continuous.
The available handlers are listed in
`imfusion_webappkit.static_demo.AVAILABLE_HANDLERS`, and their implementations
live in `static/src/static-demo/handlers.ts`. A name that is not among them
fails while building rather than in a visitor's browser.

## Workflows

A workflow is recorded by walking it. **Next**, **Back**, and a processing
step's **Run** are followed wherever the workflow allows them, and each step
contributes the interactions its type implies: parameter values for a
`ParameterStep`, both answers for a `ValidationStep`, the role assignment for an
`InputSelectionStep`, each button for a `CustomStep`.

Parameter values come from the spec, either per name for the whole demo or
scripted per step:

```python
from imfusion_webappkit.static_demo import StaticDemoSpec, WorkflowScenario

spec = StaticDemoSpec(
    app=build_app,
    parameters={"threshold": [100, 300]},
    workflow=WorkflowScenario(
        step_data={"configure": [{"parameters": {"threshold": 300, "smooth": True}}]},
        include_back=True,
    ),
)
```

**Back** is a transition rather than a return: it resets the step being left and
invalidates whatever depended on it, so the state it lands in is not the state it
came from. That makes it the most expensive thing a workflow scenario can ask
for, and the first to drop when a recording outgrows its limits — the workflow
example needs only three thresholds and a **Back** to run past fifty states. With
`include_back=False` the panel greys the button out instead of offering an
interaction the recording cannot answer. The exception is a rejected
`ValidationStep`: the live app disables **Finish** and tells the visitor to go
back, so that **Back** is recorded anyway.

Two kinds of step cannot appear in a recorded demo:

- A `BrushStep` takes freehand strokes, which are unbounded input, so no
  recording can hold their result. Recording refuses outright.
- An `ExportStep` can only hand back a dataset in a format the browser can write
  itself. Build the demo application with `show_export_button=False` and leave
  export out of the workflow.

Finishing a workflow usually clears the session, and a recorded demo has no way
to load data again. The recording therefore treats **Finish** as a restart: it
replays the initial datasets and returns to the first step, instead of leaving
the visitor on an empty Welcome screen with both buttons disabled.

## What a visitor sees

A recorded page carries a badge saying there is no Python behind it. Reaching an
interaction that was not recorded is explained rather than left to time out:

```python
StaticDemoSpec(
    app=build_app,
    notice=(
        "This page is a recording, so only what was captured while building it "
        "can be replayed. Install the real thing with "
        "`pip install imfusion-webappkit`."
    ),
)
```

Recording narrows the interface so this is rare, but a visitor who changes the
visible datasets by hand and then presses a button can still get there.

## Reproducibility

A recorded state is identified by what it contains, not by the bytes it
serialized to: the voxel values, the geometry, the names, and the workflow's
position. The IMF container is not byte-for-byte reproducible across a
save-and-load round trip, so comparing bytes would make equivalent states look
different and store the same dataset many times over. Content addressing is also
what deduplicates the payloads, so a dataset that appears in twenty recorded
states is downloaded once.

The key each interaction is stored under is computed twice, once by
`imfusion_webappkit/static_demo/canonical.py` while recording and once by
`static/src/static-demo/canonical.ts` while replaying. Both are checked against
a shared table of awkward values, so the two cannot drift apart unnoticed.
