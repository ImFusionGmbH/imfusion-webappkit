"""Optional step-based orchestration for WebAppKit sessions."""

# Workflow orchestration intentionally coordinates step-private lifecycle state.
# pylint: disable=protected-access,broad-exception-caught

from __future__ import annotations

from abc import ABC, abstractmethod
import copy
from enum import Enum
import inspect
import logging
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    TYPE_CHECKING,
    Union,
)

from .annotation_model import Annotation, AnnotationType
from .config import ViewType
from .data_export import ExportFormat, SUPPORTED_EXPORT_FORMATS
from .input_spec import InputSpec, normalize_input_specs
from .parameter_spec import (
    ParameterDefinition,
    ParameterSpec,
    normalize_parameter_specs,
    validate_parameter_values,
)
from .ui_elements import AnnotationField, Button, Fields, UIElement

if TYPE_CHECKING:
    from .application_controller import WebApplicationController

logger = logging.getLogger(__name__)


class StepUIType(str, Enum):
    PARAMETERS = "parameters"
    PROCESSING = "processing"
    BRUSH = "brush"
    ANNOTATION = "annotation"
    VALIDATION = "validation"
    EXPORT = "export"
    MESSAGE = "message"
    CUSTOM = "custom"
    DATA_SELECTION = "data_selection"


class WorkflowStep(ABC):
    """Base class for workflow state and presentation."""

    def __init__(
        self,
        title: str,
        step_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ):
        self.title = title
        self.id = step_id or title
        self.depends_on = depends_on or []
        self._completed = False
        self._workflow: Optional["Workflow"] = None
        self._dependencies_hash: Optional[int] = None

    @property
    def app(self) -> "WebApplicationController":
        if self._workflow is None:
            raise RuntimeError("Step has not been added to a workflow")
        return self._workflow.app

    @property
    def completed(self) -> bool:
        """Whether the step reports itself as finished."""
        return self._completed

    @completed.setter
    def completed(self, value: bool) -> None:
        self._completed = bool(value)

    @property
    def data_model(self):
        return self.app.data_model

    def bind(self, workflow: "Workflow") -> None:
        if self._workflow is not None and self._workflow is not workflow:
            raise ValueError("A workflow step cannot be reused across workflows")
        self._workflow = workflow

    def clone(self) -> "WorkflowStep":
        """Return an unbound copy of this step, ready to bind to a new workflow.

        Relies on subclasses resetting mutable fields to fresh objects (not
        mutating in place) in ``reset_state``/``reset_workflow_state``.
        """
        cloned = copy.copy(self)
        cloned._workflow = None
        cloned._dependencies_hash = None
        cloned.reset_workflow_state()
        return cloned

    @abstractmethod
    def get_ui_config(self) -> Dict[str, Any]:
        pass

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> bool:
        return True

    def on_data_model_changed(self) -> None:
        """React to session data changes while this step is active."""

    @abstractmethod
    def can_proceed(self) -> Tuple[bool, str]:
        pass

    def can_go_back(self) -> bool:
        return True

    def receive_data(self, data: Dict[str, Any]) -> None:
        del data

    def dependency_value(self) -> Any:
        return self._completed

    def reset_state(self) -> None:
        self._completed = False

    def reset_workflow_state(self) -> None:
        """Reset state and any history retained across step navigation."""
        self.reset_state()

    def _resolve_from_step(
        self,
        step_id: str,
        role: Optional[str] = None,
        *,
        role_argument: str = "role",
    ) -> Any:
        """Return the dataset another step provides, by role where it has several.

        Resolved to an object reference rather than an index, and re-resolved on
        every entry, because indices shift whenever the model changes.
        """
        step = self._workflow.get_step(step_id)
        if isinstance(step, InputSelectionStep):
            inputs = step.inputs
            if role:
                if role not in inputs:
                    raise ValueError(
                        f"Input role {role!r} is not selected in step {step_id!r}"
                    )
                return inputs[role]
            if len(inputs) != 1:
                raise ValueError(
                    f"Step {step_id!r} has multiple inputs; set {role_argument}"
                )
            return next(iter(inputs.values()))
        if isinstance(step, ProcessingStep):
            outputs = [
                value
                for value in step._published_outputs
                if self.data_model.contains(value)
            ]
            if not outputs:
                result = step.result
                outputs = (
                    list(result)
                    if isinstance(result, (list, tuple))
                    else [result] if result is not None else []
                )
            if len(outputs) != 1:
                raise ValueError(f"Step {step_id!r} must provide exactly one dataset")
            return outputs[0]
        raise ValueError(
            f"Data source must reference an InputSelectionStep or ProcessingStep: "
            f"{step_id}"
        )

    def _compute_dependencies_hash(self) -> int:
        if self._workflow is None:
            return 0
        values = []
        for dependency_id in self.depends_on:
            dependency = self._workflow.get_step(dependency_id)
            if dependency is not None:
                values.append((dependency_id, repr(dependency.dependency_value())))
        return hash(tuple(values))

    def _check_dependencies_changed(self) -> bool:
        value = self._compute_dependencies_hash()
        changed = (
            self._dependencies_hash is not None and value != self._dependencies_hash
        )
        self._dependencies_hash = value
        return changed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "completed": self._completed,
            "ui_config": self.get_ui_config(),
        }


