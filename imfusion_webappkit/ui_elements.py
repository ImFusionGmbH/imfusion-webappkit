"""Declarative UI elements rendered by :class:`~imfusion_webappkit.workflow.CustomStep`.

Elements describe what a custom step shows without requiring browser code. The
client renders every element it recognizes and skips the rest, so a step
written against a newer server degrades instead of failing.
"""

from abc import ABC, abstractmethod
import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from numbers import Real
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .parameter_spec import (
    ParameterDefinition,
    ParameterSpec,
    normalize_parameter_specs,
)

ALERT_LEVELS = ("info", "success", "warning", "danger")
BUTTON_STYLES = ("default", "primary", "danger")
CHART_VARIANTS = ("line", "bar", "scatter")

MAX_CHART_SERIES = 8
MAX_CHART_POINTS = 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024

CellValue = Union[str, int, float, bool, None]
Position = Union[float, str]


def _finite(value: Any, context: str) -> float:
    """Return ``value`` as a plain float, rejecting anything unplottable."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{context} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{context} must be finite")
    return number


class UIElement(ABC):
    """Base class for the elements a custom step can display."""

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Return the browser-safe element descriptor."""


class Text(UIElement):
    """Markdown paragraph.

    Args:
        content: Markdown source. Raw HTML is not rendered.
    """

    def __init__(self, content: str):
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Text content must be a non-empty string")
        self.content = content

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": "text", "content": self.content}


class Alert(UIElement):
    """Short highlighted message.

    Args:
        content: Plain text shown in the callout.
        level: One of ``info``, ``success``, ``warning``, or ``danger``.
    """

    def __init__(self, content: str, level: str = "info"):
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Alert content must be a non-empty string")
        if level not in ALERT_LEVELS:
            raise ValueError(f"Alert level must be one of {list(ALERT_LEVELS)!r}")
        self.content = content
        self.level = level

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": "alert", "content": self.content, "level": self.level}


@dataclass(frozen=True)
class Metric:
    """One labelled value in a :class:`Metrics` element."""

    label: str
    value: Union[str, int, float]
    unit: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("Metric label must not be empty")
        if isinstance(self.value, bool) or not isinstance(
            self.value, (str, int, float)
        ):
            raise ValueError(
                f"Metric '{self.label}' value must be a string or a number"
            )

    def to_dict(self) -> Dict[str, Any]:
        descriptor: Dict[str, Any] = {"label": self.label, "value": self.value}
        if self.unit is not None:
            descriptor["unit"] = self.unit
        return descriptor


class Metrics(UIElement):
    """Grid of labelled values such as scores, counts, or volumes.

    Values are displayed exactly as provided, so round or format them before
    passing them in.

    Args:
        items: Either a mapping of label to value, or a sequence of
            :class:`Metric` instances when units are needed.
    """

    def __init__(self, items: Union[Mapping[str, Any], Sequence[Metric]]):
        if isinstance(items, Mapping):
            self.items = [Metric(label, value) for label, value in items.items()]
        else:
            self.items = list(items)
            if any(not isinstance(item, Metric) for item in self.items):
                raise TypeError("Metrics items must be Metric instances or a mapping")
        if not self.items:
            raise ValueError("Metrics must contain at least one item")

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": "metrics", "items": [item.to_dict() for item in self.items]}


class Table(UIElement):
    """Small tabular result.

    Args:
        rows: Either mappings keyed by column name, or sequences of cells that
            match ``columns``.
        columns: Column headers. Required for sequence rows; derived from the
            first mapping row otherwise.
        caption: Optional description shown below the table.
    """

    def __init__(
        self,
        rows: Sequence[Union[Mapping[str, CellValue], Sequence[CellValue]]],
        columns: Optional[Sequence[str]] = None,
        caption: Optional[str] = None,
    ):
        rows = list(rows)
        if not rows:
            raise ValueError("Table must contain at least one row")
        mappings = [row for row in rows if isinstance(row, Mapping)]
        if mappings and len(mappings) != len(rows):
            raise TypeError("Table rows must be either all mappings or all sequences")
        if mappings:
            self.columns = list(columns) if columns else list(mappings[0].keys())
            self.rows = [
                [self._cell(row.get(column)) for column in self.columns]
                for row in mappings
            ]
        else:
            if not columns:
                raise ValueError("Table columns are required for sequence rows")
            self.columns = list(columns)
            self.rows = []
            for row in rows:
                if isinstance(row, (str, bytes)) or not isinstance(row, Sequence):
                    raise TypeError("Table rows must be mappings or sequences")
                cells = list(row)
                if len(cells) != len(self.columns):
                    raise ValueError(
                        f"Table row has {len(cells)} cells but {len(self.columns)} "
                        "columns are declared"
                    )
                self.rows.append([self._cell(cell) for cell in cells])
        if not self.columns:
            raise ValueError("Table must declare at least one column")
        self.caption = caption

    @staticmethod
    def _cell(value: Any) -> CellValue:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise ValueError(f"Table cells must be scalars or None, got {type(value)!r}")

    def to_dict(self) -> Dict[str, Any]:
        descriptor: Dict[str, Any] = {
            "kind": "table",
            "columns": self.columns,
            "rows": self.rows,
        }
        if self.caption is not None:
            descriptor["caption"] = self.caption
        return descriptor


