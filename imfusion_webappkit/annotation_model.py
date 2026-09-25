"""Session-scoped annotations mirroring ``imfusion.app.annotation_model``.

The browser owns the geometry: only it has the ``GlAnnotation`` and the event
handler that turns clicks into points. This module keeps a shadow record per
session, pushes intent to the client, and applies whatever the client reports
back. An incoming event always wins over a value set from Python.
"""

from __future__ import annotations

import inspect
import logging
import math
import uuid
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .app import ImFusionWebApp
    from .session import Session

logger = logging.getLogger(__name__)

Point = Tuple[float, float, float]


class AnnotationType(str, Enum):
    """Annotation shapes the browser can place.

    Values are the Web SDK's own literals and are passed through to
    ``annotationModel.add()`` unchanged, so supporting a new shape is an entry
    here and nothing else. The Python SDK also defines ``CIRCLE`` and
    ``POLY_LINE``, which the Web SDK does not bind yet; see
    ``docs/guides/annotations.md``.
    """

    LINE = "LineSegment"
    RECTANGLE = "Rectangle"
    ANGLE = "Angle"
    # TODO: confirm these two literals against the Web SDK's AnnotationBindings.cpp
    # once the bindings land; they are inferred from the GlLine/GlRectangle/GlAngle
    # naming pattern. A wrong guess surfaces as an `unsupported` annotation error
    # rather than a broken client, because the client validates the string first.
    POINT = "Point"
    BOX = "Box"


def _normalize_color(color: Sequence[float]) -> List[float]:
    """Return ``color`` as RGBA, which is the form the Web SDK's state uses."""
    values = [float(component) for component in color]
    if len(values) == 3:
        values.append(1.0)
    if len(values) != 4:
        raise ValueError("Color must have three (RGB) or four (RGBA) components")
    if any(not 0.0 <= component <= 1.0 for component in values):
        raise ValueError("Color components must be between 0 and 1")
    return values


def _normalize_points(points: Sequence[Sequence[float]]) -> List[Point]:
    normalized: List[Point] = []
    for point in points:
        values = [float(component) for component in point]
        if len(values) != 3:
            raise ValueError("Each annotation point must have three components")
        normalized.append((values[0], values[1], values[2]))
    return normalized


def _invoke(callback: Callable, annotation: "Annotation") -> None:
    """Call a user callback, passing the annotation only if it asks for one.

    The Python SDK's ``on_editing_finished`` / ``on_points_changed`` callbacks
    take no arguments, so that stays the contract. Declaring an ``annotation``
    parameter opts into receiving it, detected the same way
    ``action_registry`` auto-detects action signatures.
    """
    try:
        parameters = inspect.signature(callback).parameters
    except (TypeError, ValueError):
        parameters = {}
    wants_annotation = "annotation" in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    try:
        if wants_annotation:
            callback(annotation=annotation)
        else:
            callback()
    except Exception:
        logger.error("Annotation callback failed", exc_info=True)


