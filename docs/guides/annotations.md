# Annotations

Annotations are the geometry the user draws in the viewer: a point on a
landmark, a line for a distance, a box around a region. WebAppKit collects them
in the browser and hands Python the coordinates.

`app.annotation_model` mirrors
[`imfusion.app.annotation_model`](https://docs.imfusion.com/python/application.html#annotationmodel),
so the calls that create, list, and remove annotations read the same as they do
in a desktop plugin. One model belongs to each browser session, alongside that
session's data model.

## Where geometry lives

The browser owns the annotation. Only it has the OpenGL object and the event
handler that turns clicks into points, so Python holds a shadow copy and an
incoming event always wins over a value set from Python.

That is why an annotation always belongs to a dataset, which the Web SDK
requires even though the Python SDK does not: the geometry is drawn in that
dataset's views and disappears with it.

```python
from imfusion_webappkit import AnnotationType


def mark_region(image, app):
    annotation = app.annotation_model.create_annotation(AnnotationType.RECTANGLE, image)
    annotation.label = "Region of interest"
    annotation.on_editing_finished(lambda: print(annotation.points))
    annotation.start_editing()
```

Nothing reaches the browser until `start_editing()`, because the Web SDK's
`add()` immediately arms interactive placement. Assigning `points` publishes it
too, which is how an annotation gets displayed without the user placing it.

Callbacks run on the ImFusion SDK owner thread, like action and algorithm
callbacks, so they may call into the SDK directly. They take no arguments to
match the Python SDK; declare an `annotation` parameter to receive the
annotation that fired.

### World and image coordinates

`points` is in world coordinates, matching the Web SDK. `points_in(data)`
converts to a dataset's own frame, and is what you want for anything that has
to outlive a change to that dataset's transform — a registration, a reslice, or
a JSON file read back tomorrow.

```python
box = annotation.points_in(image)
lower = [min(axis) for axis in zip(*box)]
upper = [max(axis) for axis in zip(*box)]
```

`length` and `angle` are filled in for `LINE` and `ANGLE` annotations, and are
`None` for every other type.

`label` is drawn next to the annotation in the views, but the viewer writes its
own measurement there for the shapes that have one, so a label set on a `LINE`
or an `ANGLE` does not appear. Use it for the shapes the viewer leaves
unlabelled.

## Annotation types

`AnnotationType` carries the Web SDK's own literals, so an annotation type is
available exactly when the browser's SDK build binds it.

| Type | Points | Available |
| --- | --- | --- |
| `AnnotationType.LINE` | 2 | yes |
| `AnnotationType.RECTANGLE` | 2 corners | yes |
| `AnnotationType.ANGLE` | 3, vertex in the middle | yes |
| `AnnotationType.POINT` | 1 | pending a Web SDK release |
| `AnnotationType.BOX` | 3D extent | pending a Web SDK release |

The client checks the type against its own bindings before creating anything,
so an unsupported type is reported rather than throwing. `annotation.error`
carries the reason, and `AnnotationStep` blocks with that message instead of
asking for a placement the browser cannot make.

The Python SDK additionally defines `CIRCLE` and `POLY_LINE`. Those have no Web
SDK equivalent at all; supporting them is one entry in `AnnotationType` once
they appear.

## Collecting annotations in a workflow

`AnnotationStep` is the whole step when placement is all it does. It creates one
annotation per label, arms them one at a time, and blocks navigation until they
are placed.

```python
from imfusion_webappkit import AnnotationStep, AnnotationType, InputSelectionStep, InputSpec

webapp.set_workflow(
    [
        InputSelectionStep(
            "Select image",
            inputs=[InputSpec("image", "Image")],
            step_id="input",
        ),
        AnnotationStep(
            title="Mark the region",
            message="Press Place, then drag a box around the branching region.",
            annotation_type=AnnotationType.RECTANGLE,
            image_from="input",
            show_measurements=True,
            step_id="region",
        ),
    ]
)
```

Placement is armed explicitly, by the panel's Place button, so the first click
on the canvas cannot become an annotation while the user is still navigating to
the anatomy. Collecting several is one press and one click each: finishing one
arms the next.

The collected geometry is on the step, keyed by role:

```python
region = app.workflow.get_step("region")
corners = region.annotations["default"][0].points
```

Use `labels` to collect a sequence with its own prompts, and `image_roles` to
collect a set per dataset. Each role names an input role in `image_from` and
gets a colour of its own, which is what makes landmarks on a fixed and a moving
image distinguishable:

```python
AnnotationStep(
    title="Pick corresponding landmarks",
    annotation_type=AnnotationType.POINT,
    image_from="registration_inputs",
    image_roles=["fixed", "moving"],
    labels=["Anterior", "Superior", "Lateral"],
    keep_annotations=False,
    on_finished=initialize_registration,
    step_id="landmarks",
)
```

`on_finished` fires once every annotation is placed:

```python
import numpy as np


def initialize_registration(step):
    fixed_points = np.array([a.points[0] for a in step.annotations["fixed"]])
    moving_points = np.array([a.points[0] for a in step.annotations["moving"]])
    step.app.workflow.get_step("register").initial_matrix = kabsch(
        moving_points, fixed_points
    )
```

`keep_annotations=False` matters here. An annotation does not follow its
dataset's transform, so once the registration moves the moving image its
landmarks sit visibly detached from the anatomy they marked. Clear them as soon
as the geometry has been consumed.

By default annotations stay in the viewer after the step and are reused if the
user comes back, so navigating away and returning does not discard work.

`views` restricts where placement is allowed. Slice views are the default for
the 2D shapes, because dragging a rectangle in a 3D rendering places its corners
on whatever the ray happens to hit.

### Mixing placement with other input

`AnnotationField` is the same panel readout as an element, for a `CustomStep`
that collects something else alongside the geometry — a distance the operator
reads off a chart, say, which cannot come from the image. The step drives
`app.annotation_model` from `on_action` and the element shows the result.

```python
from imfusion_webappkit import AnnotationField, CustomStep, Fields, FloatParameter


class ClinicalBoxStep(CustomStep):
    def on_enter(self):
        model = self.app.annotation_model
        image = self.app.workflow.get_step("input").inputs["image"]
        if self.line is None:
            self.line = model.create_annotation(AnnotationType.LINE, image)

    def body(self):
        return [
            Fields([FloatParameter("distance", unit="mm")], submit_action="set"),
            AnnotationField(
                [self.line],
                place_action="place",
                show_measurements=True,
            ),
        ]

    def on_action(self, action):
        if action == "place":
            self.line.start_editing()
```

See `imfusion_webappkit/examples/annotation_workflow_demo.py` for the whole step.

## Annotations outside a workflow

### As an action parameter

`AnnotationParameter` turns a placement into one field of an action's parameter
dialog. The user presses Place, and the dialog steps out of the way so the
viewer is reachable, then comes back with the annotation in place and the Run
button unlocked. The callback receives the `Annotation`, not its id.

The annotation attaches to the dataset chosen for the action's first input, so
`points_in` converts into the frame of an image the action actually holds.

```python
from imfusion_webappkit import AnnotationParameter, AnnotationType


def crop(image, roi, app):
    """`roi` is an Annotation the user drew before pressing Run."""
    corners = roi.points_in(image)
    ...


webapp.register(
    "Crop to region",
    crop,
    inputs=[InputSpec("image", "Image")],
    parameters=[
        AnnotationParameter("roi", annotation_type=AnnotationType.RECTANGLE),
    ],
)
```

### From the sidebar

`SidebarConfig(show_annotations=True)` adds a panel where the user starts an
annotation without an action asking for one, and lists what they have drawn per
dataset. Only the shapes the browser's SDK build supports are offered.

Python hears about each one through `on_annotation_added`. Register it from
`on_session_created`, which is the per-connection hook for listeners that no
action or workflow step owns:

```python
webapp = ImFusionWebApp(sidebar=SidebarConfig(show_annotations=True))


def watch_annotations(app):
    app.annotation_model.on_annotation_added(
        lambda annotation: print(annotation.type, annotation.points)
    )


webapp.on_session_created(watch_annotations)
```

The callback fires when the user picks a tool, before any points exist, so read
the geometry from `on_editing_finished` rather than from the callback argument:

```python
def watch_annotations(app):
    def placed(annotation):
        annotation.on_editing_finished(lambda: print(annotation.points))

    app.annotation_model.on_annotation_added(placed)
```

`imfusion_webappkit/examples/annotation_demo.py` puts the three pieces
together: the sidebar panel, a session callback that labels each finished box
with its extent, and two actions that export what has been collected.

## Exporting geometry

`ExportStep` writes datasets through ImFusion's writers, which is the wrong
shape for a JSON file of coordinates. `app.download` sends any bytes the server
produced straight to the browser's downloads:

```python
import json

payload = {
    "image": app.data_model.get_source_path(image),
    "box": [list(point) for point in annotation.points_in(image)],
}
app.download("annotations.json", json.dumps(payload, indent=2).encode(), "application/json")
```

`data_model.get_source_path(data)` returns the file a dataset was loaded from,
or `None` for data the browser uploaded, which the browser never sends a path
for.

## Lifetime

Annotations are removed before their dataset whenever it is removed, replaced,
or reset, because the Web SDK keys them by dataset and would otherwise be left
holding a dangling pointer. A step's records are pruned to match, so
`step.annotations` never hands back an annotation the browser has already
forgotten.

A finished or aborted annotation cannot be re-armed: the Web SDK binds no way
back from display into creation mode. Anything that means "try again" removes it
and creates another, which is what the panel's Redo button does and what
`start_editing()` refuses to do.

## Static demos

A [recorded static demo](static-demos.md) cannot replay annotations. The
geometry comes from where the user clicked, so it is not reproducible, and the
recorder raises `UnsupportedDemoInteraction` for an `AnnotationStep` rather than
recording a walkthrough that stalls. Drawing in a demo with the sidebar panel
turned on still works in the viewer, but nothing on the Python side hears about
it.
