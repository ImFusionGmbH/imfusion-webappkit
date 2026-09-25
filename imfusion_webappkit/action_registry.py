"""
Action Registry for managing image processing callbacks.
"""

import inspect
from collections.abc import Mapping
from typing import Callable, Dict, List, Optional, Any, Sequence

from .input_spec import InputSpec, normalize_input_specs
from .parameter_spec import (
    ParameterDefinition,
    normalize_parameter_specs,
    resolve_annotation_parameters,
    validate_parameter_values,
)


class ActionRegistry:
    """Registry for image processing actions."""

    def __init__(self):
        self._actions: Dict[str, Callable] = {}
        self._action_metadata: Dict[str, dict] = {}  # Stores metadata about each action

    def register(
        self,
        name: str,
        callback: Callable,
        inputs: Optional[List[InputSpec]] = None,
        result_input: Optional[str] = None,
        parameters: Optional[Sequence[ParameterDefinition]] = None,
    ):
        """
        Register a new action.

        Args:
            name: Display name for the action (will appear as button label)
            callback: Function that processes data. Can have these signatures:
                - callback(image) -> image  (classic image processing)
                - callback(image, app) -> image  (with app access)
                - callback(app) -> None  (app-only action, no image input/output)
            parameters: Browser-editable values passed to the callback by name.

        The callback signature is auto-detected using introspection.
        """
        if name in self._actions:
            raise ValueError(f"Action '{name}' already registered")

        parameter_specs = normalize_parameter_specs(parameters)
        parameter_names = {spec.name for spec in parameter_specs}

        # Analyze the callback signature.
        sig = inspect.signature(callback)
        signature_parameters = sig.parameters
        accepts_keywords = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature_parameters.values()
        )
        missing_parameters = parameter_names - set(signature_parameters)
        if missing_parameters and not accepts_keywords:
            raise ValueError(
                f"Action parameters missing from callback signature: "
                f"{sorted(missing_parameters)!r}"
            )
        for parameter_name in parameter_names:
            callback_parameter = signature_parameters.get(parameter_name)
            if (
                callback_parameter is not None
                and callback_parameter.kind == inspect.Parameter.POSITIONAL_ONLY
            ):
                raise ValueError(
                    f"Action parameter '{parameter_name}' must accept keyword values"
                )

        data_parameters = [
            param
            for param in signature_parameters.values()
            if param.name not in parameter_names
            and param.name not in {"app", "self"}
            and param.kind
            not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        ]
        if len(data_parameters) > 1:
            raise ValueError(
                "Actions accept one data argument; declare browser-editable "
                "arguments with parameters="
            )
        if (
            data_parameters
            and data_parameters[0].kind == inspect.Parameter.KEYWORD_ONLY
        ):
            raise ValueError("The action data argument cannot be keyword-only")

        needs_image = bool(data_parameters)
        needs_app = "app" in signature_parameters
        is_app_only = not needs_image
        if (
            parameter_specs
            and needs_app
            and signature_parameters["app"].kind == inspect.Parameter.POSITIONAL_ONLY
        ):
            raise ValueError(
                "'app' must accept a keyword value for parameterized actions"
            )

        input_specs = normalize_input_specs(inputs, default=not is_app_only)
        if is_app_only and input_specs:
            raise ValueError("App-only actions cannot declare data inputs")
        if not is_app_only and not input_specs:
            raise ValueError("Data actions must declare at least one input")
        if input_specs and not any(spec.required for spec in input_specs):
            raise ValueError("Data actions must declare at least one required input")
        if result_input is not None and result_input not in {
            spec.key for spec in input_specs
        }:
            raise ValueError(f"Unknown result input key: {result_input!r}")

        self._actions[name] = callback
        self._action_metadata[name] = {
            "needs_image": needs_image and not is_app_only,
            "needs_app": needs_app,
            "is_app_only": is_app_only,
            "inputs": input_specs,
            "parameters": parameter_specs,
            "result_input": result_input
            or (input_specs[0].key if input_specs else None),
        }

    def remove_action(self, name: str):
        """Remove an action from the registry."""
        if name in self._actions:
            del self._actions[name]
            del self._action_metadata[name]

    def get_action(self, name: str) -> Callable:
        """Get the callback for a specific action."""
        if name not in self._actions:
            raise KeyError(f"Action '{name}' not found")
        return self._actions[name]

    def get_action_metadata(self, name: str) -> dict:
        """Get metadata about an action."""
        if name not in self._action_metadata:
            raise KeyError(f"Action '{name}' not found")
        return self._action_metadata[name]

    def list_actions(self) -> List[str]:
        """Get a list of all registered action names."""
        return list(self._actions.keys())

    def list_action_descriptors(self) -> List[dict]:
        """Return browser-safe action metadata."""
        descriptors = []
        for name in self.list_actions():
            metadata = self.get_action_metadata(name)
            descriptors.append(
                {
                    "name": name,
                    "is_app_only": metadata["is_app_only"],
                    "inputs": [spec.to_dict() for spec in metadata["inputs"]],
                    "parameters": {
                        spec.name: spec.to_dict() for spec in metadata["parameters"]
                    },
                }
            )
        return descriptors

    def has_action(self, name: str) -> bool:
        """Check if an action is registered."""
        return name in self._actions

    def execute_action(
        self,
        name: str,
        inputs: Optional[Any] = None,
        parameters: Optional[Mapping[str, Any]] = None,
        app: Optional[Any] = None,
    ) -> Optional[Any]:
        """
        Execute a registered action.

        Args:
            name: Name of the action to execute
            inputs: A role-keyed mapping for multi-input actions, or a single
                image for backward-compatible single-input actions.
            parameters: Browser-provided values for the declared parameters.

        Returns:
            Processed image, or None for app-only actions
        """
        callback = self.get_action(name)
        metadata = self.get_action_metadata(name)
        parameter_specs = metadata["parameters"]
        parameter_values = validate_parameter_values(parameter_specs, parameters)
        parameter_values = resolve_annotation_parameters(
            parameter_specs,
            parameter_values,
            getattr(app, "annotation_model", None),
        )

        if metadata["is_app_only"]:
            if parameter_specs:
                if metadata["needs_app"]:
                    parameter_values["app"] = app
                return callback(**parameter_values)
            if metadata["needs_app"]:
                return callback(app)
            return callback()
        input_specs = metadata["inputs"]
        if isinstance(inputs, Mapping):
            resolved = dict(inputs)
        elif len(input_specs) == 1:
            resolved = {input_specs[0].key: inputs}
        else:
            raise ValueError(f"Action '{name}' requires role-keyed inputs")

        callback_input = (
            resolved[input_specs[0].key] if len(input_specs) == 1 else resolved
        )
        if parameter_specs:
            if metadata["needs_app"]:
                parameter_values["app"] = app
            return callback(callback_input, **parameter_values)
        if metadata["needs_app"]:
            return callback(callback_input, app)
        return callback(callback_input)