class Workflow:
    """Manage a sequence of steps for one session controller."""

    def __init__(
        self,
        app: "WebApplicationController",
        steps: Optional[List[WorkflowStep]] = None,
    ):
        self.app = app
        self.steps: List[WorkflowStep] = []
        self._current_index = 0
        self._started = False
        self._handling_data_change = False
        for step in steps or []:
            self.add_step(step)

    def add_step(self, step: WorkflowStep) -> "Workflow":
        if self.get_step(step.id) is not None:
            raise ValueError(f"Duplicate workflow step id: {step.id!r}")
        step.bind(self)
        self.steps.append(step)
        return self

    @property
    def current_step(self) -> Optional[WorkflowStep]:
        if 0 <= self._current_index < len(self.steps):
            return self.steps[self._current_index]
        return None

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def is_first_step(self) -> bool:
        return self._current_index == 0

    @property
    def is_last_step(self) -> bool:
        return bool(self.steps) and self._current_index == len(self.steps) - 1

    def get_step(self, step_id: str) -> Optional[WorkflowStep]:
        return next((step for step in self.steps if step.id == step_id), None)

    def start(self) -> None:
        if self.steps and not self._started:
            self._started = True
            self._current_index = 0
            self.steps[0].on_enter()
            self._sync_state()

    def reset(self) -> None:
        for step in self.steps:
            step.reset_workflow_state()
        self.app.data_model.clear()
        self.app._session.send_message("reset_views", {})
        self._current_index = 0
        self._started = True
        if self.steps:
            self.steps[0].on_enter()
        self._sync_state()

    def next_step(self) -> Tuple[bool, str]:
        current = self.current_step
        if current is None:
            return False, "No current workflow step"
        allowed, message = current.can_proceed()
        if not allowed:
            return False, message
        if self.is_last_step:
            self.reset()
            return True, "Workflow completed"
        if not current.on_exit():
            return False, "Cannot leave current step"
        current._completed = True
        self._current_index += 1
        next_step = self.current_step
        if next_step:
            next_step._dependencies_hash = next_step._compute_dependencies_hash()
            next_step.on_enter()
        self._sync_state()
        return True, ""

    def run_current_step(self, action: Optional[str] = None) -> Tuple[bool, str]:
        """Run a manually triggered processing step or custom step action."""
        current = self.current_step
        if isinstance(current, CustomStep):
            if action is None:
                return False, "Current workflow step has no automatic action"
            # A failing action still needs to publish whatever it changed before
            # the browser reports the error.
            try:
                self._apply_step_change(current, lambda: current.run_action(action))
            finally:
                self._sync_state()
            return True, ""
        if not isinstance(current, ProcessingStep):
            return False, "Current workflow step is not a processing step"
        if current.auto_run:
            return False, "Current processing step runs automatically"
        current.run()
        self._sync_state()
        return True, ""

    def previous_step(self) -> Tuple[bool, str]:
        current = self.current_step
        if current is None:
            return False, "No current workflow step"
        if self.is_first_step:
            return False, "Already at first step"
        if not current.can_go_back() or not current.on_exit():
            return False, "Cannot go back from current step"
        current.reset_state()
        self._current_index -= 1
        self._invalidate_dependents(self.current_step.id)
        self.current_step.on_enter()
        self._sync_state()
        return True, ""

    def receive_step_data(self, data: Dict[str, Any]) -> None:
        current = self.current_step
        if current is None:
            return
        self._apply_step_change(current, lambda: current.receive_data(data))
        self._sync_state()

    def _apply_step_change(
        self, step: WorkflowStep, mutate: Callable[[], None]
    ) -> None:
        """Apply a step mutation, invalidating dependents when its value changes."""
        old_value = repr(step.dependency_value())
        mutate()
        if old_value != repr(step.dependency_value()):
            self._invalidate_dependents(step.id)

    def _invalidate_dependents(self, changed_id: str) -> None:
        for step in self.steps:
            if changed_id in step.depends_on and step._check_dependencies_changed():
                step.reset_state()
                self._invalidate_dependents(step.id)

    def get_state(self) -> Dict[str, Any]:
        current = self.current_step
        allowed, message = current.can_proceed() if current else (False, "")
        return {
            "enabled": True,
            "current_index": self._current_index,
            "total_steps": self.total_steps,
            "is_first_step": self.is_first_step,
            "is_last_step": self.is_last_step,
            "current_step": current.to_dict() if current else None,
            "steps": [
                {"id": step.id, "title": step.title, "completed": step._completed}
                for step in self.steps
            ],
            "can_proceed": allowed,
            "proceed_message": message,
            "can_go_back": bool(
                current and current.can_go_back() and not self.is_first_step
            ),
        }

    def _on_data_model_changed(self) -> None:
        """Let the active step react to session data changes, then push state."""
        current = self.current_step
        if current is not None and self._started and not self._handling_data_change:
            # Invalidating dependents can remove generated data, which would
            # re-enter this handler before the current pass finished.
            self._handling_data_change = True
            try:
                current.on_data_model_changed()
            finally:
                self._handling_data_change = False
        self._sync_state()

    def _sync_state(self) -> None:
        self.app._session.send_message("workflow_state", self.get_state())


class MessageStep(WorkflowStep):
    def __init__(
        self,
        title: str,
        message: str,
        step_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ):
        super().__init__(title, step_id, depends_on)
        self.message = message

    def get_ui_config(self) -> Dict[str, Any]:
        return {"type": StepUIType.MESSAGE.value, "message": self.message}

    def can_proceed(self) -> Tuple[bool, str]:
        return True, ""