class Annotation:
    """One annotation, created through :meth:`WebAnnotationModel.create_annotation`.

    Points are world coordinates, matching the Web SDK. Use :meth:`points_in`
    to express them in a dataset's own frame, which is what you want whenever
    the value has to outlive a change to that dataset's transform.
    """

    #: Alias so ``Annotation.AnnotationType.LINE`` resolves as it does in the SDK.
    AnnotationType = AnnotationType

    def __init__(
        self,
        model: "WebAnnotationModel",
        annotation_type: AnnotationType,
        data: Any,
        annotation_id: Optional[str] = None,
    ):
        self._model = model
        self._id = annotation_id or str(uuid.uuid4())
        self._type = AnnotationType(annotation_type)
        self._data = data
        self._points: List[Point] = []
        self._color = _normalize_color((1.0, 1.0, 0.0))
        self._name = ""
        self._label = ""
        self._visible = True
        self._max_points: Optional[int] = None
        self._published = False
        self._armed = False
        self._complete = False
        self._error = ""
        self._editing_finished_callbacks: List[Callable] = []
        self._points_changed_callbacks: List[Callable] = []

    # ----- identity and parent -----

    @property
    def id(self) -> str:
        return self._id

    @property
    def type(self) -> AnnotationType:
        return self._type

    @property
    def data(self) -> Any:
        """The dataset this annotation belongs to."""
        return self._data

    # ----- geometry -----

    @property
    def points(self) -> List[Point]:
        """Control points in world coordinates."""
        return list(self._points)

    @points.setter
    def points(self, value: Sequence[Sequence[float]]) -> None:
        self._points = _normalize_points(value)
        self._model._push(self, points=self._points)

    def points_in(self, data: Any = None) -> List[Point]:
        """Return the points in ``data``'s own coordinate frame.

        Defaults to the annotation's parent dataset. World coordinates are only
        meaningful while the dataset's transform stays put, so anything that
        survives a registration or a reslice should be stored in this frame.
        """
        target = self._data if data is None else data
        matrix = getattr(target, "matrix", None)
        if matrix is None:
            raise TypeError(
                "points_in requires a dataset with a matrix, such as a SharedImageSet"
            )
        to_local = np.linalg.inv(np.asarray(matrix(), dtype=float))
        return [
            tuple(float(component) for component in (to_local @ (*point, 1.0))[:3])
            for point in self._points
        ]

    @property
    def max_points(self) -> Optional[int]:
        """Points this shape holds, as reported by the SDK.

        ``None`` until the browser has created the annotation, because the
        value is read from its state rather than hardcoded per type.
        """
        return self._max_points

    @property
    def length(self) -> Optional[float]:
        """Distance between the endpoints of a :attr:`AnnotationType.LINE`."""
        if self._type is not AnnotationType.LINE or len(self._points) != 2:
            return None
        start, end = (np.asarray(point) for point in self._points)
        return float(np.linalg.norm(end - start))

    @property
    def angle(self) -> Optional[float]:
        """Angle in degrees at the vertex of an :attr:`AnnotationType.ANGLE`.

        The middle control point is taken as the vertex.
        """
        if self._type is not AnnotationType.ANGLE or len(self._points) != 3:
            return None
        first, vertex, second = (np.asarray(point) for point in self._points)
        left = first - vertex
        right = second - vertex
        scale = np.linalg.norm(left) * np.linalg.norm(right)
        if not scale:
            return None
        cosine = float(np.dot(left, right) / scale)
        return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))

    # ----- appearance -----

    @property
    def color(self) -> Tuple[float, ...]:
        return tuple(self._color)

    @color.setter
    def color(self, value: Sequence[float]) -> None:
        self._color = _normalize_color(value)
        self._model._push(self, color=self._color)

    @property
    def name(self) -> str:
        """Identifier shown in lists; the SDK generates one when left empty."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = str(value)
        self._model._push(self, name=self._name)

    @property
    def label(self) -> str:
        """Text drawn next to the annotation in the viewer."""
        return self._label

    @label.setter
    def label(self, value: str) -> None:
        self._label = str(value)
        self._model._push(self, label=self._label)

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        self._visible = bool(value)
        self._model._push(self, visible=self._visible)

    # ----- placement -----

    @property
    def complete(self) -> bool:
        """True once the user has finished placing this annotation."""
        return self._complete

    @property
    def editing(self) -> bool:
        """True while the browser is waiting for the user to place points."""
        return self._armed

    @property
    def error(self) -> str:
        """Why placement failed, or an empty string.

        Set when the browser cannot create the shape — typically an annotation
        type its Web SDK build does not support. Populated asynchronously, so
        it is empty immediately after :meth:`start_editing`.
        """
        return self._error

    def start_editing(self) -> None:
        """Ask the browser to let the user place this annotation."""
        if self._complete:
            # The SDK drops a finished annotation into "regular mode" and binds
            # no way back into creation mode, so re-arming is impossible. Callers
            # that want another attempt must remove this one and create another.
            raise RuntimeError(
                "This annotation has already been placed; remove it and create "
                "a new one instead of re-arming it"
            )
        self._error = ""
        self._armed = True
        self._model._add_on_client(self, editing=True)

    def on_editing_finished(self, callback: Callable) -> None:
        """Register a callback for when the user finishes placing the annotation."""
        self._editing_finished_callbacks.append(callback)

    def on_points_changed(self, callback: Callable) -> None:
        """Register a callback for every change to the annotation's points."""
        had_listeners = bool(self._points_changed_callbacks)
        self._points_changed_callbacks.append(callback)
        if not had_listeners and self._published:
            # Registered after the annotation reached the browser, so ask it to
            # start streaming; the SDK docs only recommend registering first.
            self._model._push(self, notify_points_changed=True)

    def remove(self) -> None:
        """Remove this annotation from its model."""
        self._model.remove(self)

    def _descriptor(self) -> Dict[str, Any]:
        """Browser-safe summary, used by steps and UI elements."""
        return {
            "id": self._id,
            "type": self._type.value,
            "name": self._name,
            "label": self._label,
            "points": [list(point) for point in self._points],
            "max_points": self._max_points,
            "complete": self._complete,
            "editing": self._armed,
            "error": self._error,
            "length": self.length,
            "angle": self.angle,
        }

    def __repr__(self) -> str:
        return (
            f"Annotation(type={self._type.value!r}, points={len(self._points)}, "
            f"complete={self._complete})"
        )