@dataclass(frozen=True)
class Series:
    """One named sequence of values in a :class:`Chart`.

    Args:
        label: Name shown in the chart legend.
        values: Value of each point.
        x: Optional position or category name of each point. Positions must be
            either all numbers or all strings, and default to the point index.
    """

    label: str
    values: Sequence[float]
    x: Optional[Sequence[Position]] = None

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("Series label must not be empty")
        values = tuple(
            _finite(value, f"Series {self.label!r} value") for value in self.values
        )
        if not values:
            raise ValueError(f"Series {self.label!r} must contain at least one value")
        if len(values) > MAX_CHART_POINTS:
            raise ValueError(
                f"Series {self.label!r} must contain at most {MAX_CHART_POINTS} values"
            )
        object.__setattr__(self, "values", values)
        if self.x is None:
            return
        positions = tuple(self.x)
        if len(positions) != len(values):
            raise ValueError(
                f"Series {self.label!r} declares {len(positions)} positions for "
                f"{len(values)} values"
            )
        strings = [isinstance(position, str) for position in positions]
        if all(strings):
            object.__setattr__(self, "x", positions)
            return
        if any(strings):
            raise ValueError(
                f"Series {self.label!r} positions must be either all numbers or "
                "all strings"
            )
        object.__setattr__(
            self,
            "x",
            tuple(
                _finite(position, f"Series {self.label!r} position")
                for position in positions
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        descriptor: Dict[str, Any] = {"label": self.label, "values": list(self.values)}
        if self.x is not None:
            descriptor["x"] = list(self.x)
        return descriptor


class Chart(UIElement):
    """Plot of one or more numeric series, drawn to the width of the panel.

    Charts summarize a result; they are not a substitute for the viewer. Use
    string positions for categories such as label names, and numeric positions
    for measured quantities such as histogram bins.

    Args:
        variant: One of ``line``, ``bar``, or ``scatter``.
        series: A single :class:`Series`, several of them, or a mapping of label
            to values.
        x_label: Optional name of the horizontal axis.
        y_label: Optional name of the vertical axis.
        caption: Optional description shown below the chart.
    """

    def __init__(
        self,
        variant: str,
        series: Union[Series, Sequence[Series], Mapping[str, Sequence[float]]],
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        caption: Optional[str] = None,
    ):
        if variant not in CHART_VARIANTS:
            raise ValueError(f"Chart variant must be one of {list(CHART_VARIANTS)!r}")
        if isinstance(series, Series):
            self.series = [series]
        elif isinstance(series, Mapping):
            self.series = [Series(label, values) for label, values in series.items()]
        else:
            self.series = list(series)
            if any(not isinstance(item, Series) for item in self.series):
                raise TypeError("Chart series must be Series instances or a mapping")
        if not self.series:
            raise ValueError("Chart must contain at least one series")
        if len(self.series) > MAX_CHART_SERIES:
            raise ValueError(f"Chart must contain at most {MAX_CHART_SERIES} series")
        labels = [item.label for item in self.series]
        if len(set(labels)) != len(labels):
            raise ValueError("Chart series labels must be unique")
        self.variant = variant
        self.x_label = x_label
        self.y_label = y_label
        self.caption = caption

    def to_dict(self) -> Dict[str, Any]:
        descriptor: Dict[str, Any] = {
            "kind": "chart",
            "variant": self.variant,
            "series": [item.to_dict() for item in self.series],
        }
        optional_values = {
            "x_label": self.x_label,
            "y_label": self.y_label,
            "caption": self.caption,
        }
        descriptor.update(
            {key: value for key, value in optional_values.items() if value is not None}
        )
        return descriptor


class Image(UIElement):
    """Raster image such as a rendered plot or an external screenshot.

    The encoded image is part of every workflow state update, so keep it small.
    Images belong to a step's description of its result; data that has a
    position in space belongs in the session data model instead, where the
    viewer can display it.

    Args:
        source: PNG, JPEG, or WebP data, or the path of such a file.
        caption: Optional description shown below the image.
        alt: Alternative text for assistive technologies. Defaults to the
            caption.
    """

    def __init__(
        self,
        source: Union[bytes, bytearray, memoryview, str, Path],
        caption: Optional[str] = None,
        alt: Optional[str] = None,
    ):
        content = (
            bytes(source)
            if isinstance(source, (bytes, bytearray, memoryview))
            else Path(source).read_bytes()
        )
        if len(content) > MAX_IMAGE_BYTES:
            raise ValueError(
                f"Image must be at most {MAX_IMAGE_BYTES // 1024} KiB because it is "
                "resent with every workflow state update"
            )
        self.media_type = self._media_type(content)
        self.caption = caption
        self.alt = alt
        # Encoding here keeps every later state update cheap.
        self._encoded = base64.b64encode(content).decode("ascii")

    @staticmethod
    def _media_type(content: bytes) -> str:
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if content.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            return "image/webp"
        raise ValueError("Image source must be PNG, JPEG, or WebP data")

    def to_dict(self) -> Dict[str, Any]:
        descriptor: Dict[str, Any] = {
            "kind": "image",
            "media_type": self.media_type,
            "data": self._encoded,
        }
        optional_values = {"caption": self.caption, "alt": self.alt}
        descriptor.update(
            {key: value for key, value in optional_values.items() if value is not None}
        )
        return descriptor


class Fields(UIElement):
    """Editable values using the same typed parameters as actions.

    Values are validated by the server and are available as ``step.values``,
    keyed by parameter name.

    Args:
        parameters: Parameter descriptors such as
            :class:`~imfusion_webappkit.parameter_spec.FloatParameter`.
        submit_action: Action to dispatch, as if a :class:`Button` with this
            action had been pressed, when the visitor presses Enter in a
            single-line field. Lets a composer such as a chat message submit
            without a separate button.
    """

    def __init__(
        self,
        parameters: Sequence[ParameterDefinition],
        *,
        submit_action: Optional[str] = None,
    ):
        self.parameters: List[ParameterSpec] = normalize_parameter_specs(parameters)
        if not self.parameters:
            raise ValueError("Fields must declare at least one parameter")
        if submit_action is not None and not submit_action.isidentifier():
            raise ValueError(f"Invalid fields submit_action: {submit_action!r}")
        self.submit_action = submit_action

    def to_dict(self) -> Dict[str, Any]:
        descriptor: Dict[str, Any] = {
            "kind": "fields",
            "parameters": [spec.to_dict() for spec in self.parameters],
        }
        if self.submit_action is not None:
            descriptor["submit_action"] = self.submit_action
        return descriptor


class AnnotationField(UIElement):
    """Live state of annotations the step is collecting, with its own controls.

    For steps that mix annotation placement with other input — measure a
    distance in a field, then place a box using it — where
    :class:`~imfusion_webappkit.workflow.AnnotationStep` does not apply. The
    step drives ``app.annotation_model`` from ``on_action`` and this element
    shows the result.

    Args:
        annotations: The annotations to display, in the order the user places
            them. Usually ``step.my_annotations``.
        label: Optional heading above the list.
        place_action: Action dispatched by the Place button; omit for a
            read-only readout.
        clear_action: Action dispatched by the Clear button.
        prompts: Optional per-annotation prompt, shown instead of the
            annotation's own label.
        show_measurements: Show a line's length and an angle's angle.
    """

    def __init__(
        self,
        annotations: Sequence[Any],
        *,
        label: Optional[str] = None,
        place_action: Optional[str] = None,
        clear_action: Optional[str] = None,
        prompts: Optional[Sequence[str]] = None,
        show_measurements: bool = False,
    ):
        for action in (place_action, clear_action):
            if action is not None and not action.isidentifier():
                raise ValueError(f"Invalid annotation field action: {action!r}")
        self.annotations = list(annotations)
        self.label = label
        self.place_action = place_action
        self.clear_action = clear_action
        self.prompts = list(prompts) if prompts is not None else []
        if self.prompts and len(self.prompts) != len(self.annotations):
            raise ValueError("prompts must have one entry per annotation")
        self.show_measurements = bool(show_measurements)

    def to_dict(self) -> Dict[str, Any]:
        descriptor: Dict[str, Any] = {
            "kind": "annotation",
            "show_measurements": self.show_measurements,
            "annotations": [
                {
                    **annotation._descriptor(),
                    "prompt": self.prompts[index] if self.prompts else "",
                }
                for index, annotation in enumerate(self.annotations)
            ],
        }
        optional_values = {
            "label": self.label,
            "place_action": self.place_action,
            "clear_action": self.clear_action,
        }
        descriptor.update(
            {key: value for key, value in optional_values.items() if value is not None}
        )
        return descriptor


class Button(UIElement):
    """Button that calls the step's ``on_action`` hook.

    Args:
        action: Identifier passed to ``on_action``.
        label: Button text. Defaults to a title-cased ``action``.
        style: One of ``default``, ``primary``, or ``danger``.
        job: Run the handler as a correlated job so it reports progress and can
            be cancelled. Required for handlers that do more than update step
            state, because other work stays blocked while they run.
        disabled: Show the button but reject presses, in the browser and on the
            server.
    """

    def __init__(
        self,
        action: str,
        label: Optional[str] = None,
        *,
        style: str = "default",
        job: bool = False,
        disabled: bool = False,
    ):
        if not action or not action.isidentifier():
            raise ValueError(f"Invalid button action: {action!r}")
        if style not in BUTTON_STYLES:
            raise ValueError(f"Button style must be one of {list(BUTTON_STYLES)!r}")
        self.action = action
        self.label = label or action.replace("_", " ").title()
        self.style = style
        self.job = bool(job)
        self.disabled = bool(disabled)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "button",
            "action": self.action,
            "label": self.label,
            "style": self.style,
            "job": self.job,
            "disabled": self.disabled,
        }