class InputSelectionStep(WorkflowStep):
    def __init__(
        self,
        title: str = "Select Inputs",
        inputs: Optional[List[InputSpec]] = None,
        allow_upload: bool = True,
        allow_sample_datasets: Optional[bool] = None,
        message: str = "Load datasets, then assign each input role.",
        step_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ):
        super().__init__(title, step_id, depends_on)
        self.input_specs = normalize_input_specs(inputs)
        self.allow_upload = allow_upload
        # Offering the app's sample datasets is another way of adding data, so
        # it follows allow_upload unless the caller decides otherwise.
        self.allow_sample_datasets = (
            allow_upload if allow_sample_datasets is None else allow_sample_datasets
        )
        self.message = message
        # Roles map to data references, not indices: indices shift whenever any
        # other dataset is added or removed, which would silently rebind a role.
        self.assignments: Dict[str, Any] = {}
        self._known_data: List[Any] = []

    @property
    def inputs(self) -> Dict[str, Any]:
        return {
            spec.key: value
            for spec in self.input_specs
            if (value := self.assignments.get(spec.key)) is not None
            and self.data_model.contains(value)
        }

    def _dataset_index(self, value: Any) -> Optional[int]:
        return self.data_model.index(value) if self.data_model.contains(value) else None

    def _is_assigned(self, value: Any) -> bool:
        return any(value is assigned for assigned in self.assignments.values())

    def _prune_assignments(self) -> bool:
        stale = [
            key
            for key, value in self.assignments.items()
            if not self.data_model.contains(value)
        ]
        for key in stale:
            del self.assignments[key]
        return bool(stale)

    def _fill_required_roles(self, candidates: List[Any]) -> bool:
        """Assign unassigned required roles in declaration order."""
        available = [value for value in candidates if not self._is_assigned(value)]
        changed = False
        for spec in self.input_specs:
            if not available:
                break
            if not spec.required or self.assignments.get(spec.key) is not None:
                continue
            self.assignments[spec.key] = available.pop(0)
            changed = True
        return changed

    def _assign_loaded_data(self, loaded: List[Any]) -> bool:
        if not loaded:
            return False
        if len(self.input_specs) == 1:
            # A single role follows the newest dataset, so loading another image
            # replaces the previous choice instead of piling up alongside it.
            spec = self.input_specs[0]
            if self.assignments.get(spec.key) is loaded[-1]:
                return False
            self.assignments[spec.key] = loaded[-1]
            return True
        return self._fill_required_roles(loaded)

    def _apply_visibility(self) -> None:
        self.app.select_data(list(self.inputs.values()))

    def on_enter(self) -> None:
        self._known_data = list(self.data_model)
        self._prune_assignments()
        self._fill_required_roles(self._known_data)
        self._apply_visibility()

    def on_data_model_changed(self) -> None:
        current = list(self.data_model)
        loaded = [
            value
            for value in current
            if not any(value is known for known in self._known_data)
        ]
        changed = self._prune_assignments()
        changed = self._assign_loaded_data(loaded) or changed
        self._known_data = current
        if changed:
            self._apply_visibility()
            if self._workflow is not None:
                self._workflow._invalidate_dependents(self.id)

    def get_ui_config(self) -> Dict[str, Any]:
        values = {}
        for spec in self.input_specs:
            value = self.assignments.get(spec.key)
            index = None if value is None else self._dataset_index(value)
            if index is not None:
                values[spec.key] = index
        return {
            "type": StepUIType.DATA_SELECTION.value,
            "inputs": [spec.to_dict() for spec in self.input_specs],
            "values": values,
            "datasets": [
                {"index": index, "name": self.data_model.get_name(index)}
                for index in range(len(self.data_model))
            ],
            "allow_upload": self.allow_upload,
            "allow_sample_datasets": self.allow_sample_datasets,
            "message": self.message,
        }

    def receive_data(self, data: Dict[str, Any]) -> None:
        values = data.get("inputs")
        if not isinstance(values, dict):
            return
        valid = {spec.key for spec in self.input_specs}
        self.assignments = {
            key: self.data_model[index]
            for key, index in values.items()
            if key in valid
            and isinstance(index, int)
            and 0 <= index < len(self.data_model)
        }
        self._apply_visibility()

    def can_proceed(self) -> Tuple[bool, str]:
        selected = []
        for spec in self.input_specs:
            value = self.assignments.get(spec.key)
            if value is None:
                if spec.required:
                    return False, f"Please select {spec.label}"
                continue
            if not self.data_model.contains(value):
                return False, f"Selected {spec.label} is no longer available"
            selected.append(id(value))
        if len(selected) != len(set(selected)):
            return False, "Each input must use a different dataset"
        return True, ""

    def dependency_value(self) -> Any:
        return tuple(
            (spec.key, id(self.assignments.get(spec.key))) for spec in self.input_specs
        )

    def reset_state(self) -> None:
        super().reset_state()
        self.assignments = {}
        self._known_data = []


class ParameterStep(WorkflowStep):
    """Collect browser-editable values using the same typed parameters as actions."""

    def __init__(
        self,
        title: str = "Configure",
        parameters: Optional[Sequence[ParameterDefinition]] = None,
        step_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ):
        super().__init__(title, step_id, depends_on)
        self.parameter_specs = normalize_parameter_specs(parameters)
        self.values: Dict[str, Any] = {}
        self._set_defaults()

    def _set_defaults(self) -> None:
        self.values = {spec.name: spec.default for spec in self.parameter_specs}

    def get_ui_config(self) -> Dict[str, Any]:
        descriptors = []
        for spec in self.parameter_specs:
            descriptor = spec.to_dict()
            descriptor["value"] = self.values.get(spec.name, spec.default)
            descriptors.append(descriptor)
        return {"type": StepUIType.PARAMETERS.value, "parameters": descriptors}

    def receive_data(self, data: Dict[str, Any]) -> None:
        updates = data.get("parameters")
        if not isinstance(updates, dict):
            return
        self.values = validate_parameter_values(
            self.parameter_specs, {**self.values, **updates}
        )

    def can_proceed(self) -> Tuple[bool, str]:
        return True, ""

    def dependency_value(self) -> Any:
        return tuple(sorted(self.values.items()))

    def reset_state(self) -> None:
        super().reset_state()
        self._set_defaults()


