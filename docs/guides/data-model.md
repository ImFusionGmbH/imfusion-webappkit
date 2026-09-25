# Data model synchronization

Add, rename, or clear data through `app.data_model`, and the browser follows,
because every connection owns a `WebApplicationController` whose `data_model`
stays synchronized with that browser alone. Data, progress, selection, workflow,
and jobs never route through a global "current session".

## Initial and session data

Seed data belongs to the server host:

```python
import imfusion
from imfusion_webappkit import ImFusionWebApp


webapp = ImFusionWebApp()
planning_ct = imfusion.load("scan.nii.gz")[0]
webapp.initial_data.add(planning_ct, "Planning CT")
webapp.run()
```

Each new connection receives serialized copies in an isolated session model,
so an in-place change in one browser cannot mutate another session's seed data.
Inside actions and workflows, the injected `app` is the session controller:

```python
def clear_session(app):
    app.data_model.clear()


def process(image, app):
    modify(image)
    app.data_model.update(app.data_model.index(image))
    return image
```

There is deliberately no runtime `ImFusionWebApp.data_model` proxy because a
server may have several active browser sessions.

## Collection operations

The synchronized model supports:

- indexing by integer, list, or slice;
- iteration, `len(model)`, and `size`;
- `add(data, name=\"\")` and `add(list_of_data)`;
- `remove(data_or_index)` and `clear()`;
- `get(name)`, `contains(data)`, and `index(data)`;
- `get_name`, `set_name`, `update(index)`, `update_metadata(index)`, and
  `replace(index, data, name=None)`.

`update(index)` pushes an in-place modification to the browser. The ordered
browser model is rebuilt from the session model so subsequent input references
remain aligned with server indices.

`update_metadata(index)` is the cheap variant for changes that leave the pixels
alone. The caller asserts that; the pixels are never compared, because
comparing them would cost as much as sending them.

```python
def relabel(image, app):
    image.modality = imfusion.Data.Modality.LABEL
    app.data_model.update_metadata(app.data_model.index(image))
```

Only the name and the modality currently avoid the full transfer, because they
are the only fields the web SDK can write onto a dataset the browser already
holds. A change to the spacing or the matrix falls back to the same full
transfer as `update(index)`, which `update_metadata` reports by returning
`False` and logging why. Callers do not need to change when the SDK gains the
missing setters; the same call simply gets cheaper.

`replace(index, data, name=None)` swaps an object while preserving its model
position and browser views. Processing steps use it internally when replacing
the output of a previous run. When passing a list to `add`, omit `name`; one
name cannot be applied to a list and raises `ValueError`.

## Relationship to `imfusion.DataModel`

The common flat collection API intentionally resembles
`imfusion.app.data_model`, but WebAppKit has documented differences:

- `add` retains the Python object instead of copying it;
- `get` returns `None` when a name is absent;
- `remove` additionally accepts an integer index;
- grouping, `root_node`, and parent traversal are not implemented;
- `update`, `update_metadata`, `get_name`, and `set_name` are web
  synchronization extensions.

## Selection

`app.selected_data` returns the current browser-visible selection.
`app.select_data(data_or_list)` updates it from Python. Named action and
workflow inputs remain explicit through `InputSpec` and are not inferred from
arbitrary multi-selection.

Data references are released on the ImFusion SDK owner thread when the browser
disconnects.
