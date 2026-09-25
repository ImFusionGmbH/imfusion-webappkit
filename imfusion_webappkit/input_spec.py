"""Shared input metadata for actions, algorithms, and workflows."""

from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class InputSpec:
    """Describe one named data input exposed to the web client."""

    key: str
    label: str
    required: bool = True

    def __post_init__(self) -> None:
        if not self.key or not self.key.isidentifier():
            raise ValueError(f"Input key must be a valid identifier: {self.key!r}")
        if not self.label:
            raise ValueError("Input label cannot be empty")

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation."""
        return {
            "key": self.key,
            "label": self.label,
            "required": self.required,
        }


def normalize_input_specs(
    inputs: Optional[Iterable[InputSpec]],
    *,
    default: bool = True,
) -> List[InputSpec]:
    """Validate input specifications and optionally provide one default input."""
    specs = (
        list(inputs)
        if inputs is not None
        else ([InputSpec("image", "Image")] if default else [])
    )
    keys = [spec.key for spec in specs]
    if len(keys) != len(set(keys)):
        raise ValueError("Input keys must be unique")
    return specs