class ProcessingStep(WorkflowStep):
    """Run an action-style callback automatically or from an explicit button."""

    def __init__(
        self,
        title: str = "Processing",
        callback: Optional[Callable[..., Any]] = None,
        inputs_from: Optional[str] = None,
        parameters_from: Optional[str] = None,
        auto_proceed: bool = False,
        auto_run: bool = True,
        run_label: str = "Run",
        step_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ):
        inferred = list(depends_on or [])
        for dependency in (inputs_from, parameters_from):
            if dependency and dependency not in inferred:
                inferred.append(dependency)
        super().__init__(title, step_id, inferred)
        self.callback = callback
        self.inputs_from = inputs_from
        self.parameters_from = parameters_from
        self.auto_proceed = auto_proceed
        self.auto_run = auto_run
        self.run_label = run_label
        self.result: Any = None
        self._error: Optional[str] = None
        self._published_outputs: List[Any] = []
        self._last_source_inputs: List[Any] = []

    def _infer_processing_inputs(self) -> Any:
        if self.inputs_from:
            step = self._workflow.get_step(self.inputs_from)
            if not isinstance(step, InputSelectionStep):
                raise ValueError(
                    f"inputs_from must reference an InputSelectionStep: {self.inputs_from}"
                )
            values = step.inputs
            return next(iter(values.values())) if len(values) == 1 else values
        selected = self.app.selected_data
        if selected:
            source_selection = [
                item
                for item in selected
                if not any(item is output for output in self._published_outputs)
            ]
            if source_selection:
                return (
                    source_selection[0]
                    if len(source_selection) == 1
                    else source_selection
                )
            retained_sources = [
                item
                for item in self._last_source_inputs
                if not hasattr(self.data_model, "contains")
                or self.data_model.contains(item)
            ]
            if retained_sources:
                return (
                    retained_sources[0]
                    if len(retained_sources) == 1
                    else retained_sources
                )
        if len(self.data_model) == 1:
            return self.data_model[0]
        return None

    def _resolve_parameters(self) -> Dict[str, Any]:
        if not self.parameters_from:
            return {}
        step = self._workflow.get_step(self.parameters_from)
        if not isinstance(step, ParameterStep):
            raise ValueError(
                "parameters_from must reference a ParameterStep: "
                f"{self.parameters_from}"
            )
        return dict(step.values)

    def on_enter(self) -> None:
        if self.auto_run:
            self.run()

    def run(self) -> None:
        """Execute the processing callback once for the current inputs."""
        if self.callback is None or self._completed:
            return
        try:
            inputs = self._infer_processing_inputs()
            parameters = self._resolve_parameters()
            signature = inspect.signature(self.callback)
            kwargs = dict(parameters)
            if "app" in signature.parameters:
                kwargs["app"] = self.app

            # Named multi-input roles are unpacked as keyword arguments when the
            # callback declares a parameter per role (e.g. `def register(fixed,
            # moving, app)`), the same way pytest unpacks parametrized values by
            # name. Callbacks that instead take a single catch-all parameter
            # (e.g. `def register(inputs, app)`) keep receiving the raw dict.
            unpack_named_inputs = isinstance(inputs, dict) and any(
                key in signature.parameters for key in inputs
            )
            if unpack_named_inputs:
                kwargs.update(
                    {
                        key: value
                        for key, value in inputs.items()
                        if key in signature.parameters
                    }
                )
                self.result = self.callback(**kwargs)
            else:
                non_keyword = [
                    item
                    for item in signature.parameters.values()
                    if item.name not in kwargs
                    and item.name != "app"
                    and item.kind
                    not in {
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                        inspect.Parameter.KEYWORD_ONLY,
                    }
                ]
                self.result = (
                    self.callback(inputs, **kwargs)
                    if non_keyword
                    else self.callback(**kwargs)
                )
            source_inputs = (
                list(inputs.values())
                if isinstance(inputs, dict)
                else (
                    list(inputs)
                    if isinstance(inputs, list)
                    else [inputs] if inputs is not None else []
                )
            )
            self._last_source_inputs = source_inputs
            published = self.app.publish_results(
                self.result,
                self.title,
                source_inputs,
                replace=self._published_outputs,
            )
            self._published_outputs = [
                output
                for output in published
                if not any(output is item for item in source_inputs)
            ]
            self._completed = True
            self._error = None
            if self.auto_proceed and self._workflow is not None:
                success, message = self._workflow.next_step()
                if not success:
                    raise RuntimeError(message)
        except Exception as exc:
            logger.error("Processing step failed: %s", exc, exc_info=True)
            self._error = str(exc)
            self._completed = False
            if self._workflow is not None:
                self._workflow._sync_state()
            raise RuntimeError(f"Processing failed: {exc}") from exc

    def get_ui_config(self) -> Dict[str, Any]:
        return {
            "type": StepUIType.PROCESSING.value,
            "message": (
                "Processing complete"
                if self._completed
                else "Ready to run" if not self.auto_run else "Processing..."
            ),
            "completed": self._completed,
            "error": self._error,
            "auto_proceed": self.auto_proceed,
            "auto_run": self.auto_run,
            "run_label": self.run_label,
        }

    def can_proceed(self) -> Tuple[bool, str]:
        if self._error:
            return False, f"Processing failed: {self._error}"
        return (True, "") if self._completed else (False, "Processing not complete")

    def reset_state(self) -> None:
        super().reset_state()
        self.result = None
        self._error = None

    def reset_workflow_state(self) -> None:
        self.reset_state()
        self._published_outputs = []
        self._last_source_inputs = []


