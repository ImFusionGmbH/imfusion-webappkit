"""Typed parameter descriptions for configurable actions."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Any, Dict, List, Optional, Union

PARAMETER_TYPES = {"bool", "int", "float", "string", "choice", "annotation"}


@dataclass(frozen=True)
class ParameterSpec:
    """Describe and validate one browser-editable action parameter."""

    name: str
    type: str
    default: Any
    label: Optional[str] = None
    description: Optional[str] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None
    options: tuple[str, ...] = ()
    unit: Optional[str] = None
    placeholder: Optional[str] = None
    annotation_type: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.isidentifier():
            raise ValueError(f"Invalid parameter name: {self.name!r}")
        if self.name in {"app", "self"}:
            raise ValueError(f"Reserved parameter name: {self.name!r}")
        if self.type not in PARAMETER_TYPES:
            raise ValueError(f"Unsupported parameter type: {self.type!r}")
        if self.type == "annotation" and not self.annotation_type:
            raise ValueError("Annotation parameters must declare an annotation_type")
        if self.type != "annotation" and self.annotation_type:
            raise ValueError("Only annotation parameters can declare annotation_type")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("minimum cannot be greater than maximum")
        if self.step is not None and self.step <= 0:
            raise ValueError("step must be greater than zero")
        if self.type == "choice" and not self.options:
            raise ValueError("Choice parameters must declare at least one option")
        if self.type != "choice" and self.options:
            raise ValueError("Only choice parameters can declare options")
        object.__setattr__(self, "default", self.validate(self.default))

    def validate(self, value: Any) -> Any:
        """Validate and normalize one value received from the browser."""
        if self.type == "bool":
            if type(value) is not bool:
                raise ValueError(f"Parameter '{self.name}' must be a boolean")
            normalized = value
        elif self.type == "int":
            if not isinstance(value, Integral) or isinstance(value, bool):
                raise ValueError(f"Parameter '{self.name}' must be an integer")
            normalized = int(value)
        elif self.type == "float":
            if not isinstance(value, Real) or isinstance(value, bool):
                raise ValueError(f"Parameter '{self.name}' must be a number")
            normalized = float(value)
        elif self.type == "string":
            if not isinstance(value, str):
                raise ValueError(f"Parameter '{self.name}' must be a string")
            normalized = value
        elif self.type == "annotation":
            # On the wire an annotation is only its id: the geometry lives in
            # the session's annotation model, which validation cannot see. The
            # id is exchanged for an Annotation when the action runs.
            if not isinstance(value, str):
                raise ValueError(f"Parameter '{self.name}' must be an annotation id")
            normalized = value
        else:
            if value not in self.options:
                raise ValueError(
                    f"Parameter '{self.name}' must be one of {list(self.options)!r}"
                )
            normalized = value

        if self.type in {"int", "float"}:
            if self.minimum is not None and normalized < self.minimum:
                raise ValueError(
                    f"Parameter '{self.name}' must be at least {self.minimum}"
                )
            if self.maximum is not None and normalized > self.maximum:
                raise ValueError(
                    f"Parameter '{self.name}' must be at most {self.maximum}"
                )
        return normalized

    def to_dict(self) -> Dict[str, Any]:
        """Return the browser-safe parameter descriptor."""
        descriptor: Dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            # An explicit empty label ("") suppresses the label instead of
            # falling back to the name, e.g. for a field named by a
            # placeholder instead, such as a chat message composer.
            "label": (
                self.name.replace("_", " ").title()
                if self.label is None
                else self.label
            ),
            "value": self.default,
            "default": self.default,
        }
        optional_values = {
            "description": self.description,
            "min": self.minimum,
            "max": self.maximum,
            "step": self.step,
            "unit": self.unit,
            "placeholder": self.placeholder,
            "annotation_type": self.annotation_type,
        }
        descriptor.update(
            {key: value for key, value in optional_values.items() if value is not None}
        )
        if self.options:
            descriptor["options"] = list(self.options)
        return descriptor


class BoolParameter(ParameterSpec):
    """Boolean action parameter."""

    def __init__(
        self,
        name: str,
        *,
        default: bool = False,
        label: Optional[str] = None,
        description: Optional[str] = None,
    ):
        super().__init__(name, "bool", default, label, description)


class IntParameter(ParameterSpec):
    """Integer action parameter."""

    def __init__(
        self,
        name: str,
        *,
        default: int,
        label: Optional[str] = None,
        description: Optional[str] = None,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
        step: Optional[int] = None,
        unit: Optional[str] = None,
    ):
        super().__init__(
            name,
            "int",
            default,
            label,
            description,
            minimum,
            maximum,
            step,
            unit=unit,
        )


class FloatParameter(ParameterSpec):
    """Floating-point action parameter."""

    def __init__(
        self,
        name: str,
        *,
        default: float,
        label: Optional[str] = None,
        description: Optional[str] = None,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
        step: Optional[float] = None,
        unit: Optional[str] = None,
    ):
        super().__init__(
            name,
            "float",
            default,
            label,
            description,
            minimum,
            maximum,
            step,
            unit=unit,
        )


class StringParameter(ParameterSpec):
    """Text action parameter."""

    def __init__(
        self,
        name: str,
        *,
        default: str = "",
        label: Optional[str] = None,
        description: Optional[str] = None,
        placeholder: Optional[str] = None,
    ):
        super().__init__(
            name, "string", default, label, description, placeholder=placeholder
        )


class ChoiceParameter(ParameterSpec):
    """Action parameter restricted to a finite set of string values."""

    def __init__(
        self,
        name: str,
        *,
        options: Sequence[str],
        default: Optional[str] = None,
        label: Optional[str] = None,
        description: Optional[str] = None,
    ):
        normalized_options = tuple(options)
        if not normalized_options:
            raise ValueError("Choice parameters must declare at least one option")
        super().__init__(
            name,
            "choice",
            default if default is not None else normalized_options[0],
            label,
            description,
            options=normalized_options,
        )


class AnnotationParameter(ParameterSpec):
    """Action parameter the user fills in by drawing in the viewer.

    The callback receives an ``Annotation``, not an id: the browser sends the
    id and it is exchanged for the object when the action runs.
    """

    def __init__(
        self,
        name: str,
        *,
        annotation_type: Any,
        label: Optional[str] = None,
        description: Optional[str] = None,
    ):
        super().__init__(
            name,
            "annotation",
            "",
            label,
            description,
            annotation_type=str(getattr(annotation_type, "value", annotation_type)),
        )


ParameterDefinition = Union[ParameterSpec, Mapping[str, Any]]


def resolve_annotation_parameters(
    specs: Sequence[ParameterSpec],
    values: Dict[str, Any],
    annotation_model: Any,
) -> Dict[str, Any]:
    """Exchange annotation ids for the session's ``Annotation`` objects.

    Separate from :func:`validate_parameter_values` because validation only
    ever sees JSON from the browser, with no session in scope.
    """
    resolved = dict(values)
    for spec in specs:
        if spec.type != "annotation":
            continue
        annotation_id = resolved.get(spec.name) or ""
        annotation = (
            annotation_model._find(annotation_id)
            if annotation_id and annotation_model is not None
            else None
        )
        if annotation is None:
            label = spec.label or spec.name.replace("_", " ")
            raise ValueError(f"Place the {label} annotation before running this action")
        resolved[spec.name] = annotation
    return resolved


def normalize_parameter_specs(
    parameters: Optional[Sequence[ParameterDefinition]],
) -> List[ParameterSpec]:
    """Normalize public parameter definitions and reject duplicate names."""
    normalized: List[ParameterSpec] = []
    for definition in parameters or ():
        if isinstance(definition, ParameterSpec):
            spec = definition
        elif isinstance(definition, Mapping):
            values = dict(definition)
            parameter_type = values.pop("type")
            if "min" in values:
                values["minimum"] = values.pop("min")
            if "max" in values:
                values["maximum"] = values.pop("max")
            constructors = {
                "bool": BoolParameter,
                "int": IntParameter,
                "float": FloatParameter,
                "string": StringParameter,
                "choice": ChoiceParameter,
                "annotation": AnnotationParameter,
            }
            try:
                spec = constructors[parameter_type](**values)
            except KeyError as exc:
                raise ValueError(
                    f"Unsupported parameter type: {parameter_type!r}"
                ) from exc
        else:
            raise TypeError("Parameters must be ParameterSpec instances or mappings")
        if any(existing.name == spec.name for existing in normalized):
            raise ValueError(f"Duplicate parameter name: {spec.name!r}")
        normalized.append(spec)
    return normalized


def validate_parameter_values(
    specs: Sequence[ParameterSpec],
    values: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Validate browser values, applying defaults for omitted parameters."""
    supplied = dict(values or {})
    expected = {spec.name for spec in specs}
    unknown = set(supplied) - expected
    if unknown:
        raise ValueError(f"Unknown action parameters: {sorted(unknown)!r}")
    return {
        spec.name: spec.validate(supplied.get(spec.name, spec.default))
        for spec in specs
    }
