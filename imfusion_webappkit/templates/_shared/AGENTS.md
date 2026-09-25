# ImFusion WebAppKit guidance

- Use `uv` for dependencies and run Python with `uv run`.
- The `app` injected into callbacks is the current browser session's
  `WebApplicationController`, not the global `ImFusionWebApp`. Each browser tab
  has isolated data and workflow state; `webapp.initial_data` only seeds copies.
- ImFusion SDK work is serialized on its owner thread. Do not call `imfusion`
  APIs from background or async threads; use registered actions and workflow
  processing callbacks.
- A session has one active job. Long callbacks should report progress and check
  `app.cancellation_requested` before in-place changes or other side effects.
- Keep callback `app` keyword-only when parameters are present, and make
  parameter names match their registrations.
- Return new or modified data for automatic publication. After an in-place
  change, call `app.data_model.update(app.data_model.index(data))`.
- Workflow `ParameterStep` uses the same `BoolParameter`/`IntParameter`/
  `FloatParameter`/`StringParameter`/`ChoiceParameter` classes as action
  parameters. Use `InputSelectionStep` and `inputs_from` when input roles must
  remain stable across repeated runs.
- Completing the final workflow step resets session data and views. Export or
  otherwise persist required results before completion.
- When creating derived images, follow the `work-with-imfusion-images` skill.