class BrushStep(WorkflowStep):
    """Create or edit a label map with the browser's smart brush."""

    def __init__(
        self,
        title: str = "Edit Label Map",
        message: str = "Start the brush, paint in the viewer, then stop it to save your edits.",
        image_from: Optional[str] = None,
        label_map_from: Optional[str] = None,
        image_role: Optional[str] = None,
        label_map_role: Optional[str] = None,
        radius_mm: float = 10.0,
        adaptiveness: float = 0.5,
        allow_radius_change: bool = True,
        allow_adaptiveness_change: bool = True,
        labels: Sequence[int] = (1,),
        label_map_name: str = "Label Map",
        step_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ):
        inferred = list(depends_on or [])
        for dependency in (image_from, label_map_from):
            if dependency and dependency not in inferred:
                inferred.append(dependency)
        super().__init__(title, step_id, inferred)
        if radius_mm <= 0:
            raise ValueError("radius_mm must be greater than zero")
        if not 0.0 <= adaptiveness <= 1.0:
            raise ValueError("adaptiveness must be between 0 and 1")
        labels = list(labels)
        if not labels:
            raise ValueError("labels must contain at least one value")
        if any(not isinstance(value, int) or value < 1 for value in labels):
            raise ValueError("labels must contain integers of at least 1")
        if len(set(labels)) != len(labels):
            raise ValueError("labels must not contain duplicate values")
        self.message = message
        self.image_from = image_from
        self.label_map_from = label_map_from
        self.image_role = image_role
        self.label_map_role = label_map_role
        self.radius_mm = float(radius_mm)
        self.adaptiveness = float(adaptiveness)
        self.allow_radius_change = allow_radius_change
        self.allow_adaptiveness_change = allow_adaptiveness_change
        self.labels = labels
        self.label_map_name = label_map_name
        self._image: Any = None
        self._label_map: Any = None
        self._created_label_map = False
        self._edit_revision = 0
        self._enter_revision = 0

    def _resolve_data(self) -> None:
        label_step = (
            self._workflow.get_step(self.label_map_from)
            if self.label_map_from
            else None
        )
        retained_label_map = (
            self._label_map
            if self._label_map is not None and self.data_model.contains(self._label_map)
            else None
        )
        self._label_map = (
            retained_label_map
            if retained_label_map is not None
            else (
                self._resolve_from_step(
                    self.label_map_from,
                    self.label_map_role,
                    role_argument="label_map_role",
                )
                if self.label_map_from
                else None
            )
        )
        if self.image_from:
            self._image = self._resolve_from_step(
                self.image_from, self.image_role, role_argument="image_role"
            )
        elif isinstance(label_step, ProcessingStep):
            sources = [
                value
                for value in label_step._last_source_inputs
                if self.data_model.contains(value)
            ]
            if len(sources) != 1:
                raise ValueError(
                    "image_from is required when label_map_from does not have "
                    "exactly one source image"
                )
            self._image = sources[0]
        else:
            selected = [
                value
                for value in self.app.selected_data
                if value is not self._label_map
            ]
            if len(selected) != 1:
                raise ValueError(
                    "image_from is required unless exactly one source image is selected"
                )
            self._image = selected[0]

        if not self.data_model.contains(self._image):
            raise ValueError("Brush source image is no longer available")
        if self._label_map is not None and not self.data_model.contains(
            self._label_map
        ):
            raise ValueError("Brush label map is no longer available")

    def on_enter(self) -> None:
        self._enter_revision += 1
        self._resolve_data()
        # An existing label map is already a valid workflow result. Users can
        # continue without starting the brush when no correction is needed.
        # Creation-only steps still require a commit so the browser-created
        # label map is synchronized to the server.
        self._completed = self._label_map is not None
        visible = [self._image]
        if self._label_map is not None:
            visible.append(self._label_map)
        self.app.select_data(visible)

    def get_ui_config(self) -> Dict[str, Any]:
        image_index = (
            self.data_model.index(self._image)
            if self._image is not None and self.data_model.contains(self._image)
            else None
        )
        label_map_index = (
            self.data_model.index(self._label_map)
            if self._label_map is not None and self.data_model.contains(self._label_map)
            else None
        )
        return {
            "type": StepUIType.BRUSH.value,
            "message": self.message,
            "image_index": image_index,
            "label_map_index": label_map_index,
            "label_map_name": self.label_map_name,
            "radius_mm": self.radius_mm,
            "adaptiveness": self.adaptiveness,
            "allow_radius_change": self.allow_radius_change,
            "allow_adaptiveness_change": self.allow_adaptiveness_change,
            "labels": self.labels,
            "committed": self._completed,
            "entry_token": self._enter_revision,
        }

    def commit_label_map(self, label_map: Any, target_index: Optional[int]) -> int:
        previous_label_map = self._label_map
        expected_index = (
            self.data_model.index(previous_label_map)
            if previous_label_map is not None
            and self.data_model.contains(previous_label_map)
            else None
        )
        if target_index != expected_index:
            raise ValueError("Brush label map target changed while editing")
        if target_index is None:
            self.data_model._append_from_client(label_map, self.label_map_name)
            self._created_label_map = True
        else:
            self.data_model._replace_from_client(target_index, label_map)
            source_step = (
                self._workflow.get_step(self.label_map_from)
                if self.label_map_from
                else None
            )
            if isinstance(source_step, ProcessingStep):
                source_step._published_outputs = [
                    label_map if value is previous_label_map else value
                    for value in source_step._published_outputs
                ]
                if source_step.result is previous_label_map:
                    source_step.result = label_map
        self._label_map = label_map
        self._edit_revision += 1
        self._completed = True
        if self._workflow is not None:
            self._workflow._invalidate_dependents(self.id)
        return self.data_model.index(label_map)

    def receive_data(self, data: Dict[str, Any]) -> None:
        if data.get("editing") is True:
            self._completed = False

    def can_proceed(self) -> Tuple[bool, str]:
        return (
            (True, "")
            if self._completed
            else (False, "Save the label map before continuing")
        )

    def dependency_value(self) -> Any:
        return self._edit_revision

    def reset_state(self) -> None:
        super().reset_state()
        if (
            self._created_label_map
            and self._label_map is not None
            and self.data_model.contains(self._label_map)
        ):
            self.data_model.remove(self._label_map)
        self._image = None
        self._label_map = None
        self._created_label_map = False


#: Slice views, where a line or rectangle dragged by the user means something.
#: A rectangle dragged in a volume rendering does not.
_SLICE_VIEWS = (
    ViewType.TWO_D,
    ViewType.MPR,
    ViewType.AXIAL,
    ViewType.CORONAL,
    ViewType.SAGITTAL,
)

_DEFAULT_VIEWS: Dict[AnnotationType, Tuple[ViewType, ...]] = {
    AnnotationType.LINE: _SLICE_VIEWS,
    AnnotationType.RECTANGLE: _SLICE_VIEWS,
    AnnotationType.ANGLE: _SLICE_VIEWS,
    AnnotationType.POINT: _SLICE_VIEWS + (ViewType.THREE_D,),
    AnnotationType.BOX: _SLICE_VIEWS + (ViewType.THREE_D,),
}

#: Distinct colours per role, so two landmark sets on a fixed and a moving image
#: are not both yellow.
_ROLE_COLORS = (
    (1.0, 1.0, 0.0),
    (0.2, 0.8, 1.0),
    (1.0, 0.45, 0.8),
    (0.4, 1.0, 0.5),
)