class WebAnnotationModel:
    """Browser-session equivalent of ``imfusion.AnnotationModel``."""

    def __init__(self, host: "ImFusionWebApp", session: "Session"):
        self._host = host
        self._session = session
        self._annotations: List[Annotation] = []
        self._added_callbacks: List[Callable] = []

    # ===== imfusion.AnnotationModel API =====

    def create_annotation(
        self,
        annotation_type: AnnotationType,
        data: Any = None,
    ) -> Annotation:
        """Create an annotation belonging to ``data``.

        Nothing reaches the browser yet: the Web SDK's ``add()`` immediately
        arms interactive placement, so creation is deferred until
        :meth:`Annotation.start_editing` or until points are assigned.

        ``data`` defaults to the session's selection, because the Web SDK
        requires a parent dataset even though the Python SDK does not.
        """
        parent = data if data is not None else self._default_data()
        if not self._session.data_model.contains(parent):
            raise ValueError("An annotation's dataset must be in the data model")
        annotation = Annotation(self, annotation_type, parent)
        self._annotations.append(annotation)
        return annotation

    def annotations(self) -> List[Annotation]:
        """Every annotation in this session."""
        return list(self._annotations)

    def data_annotations(self, data: Any) -> List[Annotation]:
        """Annotations belonging to ``data``."""
        return [
            annotation for annotation in self._annotations if annotation.data is data
        ]

    def remove(self, annotation: Annotation) -> None:
        """Remove one annotation from the model and the browser."""
        if annotation not in self._annotations:
            return
        self._annotations.remove(annotation)
        if annotation._published:
            self._send("annotation_remove", {"id": annotation.id})

    def clear(self) -> None:
        """Remove every annotation."""
        for annotation in tuple(self._annotations):
            self.remove(annotation)

    def on_annotation_added(self, callback: Callable[[Annotation], None]) -> None:
        """Register a callback for annotations the user starts in the browser.

        Called with the new annotation, which has no points yet: the browser
        reports it as soon as the user picks a tool. Register
        :meth:`Annotation.on_editing_finished` on it to hear the geometry.

        Unlike the annotation's own callbacks, which mirror the Python SDK's
        no-argument signature, this one has no SDK counterpart and always
        passes the annotation — there is no other way to reach it.
        """
        self._added_callbacks.append(callback)

    # ===== internals =====

    def _default_data(self) -> Any:
        selected = self._session.controller.selected_data
        if len(selected) == 1:
            return selected[0]
        raise ValueError(
            "create_annotation needs a dataset unless exactly one is selected"
        )

    def _data_index(self, data: Any) -> int:
        return self._session.data_model.index(data)

    def _send(self, msg_type: str, payload: Dict[str, Any]) -> None:
        self._session.send_message(msg_type, payload)

    def _add_on_client(self, annotation: Annotation, *, editing: bool) -> None:
        """Create the annotation in the browser, optionally arming placement."""
        if not self._session.data_model.contains(annotation.data):
            raise ValueError("An annotation's dataset is no longer in the data model")
        annotation._published = True
        self._send(
            "annotation_add",
            {
                "id": annotation.id,
                "type": annotation.type.value,
                "data_index": self._data_index(annotation.data),
                "color": list(annotation._color),
                "name": annotation.name,
                "label": annotation.label,
                "visible": annotation.visible,
                "points": [list(point) for point in annotation.points],
                "editing": editing,
                "notify_points_changed": bool(annotation._points_changed_callbacks),
            },
        )

    def _push(self, annotation: Annotation, **fields: Any) -> None:
        """Send a property change, creating the annotation first if needed."""
        if annotation not in self._annotations:
            return
        if not annotation._published:
            if "points" not in fields:
                # Appearance set before the annotation exists in the browser
                # travels with the `annotation_add` that creates it.
                return
            # Assigning points is how an annotation gets displayed without the
            # user placing it, so it is what forces creation.
            self._add_on_client(annotation, editing=False)
            return
        payload: Dict[str, Any] = {"id": annotation.id}
        for key, value in fields.items():
            payload[key] = (
                [list(point) for point in value] if key == "points" else value
            )
        self._send("annotation_update", payload)

    def _find(self, annotation_id: Any) -> Optional[Annotation]:
        for annotation in self._annotations:
            if annotation.id == annotation_id:
                return annotation
        return None

    def _handle_event(self, payload: Dict[str, Any]) -> None:
        """Apply one ``annotation_event`` from the browser.

        An unknown id is ignored rather than raising: a removal from Python and
        an event already in flight legitimately cross on the wire.
        """
        annotation = self._find(payload.get("id"))
        if annotation is None:
            return

        max_points = payload.get("max_points")
        if isinstance(max_points, int) and max_points > 0:
            annotation._max_points = max_points

        event = payload.get("event")
        if "points" in payload and payload["points"] is not None:
            annotation._points = _normalize_points(payload["points"])

        if event == "points_changed":
            for callback in tuple(annotation._points_changed_callbacks):
                _invoke(callback, annotation)
        elif event == "editing_finished":
            annotation._armed = False
            annotation._complete = True
            for callback in tuple(annotation._points_changed_callbacks):
                _invoke(callback, annotation)
            for callback in tuple(annotation._editing_finished_callbacks):
                _invoke(callback, annotation)
        elif event == "editing_aborted":
            # Aborting clears the points and drops the SDK annotation into a
            # mode that cannot be re-armed, so it is dead: whoever owns it has
            # to replace it.
            annotation._armed = False
            annotation._complete = False
            annotation._points = []
        elif event == "removed":
            if annotation in self._annotations:
                self._annotations.remove(annotation)
        elif event == "unsupported":
            annotation._armed = False
            annotation._error = str(
                payload.get("message")
                or f"The browser's Web SDK cannot create a "
                f"{annotation.type.value} annotation"
            )
            logger.warning("Annotation placement failed: %s", annotation._error)

    def _handle_created(self, payload: Dict[str, Any]) -> None:
        """Register an annotation the user drew in the browser."""
        annotation_id = payload.get("id")
        if not isinstance(annotation_id, str) or self._find(annotation_id) is not None:
            return
        data_index = payload.get("data_index")
        if not isinstance(data_index, int) or not 0 <= data_index < len(
            self._session.data_model
        ):
            return
        annotation = Annotation(
            self,
            AnnotationType(payload["type"]),
            self._session.data_model[data_index],
            annotation_id=annotation_id,
        )
        annotation._published = True
        points = payload.get("points") or []
        if points:
            annotation._points = _normalize_points(points)
        # The browser arms creation as soon as the user picks a tool, so one
        # arriving without points is still being drawn rather than finished.
        annotation._complete = bool(points)
        annotation._armed = not points
        max_points = payload.get("max_points")
        if isinstance(max_points, int) and max_points > 0:
            annotation._max_points = max_points
        self._annotations.append(annotation)
        for callback in tuple(self._added_callbacks):
            try:
                callback(annotation)
            except Exception:
                logger.error("Annotation added callback failed", exc_info=True)

    def _remove_for_data(self, data: Any) -> None:
        """Drop annotations whose dataset is about to disappear.

        The Web SDK keys annotations by ``Data*``, so they have to go before
        the dataset does or it is left holding a dangling pointer.
        """
        for annotation in self.data_annotations(data):
            self.remove(annotation)

    def _dispose(self) -> None:
        self._annotations.clear()
        self._added_callbacks.clear()
