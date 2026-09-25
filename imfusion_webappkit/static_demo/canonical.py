"""Canonical keys for the client messages that drive a recorded demo.

The recorded graph is keyed by the message that caused each transition, so the
key the browser computes while replaying has to match the one written here
character for character. Both sides apply the same two rules: reduce the
payload to the part the server actually reads, then serialize it the way
``JSON.stringify`` would with sorted keys. ``static/src/static-demo/canonical.ts``
is the mirror of this module, and ``tests/test_static_demo_canonical.py`` checks
the two implementations against a shared table of awkward values.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from typing import Any, Dict, Iterable, Optional, Set

# Messages that mutate server state and therefore become graph edges. Anything
# else the client sends is either bookkeeping the server only mirrors
# (`selection_changed`, `data_removed`) or unsupported in a static demo.
RECORDABLE_MESSAGE_TYPES = frozenset(
    {
        "execute_action",
        "workflow_next",
        "workflow_back",
        "workflow_run",
        "workflow_step_data",
        "annotation_event",
        "annotation_created",
    }
)


def _plain(value: Any) -> Any:
    """Reduce a value to what JavaScript would hold after parsing its JSON."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("Demo message values must be finite numbers")
        # JavaScript has a single number type, so an integral float and the
        # matching integer must produce the same key.
        return int(value) if value.is_integer() else value
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Serialize a value the way ``JSON.stringify`` would, with sorted keys."""
    return json.dumps(
        _plain(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def normalize_message(
    message_type: str,
    data: Optional[Mapping[str, Any]],
    app_only_actions: Iterable[str] = (),
) -> Dict[str, Any]:
    """Return the part of a client message that determines the server's reply.

    The browser sends fields the server ignores, and it sends the same request
    in more than one shape. Both would otherwise produce keys that miss the
    recorded edge.
    """
    payload = dict(data or {})

    if message_type == "execute_action":
        normalized: Dict[str, Any] = {"action": payload.get("action")}
        if payload.get("action") not in set(app_only_actions):
            references = payload.get("inputs")
            if not isinstance(references, Sequence) or isinstance(references, str):
                # `executeAction` falls back to the current viewer selection when
                # the caller passes no explicit roles.
                references = [
                    {"role": str(position), "index": index}
                    for position, index in enumerate(payload.get("indices") or ())
                ]
            normalized["inputs"] = sorted(
                (
                    {
                        "role": str(reference.get("role")),
                        "index": reference.get("index"),
                    }
                    for reference in references
                    if isinstance(reference, Mapping)
                ),
                key=lambda reference: reference["role"],
            )
        # An app-only action ignores inputs entirely, and the selection the
        # browser would attach changes with every click.
        parameters = payload.get("parameters")
        if parameters:
            normalized["parameters"] = dict(parameters)
        return normalized

    if message_type == "workflow_run":
        action = payload.get("action")
        return {"action": action} if action is not None else {}

    if message_type == "workflow_step_data":
        return {"data": dict(payload.get("data") or {})}

    if message_type == "annotation_event":
        # The id and the points are deliberately dropped. Ids are fresh uuids on
        # every run, and a replaying visitor drags somewhere slightly different
        # from whoever recorded the demo, so keying on either would make every
        # annotation interaction miss its edge and dead-end the demo. Without
        # them the demo replays the recorded outcome for any placement, which is
        # the honest behaviour for something canned.
        return {"event": payload.get("event")}

    if message_type == "annotation_created":
        return {"type": payload.get("type")}

    if message_type in {"workflow_next", "workflow_back"}:
        return {}

    raise ValueError(f"Message type cannot be recorded: {message_type!r}")


def edge_key(
    message_type: str,
    data: Optional[Mapping[str, Any]] = None,
    app_only_actions: Iterable[str] = (),
) -> str:
    """Return the graph key for one client message."""
    return canonical_json(
        {
            "type": message_type,
            "data": normalize_message(message_type, data, app_only_actions),
        }
    )


def app_only_action_names(descriptors: Iterable[Mapping[str, Any]]) -> Set[str]:
    """Collect the actions that take no data input, for message normalization."""
    return {
        str(descriptor["name"])
        for descriptor in descriptors
        if descriptor.get("is_app_only")
    }