class AnnotationStep(WorkflowStep):
    """Ask the user to place annotations, then hand the geometry to Python.

    One annotation is collected per entry in ``labels`` (or per ``count``) for
    each role in ``image_roles``. Placement is armed explicitly, by a button in
    the panel, so the first click on the canvas cannot become an annotation
    while the user is still navigating to the anatomy.

    Args:
        title: Step title shown in the workflow panel.
        message: Instruction shown above the placement controls.
        annotation_type: Shape the user places.
        image_from: Step id providing the dataset to annotate, either an
            ``InputSelectionStep`` or a ``ProcessingStep``. Without it the
            current selection is used, which must match the roles.
        image_role: Input role in ``image_from`` to annotate, when that step
            offers several.
        image_roles: Annotate one dataset per role, for example a fixed and a
            moving image. Each role names an input role in ``image_from``, and
            keys :attr:`annotations`. Mutually exclusive with ``image_role``.
        labels: One prompt per annotation, drawn next to it in the viewer and
            shown in the panel. Its length sets how many are collected.
        count: How many annotations to collect, when they need no labels.
        color: Fixed RGB or RGBA colour. Roles get distinct colours by default.
        required: Whether the step blocks until every annotation is placed.
        keep_annotations: Leave the annotations in the viewer after the step.
            They are reused if the user comes back. Turn this off for geometry
            that stops being meaningful later, such as a landmark on an image a
            later step registers, because an annotation does not follow its
            dataset's transform.
        views: Views the user may annotate in. Defaults to the slice views, plus
            the 3D view for point and box annotations.
        show_measurements: Show a line's length and an angle's angle.
        on_finished: Called once every annotation is placed, with no arguments
            or with the step, whichever the callback declares.
        step_id: Explicit id, for other steps to reference.
        depends_on: Extra step ids that invalidate this one; ``image_from`` is
            added automatically.
    """

    def __init__(
        self,
        title: str = "Place Annotation",
        message: str = "Press Place, then draw the annotation in the viewer.",
        annotation_type: AnnotationType = AnnotationType.RECTANGLE,
        image_from: Optional[str] = None,
        image_role: Optional[str] = None,
        image_roles: Optional[Sequence[str]] = None,
        labels: Optional[Sequence[str]] = None,
        count: int = 1,
        color: Optional[Sequence[float]] = None,
        required: bool = True,
        keep_annotations: bool = True,
        views: Optional[Sequence[ViewType]] = None,
        show_measurements: bool = False,
        on_finished: Optional[Callable[..., Any]] = None,
        step_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ):
        inferred = list(depends_on or [])
        if image_from and image_from not in inferred:
            inferred.append(image_from)
        super().__init__(title, step_id, inferred)

        if image_roles is not None and image_role is not None:
            raise ValueError("Set either image_role or image_roles, not both")
        if labels is not None:
            labels = [str(label) for label in labels]
            if not labels:
                raise ValueError("labels must contain at least one prompt")
            if count not in (1, len(labels)):
                raise ValueError("count must match the number of labels")
        elif count < 1:
            raise ValueError("count must be at least 1")

        self.message = message
        self.annotation_type = AnnotationType(annotation_type)
        self.image_from = image_from
        # A single unnamed role still needs a key, because `annotations` is a
        # dict in every case and callers should not have to special-case one.
        self.roles: List[str] = (
            [str(role) for role in image_roles]
            if image_roles
            else [image_role or "default"]
        )
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("image_roles must not repeat a role")
        self.image_roles = list(image_roles) if image_roles else None
        self.image_role = image_role
        self.labels: List[str] = labels if labels is not None else [""] * count
        self.color = tuple(color) if color is not None else None
        self.required = bool(required)
        self.keep_annotations = bool(keep_annotations)
        self.views: List[ViewType] = [
            ViewType(view)
            for view in (
                views
                if views is not None
                else _DEFAULT_VIEWS.get(self.annotation_type, _SLICE_VIEWS)
            )
        ]
        self.show_measurements = bool(show_measurements)
        self.on_finished = on_finished
        self._datasets: Dict[str, Any] = {}
        self._annotations: Dict[str, List[Annotation]] = {}
        self._revision = 0
        self._enter_revision = 0

    # ----- public state -----

    @property
    def annotations(self) -> Dict[str, List[Annotation]]:
        """Collected annotations, keyed by role and ordered by label."""
        return {role: list(self._annotations.get(role, [])) for role in self.roles}

    @property
    def points(self) -> List[List[Tuple[float, float, float]]]:
        """Every annotation's world points, flattened in role then label order."""
        return [
            annotation.points
            for role in self.roles
            for annotation in self._annotations.get(role, [])
        ]

    @property
    def complete(self) -> bool:
        """Whether every requested annotation has been placed."""
        collected = [
            annotation
            for role in self.roles
            for annotation in self._annotations.get(role, [])
        ]
        return len(collected) == len(self.roles) * len(self.labels) and all(
            annotation.complete for annotation in collected
        )

    def clear(self) -> None:
        """Remove the collected annotations from the viewer.

        Worth calling once the geometry has been consumed: an annotation does
        not follow its dataset's transform, so after a registration moves the
        image the annotation sits visibly detached from what it marked.
        """
        self._remove_annotations()
        self._bump_revision()

    def _remove_annotations(self) -> None:
        model = self.app.annotation_model
        for annotations in self._annotations.values():
            for annotation in annotations:
                model.remove(annotation)
        self._annotations = {}

    # ----- internals -----

    def _color_for_role(self, role: str) -> Tuple[float, ...]:
        if self.color is not None:
            return self.color
        return _ROLE_COLORS[self.roles.index(role) % len(_ROLE_COLORS)]

    def _sequence(self) -> List[Annotation]:
        """Annotations in the order they are collected."""
        return [
            annotation
            for role in self.roles
            for annotation in self._annotations.get(role, [])
        ]

    def _resolve_datasets(self) -> None:
        if not self.image_from:
            selected = self.app.selected_data
            if len(selected) != len(self.roles):
                raise ValueError(
                    "image_from is required unless the selection matches the roles"
                )
            self._datasets = dict(zip(self.roles, selected))
            return
        # A named role doubles as the input role in the source step, the same way
        # BrushStep's image_role does; an unnamed one resolves the step's only
        # dataset.
        named = self.image_roles is not None or self.image_role is not None
        self._datasets = {
            role: self._resolve_from_step(
                self.image_from,
                role if named else None,
                role_argument="image_roles" if self.image_roles else "image_role",
            )
            for role in self.roles
        }
        missing = [
            role
            for role, data in self._datasets.items()
            if not self.data_model.contains(data)
        ]
        if missing:
            raise ValueError(
                f"Annotation dataset for role {missing[0]!r} is no longer available"
            )

    def _create_annotations(self) -> None:
        """Create one annotation per label per role, reusing surviving ones."""
        model = self.app.annotation_model
        live = set(id(annotation) for annotation in model.annotations())
        created: Dict[str, List[Annotation]] = {}
        for role in self.roles:
            data = self._datasets[role]
            existing = [
                annotation
                for annotation in self._annotations.get(role, [])
                if id(annotation) in live and annotation.data is data
            ]
            annotations = existing[: len(self.labels)]
            for index in range(len(annotations), len(self.labels)):
                annotation = model.create_annotation(self.annotation_type, data)
                annotation.color = self._color_for_role(role)
                if self.labels[index]:
                    annotation.label = self.labels[index]
                annotation.on_editing_finished(self._annotation_finished)
                annotations.append(annotation)
            created[role] = annotations
        self._annotations = created

    def _pending(self) -> Optional[Annotation]:
        return next(
            (
                annotation
                for annotation in self._sequence()
                if not annotation.complete and not annotation.error
            ),
            None,
        )

    def _arm_next(self) -> None:
        pending = self._pending()
        if pending is not None and not pending.editing:
            pending.start_editing()

    def _replace(self, annotation: Annotation) -> Optional[Annotation]:
        """Swap an annotation for a fresh one in the same slot.

        A placed or aborted annotation cannot be re-armed — the Web SDK binds no
        way back into creation mode — so anything that looks like "try again"
        has to be a new annotation.
        """
        model = self.app.annotation_model
        for role, annotations in self._annotations.items():
            for index, candidate in enumerate(annotations):
                if candidate is not annotation:
                    continue
                model.remove(candidate)
                replacement = model.create_annotation(
                    self.annotation_type, self._datasets[role]
                )
                replacement.color = self._color_for_role(role)
                if self.labels[index]:
                    replacement.label = self.labels[index]
                replacement.on_editing_finished(self._annotation_finished)
                annotations[index] = replacement
                return replacement
        return None

    def _bump_revision(self) -> None:
        self._revision += 1
        self._completed = self.complete
        if self._workflow is not None:
            self._workflow._invalidate_dependents(self.id)

    def _annotation_finished(self, annotation: Annotation) -> None:
        """Advance the sequence when the user finishes one annotation."""
        del annotation
        self._bump_revision()
        if self.complete:
            if self.on_finished is not None:
                self._invoke_finished()
        else:
            # Arm the next prompt, so N landmarks cost one button press and N
            # clicks rather than N presses.
            self._arm_next()
        # The panel is republished by whoever delivered the event, so there is
        # no _sync_state here.

    def _invoke_finished(self) -> None:
        try:
            parameters = inspect.signature(self.on_finished).parameters
        except (TypeError, ValueError):
            parameters = {}
        try:
            if "step" in parameters:
                self.on_finished(step=self)
            elif parameters:
                self.on_finished(self)
            else:
                self.on_finished()
        except Exception:
            logger.error("AnnotationStep on_finished failed", exc_info=True)

    # ----- WorkflowStep -----

    def on_enter(self) -> None:
        self._enter_revision += 1
        self._resolve_datasets()
        self.app.select_data(list(self._datasets.values()))
        self._create_annotations()
        self._completed = self.complete

    def on_exit(self) -> bool:
        if not self.keep_annotations:
            self.clear()
        return True

    def get_ui_config(self) -> Dict[str, Any]:
        sequence = self._sequence()
        pending = self._pending()
        armed = next(
            (annotation for annotation in sequence if annotation.editing), None
        )
        errors = [annotation.error for annotation in sequence if annotation.error]
        return {
            "type": StepUIType.ANNOTATION.value,
            "message": self.message,
            "annotation_type": self.annotation_type.value,
            "required": self.required,
            "show_measurements": self.show_measurements,
            "views": [view.value for view in self.views],
            "armed_id": armed.id if armed is not None else None,
            "pending_id": pending.id if pending is not None else None,
            "placed": sum(1 for annotation in sequence if annotation.complete),
            "total": len(self.roles) * len(self.labels),
            "error": errors[0] if errors else "",
            "entry_token": self._enter_revision,
            "roles": [
                {
                    "role": role,
                    "labelled": self.image_roles is not None,
                    "data_index": (
                        self.data_model.index(self._datasets[role])
                        if role in self._datasets
                        and self.data_model.contains(self._datasets[role])
                        else None
                    ),
                    "data_name": (
                        self.data_model.get_name(self._datasets[role])
                        if role in self._datasets
                        and self.data_model.contains(self._datasets[role])
                        else ""
                    ),
                    "color": list(self._color_for_role(role)),
                    "annotations": [
                        {**annotation._descriptor(), "prompt": self.labels[index]}
                        for index, annotation in enumerate(
                            self._annotations.get(role, [])
                        )
                    ],
                }
                for role in self.roles
            ],
        }

    def receive_data(self, data: Dict[str, Any]) -> None:
        action = data.get("action")
        if action == "place":
            self._arm_next()
        elif action == "clear":
            self.clear()
            self._create_annotations()
            self._bump_revision()
        elif action == "redo":
            target = next(
                (
                    annotation
                    for annotation in self._sequence()
                    if annotation.id == data.get("id")
                ),
                None,
            )
            if target is None:
                # Default to undoing the last placement, which is what the
                # panel's single Redo button means.
                placed = [a for a in self._sequence() if a.complete or a.error]
                target = placed[-1] if placed else None
            if target is not None:
                replacement = self._replace(target)
                self._bump_revision()
                if replacement is not None:
                    replacement.start_editing()

    def on_data_model_changed(self) -> None:
        # The session drops annotations whose dataset disappears, so the step's
        # records can outlive the annotations they point at.
        live = set(
            id(annotation) for annotation in self.app.annotation_model.annotations()
        )
        surviving = {
            role: [a for a in annotations if id(a) in live]
            for role, annotations in self._annotations.items()
        }
        if surviving != self._annotations:
            self._annotations = surviving
            self._completed = self.complete

    def can_proceed(self) -> Tuple[bool, str]:
        if self.complete or not self.required:
            return True, ""
        error = next(
            (annotation.error for annotation in self._sequence() if annotation.error),
            "",
        )
        if error:
            return False, error
        pending = self._pending()
        prompt = pending.label if pending is not None else ""
        return False, f"Place {prompt or 'the annotation'} before continuing"

    def dependency_value(self) -> Any:
        return self._revision

    def reset_state(self) -> None:
        super().reset_state()
        if self._workflow is not None and not self.keep_annotations:
            self._remove_annotations()
        self._datasets = {}

    def reset_workflow_state(self) -> None:
        self._completed = False
        self._datasets = {}
        self._annotations = {}
        self._revision = 0


class ValidationStep(WorkflowStep):
    def __init__(
        self,
        title: str = "Review Result",
        message: str = "Is this result acceptable?",
        step_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ):
        super().__init__(title, step_id, depends_on)
        self.message = message
        self.accepted: Optional[bool] = None

    def get_ui_config(self) -> Dict[str, Any]:
        return {
            "type": StepUIType.VALIDATION.value,
            "message": self.message,
            "accepted": self.accepted,
        }

    def receive_data(self, data: Dict[str, Any]) -> None:
        if isinstance(data.get("accepted"), bool):
            self.accepted = data["accepted"]
            self._completed = self.accepted

    def can_proceed(self) -> Tuple[bool, str]:
        if self.accepted is True:
            return True, ""
        if self.accepted is False:
            return False, "Result was rejected. Go back to adjust parameters."
        return False, "Please accept or reject the result"

    def dependency_value(self) -> Any:
        return self.accepted

    def reset_state(self) -> None:
        super().reset_state()
        self.accepted = None


class ExportStep(WorkflowStep):
    def __init__(
        self,
        title: str = "Export",
        message: str = "Export your results",
        formats: Optional[Sequence[Union[str, ExportFormat]]] = None,
        step_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        require_export_before_finish: bool = True,
    ):
        super().__init__(title, step_id, depends_on)
        self.message = message
        requested_formats = formats or SUPPORTED_EXPORT_FORMATS
        self.formats = list(
            dict.fromkeys(ExportFormat(value) for value in requested_formats)
        )
        self.require_export_before_finish = require_export_before_finish
        self.exported = False

    def get_ui_config(self) -> Dict[str, Any]:
        return {
            "type": StepUIType.EXPORT.value,
            "message": self.message,
            "formats": [fmt.value for fmt in self.formats],
            "exported": self.exported,
            "require_export_before_finish": self.require_export_before_finish,
        }

    def receive_data(self, data: Dict[str, Any]) -> None:
        if data.get("exported"):
            self.exported = True
            self._completed = True

    def can_proceed(self) -> Tuple[bool, str]:
        if self.exported or not self.require_export_before_finish:
            return True, ""
        return False, "Please export your results"

    def reset_state(self) -> None:
        super().reset_state()
        self.exported = False


class CustomStep(WorkflowStep):
    """Step whose contents are described with :mod:`~imfusion_webappkit.ui_elements`.

    Pass a static ``body`` for a fixed layout, or subclass and override
    :meth:`body` to rebuild the elements from the current session state every
    time the browser refreshes. Subclasses handle button presses by overriding
    :meth:`on_action`.

    Args:
        title: Step title shown in the workflow panel.
        body: Elements displayed for the step.
        step_id: Stable identifier. Defaults to ``title``.
        depends_on: Identifiers of steps that invalidate this one.
        require_completion: Block **Next** until the step sets
            :attr:`~WorkflowStep.completed`.
        completion_message: Reason shown while completion is still required.
    """

    def __init__(
        self,
        title: str = "Custom",
        body: Optional[Sequence[UIElement]] = None,
        step_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        require_completion: bool = False,
        completion_message: str = "Complete this step before continuing",
    ):
        super().__init__(title, step_id, depends_on)
        self._static_body: List[UIElement] = list(body or ())
        for element in self._static_body:
            if not isinstance(element, UIElement):
                raise TypeError("Custom step body must contain UIElement instances")
        self.require_completion = bool(require_completion)
        self.completion_message = completion_message
        self._values: Dict[str, Any] = {}
        self._elements: Optional[List[UIElement]] = None

    def body(self) -> Sequence[UIElement]:
        """Return the elements to display. Override for dynamic content."""
        return self._static_body

    def on_action(self, action: str) -> None:
        """Handle a button press. Override to react to :class:`Button` elements."""

    @property
    def values(self) -> Dict[str, Any]:
        """Current values of every :class:`Fields` parameter, including defaults."""
        return {
            spec.name: self._values.get(spec.name, spec.default)
            for spec in self._parameter_specs()
        }

    def run_action(self, action: str) -> None:
        """Validate and dispatch one button press or field submission."""
        elements = self._current_elements()
        button = next(
            (
                element
                for element in elements
                if isinstance(element, Button) and element.action == action
            ),
            None,
        )
        if button is not None:
            if button.disabled:
                raise ValueError(f"Disabled custom step action: {action!r}")
        elif not any(
            (isinstance(element, Fields) and element.submit_action == action)
            or (
                isinstance(element, AnnotationField)
                and action in (element.place_action, element.clear_action)
            )
            for element in elements
        ):
            raise ValueError(f"Unknown custom step action: {action!r}")
        try:
            self.on_action(action)
        finally:
            self._elements = None

    def _current_elements(self) -> List[UIElement]:
        """Return the elements the browser last received.

        Rebuilding on every access would call a dynamic ``body()`` several times
        per state update, and would validate an incoming button press or field
        value against a layout the browser never rendered.
        """
        if self._elements is None:
            self._elements = list(self.body())
        return self._elements

    def _parameter_specs(self) -> List[ParameterSpec]:
        specs: List[ParameterSpec] = []
        for element in self._current_elements():
            if not isinstance(element, Fields):
                continue
            for spec in element.parameters:
                if any(existing.name == spec.name for existing in specs):
                    raise ValueError(f"Duplicate custom step parameter: {spec.name!r}")
                specs.append(spec)
        return specs

    def get_ui_config(self) -> Dict[str, Any]:
        self._elements = None
        values = self.values
        elements = []
        for element in self._current_elements():
            descriptor = element.to_dict()
            if isinstance(element, Fields):
                for parameter in descriptor["parameters"]:
                    parameter["value"] = values[parameter["name"]]
            elements.append(descriptor)
        return {"type": StepUIType.CUSTOM.value, "body": elements}

    def receive_data(self, data: Dict[str, Any]) -> None:
        updates = data.get("values")
        if isinstance(updates, dict):
            self._values = validate_parameter_values(
                self._parameter_specs(), {**self.values, **updates}
            )
            self._elements = None
        action = data.get("action")
        if isinstance(action, str):
            self.run_action(action)

    def can_proceed(self) -> Tuple[bool, str]:
        if self.require_completion and not self._completed:
            return False, self.completion_message
        return True, ""

    def dependency_value(self) -> Any:
        return tuple(sorted(self.values.items())), self._completed

    def reset_state(self) -> None:
        super().reset_state()
        self._values = {}
        self._elements = None
