"""Explore an application's reachable states and record what it sends.

Everything the browser can observe is the datasets it holds, which of them are
visible, and the workflow state, and every change to those is caused by one
client message. The application is therefore a state machine over messages, and
a demo is a recording of that machine: nodes are states the browser can be in,
edges are the messages that move between them together with the frames the
server answered.

Recording a graph rather than a linear transcript is what lets a visitor click
in their own order, go back, and repeat an action, instead of following the path
whoever built the demo happened to take.
"""

from __future__ import annotations

from collections import deque
import copy
from dataclasses import dataclass, field
import hashlib
import itertools
import logging
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

from .canonical import (
    RECORDABLE_MESSAGE_TYPES,
    app_only_action_names,
    canonical_json,
    edge_key,
)
from .recording import Frame, SessionState, payload_content_hash, run_path
from .spec import StaticDemoSpec

logger = logging.getLogger(__name__)

# A single step whose values multiply out beyond this is a mistake in the
# scenario rather than something worth spending an hour of build time on.
MAX_COMBINATIONS_PER_STEP = 64


class UnsupportedDemoInteraction(RuntimeError):
    """Raised for an interaction that cannot be precomputed."""


class DemoLimitExceeded(RuntimeError):
    """Raised when a recording grows past the spec's limits."""


@dataclass(frozen=True)
class RecordedFrame:
    """One server message, with any binary payload replaced by its hash."""

    type: str
    data: Dict[str, Any]
    payload: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        frame: Dict[str, Any] = {"type": self.type, "data": self.data}
        if self.payload is not None:
            frame["payload"] = self.payload
        return frame


@dataclass(frozen=True)
class RecordedEdge:
    """One client message and the reply it produced."""

    message: Dict[str, Any]
    frames: List[RecordedFrame]
    target: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "frames": [frame.to_dict() for frame in self.frames],
            "target": self.target,
        }


@dataclass
class RecordedNode:
    """One state the browser can be in, and the ways out of it."""

    id: str
    # What the browser was showing when this state was recorded. Replay compares
    # its own selection against it, so the recorder's model of the client cannot
    # drift out of agreement unnoticed.
    selection: List[int] = field(default_factory=list)
    edges: Dict[str, RecordedEdge] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "selection": self.selection,
            "edges": {key: edge.to_dict() for key, edge in self.edges.items()},
        }


@dataclass
class RecordedGraph:
    """A complete recording, ready to be written out."""

    config: Dict[str, Any]
    actions: List[Dict[str, Any]]
    handlers: Dict[str, str]
    initial_node: str
    connect_frames: List[RecordedFrame]
    nodes: Dict[str, RecordedNode]
    payloads: Dict[str, bytes]
    warnings: List[str] = field(default_factory=list)

    @property
    def total_payload_bytes(self) -> int:
        return sum(len(payload) for payload in self.payloads.values())


def _message(
    message_type: str, data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    return {"type": message_type, "data": data or {}}


def _combinations(
    choices: Sequence[Tuple[str, Sequence[Any]]],
    label: str,
) -> Iterator[Dict[str, Any]]:
    """Yield every assignment of the given values, refusing to explode."""
    if not choices:
        yield {}
        return
    total = 1
    for _, values in choices:
        total *= max(1, len(values))
    if total > MAX_COMBINATIONS_PER_STEP:
        raise DemoLimitExceeded(
            f"{label} would need {total} recorded combinations. Record fewer "
            f"values per parameter, or give the action a client-side handler."
        )
    names = [name for name, _ in choices]
    for combination in itertools.product(*(values for _, values in choices)):
        yield dict(zip(names, combination))


def _action_candidates(
    spec: StaticDemoSpec,
    descriptors: Sequence[Dict[str, Any]],
    state: SessionState,
    path: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Enumerate the action invocations worth recording from this state."""
    included = (
        set(spec.include_actions)
        if spec.include_actions is not None
        else {str(descriptor["name"]) for descriptor in descriptors}
    )
    candidates: List[Dict[str, Any]] = []
    dataset_count = len(state.names)

    for descriptor in descriptors:
        name = str(descriptor["name"])
        scenario = spec.scenario_for(name)
        if name not in included or scenario.handler is not None:
            # A handler-backed action recomputes in the browser, so recording it
            # would only fix its parameters to the values chosen here.
            continue
        already = sum(
            1
            for message in path
            if message["type"] == "execute_action"
            and message["data"].get("action") == name
        )
        if already >= scenario.repeat:
            continue

        parameters = descriptor.get("parameters") or {}
        choices = [
            (
                parameter_name,
                spec.parameter_values(
                    name,
                    parameter_name,
                    parameter.get("default", parameter.get("value")),
                ),
            )
            for parameter_name, parameter in parameters.items()
        ]
        assignments = list(_combinations(choices, f"Action {name!r}"))

        if descriptor.get("is_app_only"):
            input_sets: List[Optional[List[Dict[str, int]]]] = [None]
        elif scenario.inputs is not None:
            input_sets = [
                [
                    {"role": role, "index": index}
                    for role, index in sorted(mapping.items())
                ]
                for mapping in scenario.inputs
            ]
        else:
            specs = descriptor.get("inputs") or []
            required = [item for item in specs if item.get("required")]
            if len(required) == 1:
                input_sets = [
                    [{"role": required[0]["key"], "index": index}]
                    for index in range(dataset_count)
                ]
            else:
                # Every required role needs a different dataset, so the only
                # assignment that always exists is role order over the model.
                input_sets = (
                    [
                        [
                            {"role": item["key"], "index": index}
                            for index, item in enumerate(required)
                        ]
                    ]
                    if dataset_count >= len(required)
                    else []
                )

        for references in input_sets:
            for assignment in assignments:
                data: Dict[str, Any] = {"action": name}
                if references is not None:
                    data["inputs"] = references
                if assignment:
                    data["parameters"] = assignment
                candidates.append(_message("execute_action", data))
    return candidates


def _workflow_candidates(
    spec: StaticDemoSpec, state: SessionState
) -> List[Dict[str, Any]]:
    """Enumerate the workflow interactions worth recording from this state."""
    workflow = state.workflow
    if workflow is None or not workflow.get("current_step"):
        return []

    step = workflow["current_step"]
    config = step.get("ui_config") or {}
    kind = config.get("type")
    candidates: List[Dict[str, Any]] = []

    if kind == "brush":
        raise UnsupportedDemoInteraction(
            f"Workflow step {step['id']!r} is a brush step. Freehand strokes are "
            "unbounded input, so their result cannot be recorded in advance. "
            "Remove the step from the application used for the demo."
        )

    if kind == "annotation":
        raise UnsupportedDemoInteraction(
            f"Workflow step {step['id']!r} is an annotation step. Where the "
            "visitor drags is unbounded input, so the geometry it produces "
            "cannot be recorded in advance. Remove the step from the "
            "application used for the demo."
        )

    overrides = spec.workflow.step_data.get(step["id"])
    if overrides is not None:
        candidates += [
            _message("workflow_step_data", {"data": dict(payload)})
            for payload in overrides
        ]
    elif kind == "parameters":
        choices = [
            (
                parameter["name"],
                spec.step_parameter_values(
                    parameter["name"], parameter.get("value", parameter.get("default"))
                ),
            )
            for parameter in config.get("parameters") or []
        ]
        for assignment in _combinations(choices, f"Workflow step {step['id']!r}"):
            if assignment:
                candidates.append(
                    _message("workflow_step_data", {"data": {"parameters": assignment}})
                )
    elif kind == "validation":
        candidates += [
            _message("workflow_step_data", {"data": {"accepted": True}}),
            _message("workflow_step_data", {"data": {"accepted": False}}),
        ]
    elif kind == "export":
        candidates.append(_message("workflow_step_data", {"data": {"exported": True}}))
    elif kind == "data_selection":
        roles = [item["key"] for item in config.get("inputs") or []]
        datasets = [item["index"] for item in config.get("datasets") or []]
        if len(datasets) >= len(roles) and roles:
            candidates.append(
                _message(
                    "workflow_step_data",
                    {"data": {"inputs": dict(zip(roles, datasets))}},
                )
            )
    elif kind == "custom":
        for element in config.get("body") or []:
            if element.get("kind") == "button" and not element.get("disabled"):
                candidates.append(
                    _message("workflow_run", {"action": element["action"]})
                )

    if kind == "processing" and config.get("auto_run") is False:
        if not config.get("completed"):
            candidates.append(_message("workflow_run"))

    # The browser disables these buttons unless the state allows them, so a
    # recording of the refusal would never be replayed.
    if workflow.get("can_proceed"):
        candidates.append(_message("workflow_next"))
    # Rejecting a ValidationStep disables **Next** on purpose: the live app
    # tells the visitor to go back. That Back has to be recorded even when the
    # scenario otherwise skips it, or both nav buttons grey out and the only
    # remaining move is to click Accept after all.
    rejected = kind == "validation" and config.get("accepted") is False
    if workflow.get("can_go_back") and (spec.workflow.include_back or rejected):
        candidates.append(_message("workflow_back"))
    return candidates


def _nearest(value: Any, allowed: Sequence[Any]) -> Any:
    """The recorded value closest to `value`, mirroring the browser's snapping."""
    if not allowed or value in allowed:
        return value
    numbers = [
        candidate
        for candidate in allowed
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool)
    ]
    if isinstance(value, (int, float)) and not isinstance(value, bool) and numbers:
        return min(numbers, key=lambda candidate: abs(candidate - value))
    return allowed[0]


def _restrict(parameter: Dict[str, Any], allowed: Sequence[Any]) -> None:
    """Advertise the recorded values, and open on one of them.

    A control that starts at a value nobody recorded would send it the moment the
    visitor presses the button without touching anything, which is the one path
    into the notice that no amount of care in the interface can prevent.
    """
    parameter["allowed_values"] = list(allowed)
    for key in ("value", "default"):
        if key in parameter:
            parameter[key] = _nearest(parameter[key], allowed)


def _annotate_workflow_state(
    spec: StaticDemoSpec, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Add the recorded values to a workflow state's parameter descriptors.

    Action descriptors get the same treatment in :func:`inspect_app`, but a
    step's parameters only exist inside the frames that announce it, so they can
    only be annotated as those frames are recorded. Navigation flags are aligned
    later, once the graph knows which **Next** and **Back** edges actually exist.
    """
    step = data.get("current_step") or {}
    config = step.get("ui_config") or {}
    if not config.get("parameters"):
        return data
    if spec.workflow.step_data.get(step.get("id")) is not None:
        # The author scripted the payloads for this step, so the values the
        # browser may send are not a grid over its parameters.
        return data
    annotated = copy.deepcopy(data)
    for parameter in annotated["current_step"]["ui_config"]["parameters"]:
        _restrict(
            parameter,
            spec.step_parameter_values(
                parameter["name"], parameter.get("value", parameter.get("default"))
            ),
        )
    return annotated


def _workflow_payload(frame: RecordedFrame) -> Optional[Dict[str, Any]]:
    """Return the workflow state a frame carries, if it carries one."""
    if frame.type == "workflow_state":
        return frame.data
    if frame.type == "job_result":
        workflow = (frame.data.get("result") or {}).get("workflow")
        if isinstance(workflow, dict):
            return workflow
    return None


def _align_workflow_navigation(graph: RecordedGraph) -> None:
    """Offer **Next** and **Back** only where the recording can answer them.

    The application's own flags describe a live session. A recording may have
    skipped **Back**, or stopped exploring before **Finish**, and leaving the
    live flags in place greys out a button that has an edge or lights one that
    leads to the notice. The frames on an edge describe the state they land in,
    so the flags follow that node's outgoing edges.
    """
    next_key = edge_key("workflow_next")
    back_key = edge_key("workflow_back")

    def apply(frames: List[RecordedFrame], node: RecordedNode) -> None:
        can_proceed = next_key in node.edges
        can_go_back = back_key in node.edges
        for frame in frames:
            data = _workflow_payload(frame)
            if data is None:
                continue
            data["can_proceed"] = can_proceed
            data["can_go_back"] = can_go_back

    apply(graph.connect_frames, graph.nodes[graph.initial_node])
    for node in graph.nodes.values():
        for edge in node.edges.values():
            apply(edge.frames, graph.nodes[edge.target])


@dataclass
class _Task:
    """A path to replay, and where to attach the edge it produces."""

    path: List[Dict[str, Any]]
    parent: Optional[str] = None
    message: Optional[Dict[str, Any]] = None


def record(
    spec: StaticDemoSpec,
    metadata: "AppMetadata",
    *,
    progress: Optional[Callable[[str], None]] = None,
) -> RecordedGraph:
    """Explore the application described by `spec` and return its graph."""
    report = progress or (lambda message: logger.info("%s", message))
    config = metadata.config
    descriptors = metadata.actions
    app_only = app_only_action_names(descriptors)
    handlers = {
        name: scenario.handler
        for name, scenario in spec.actions.items()
        if scenario.handler is not None
    }

    nodes: Dict[str, RecordedNode] = {}
    ids_by_fingerprint: Dict[str, str] = {}
    payloads: Dict[str, bytes] = {}
    warnings: List[str] = []
    connect_frames: List[RecordedFrame] = []
    initial_node = ""

    # Looking inside a payload costs a deserialization, so identical bytes are
    # only inspected once. Bytes differ between paths even for the same dataset,
    # which is why the store is keyed on content rather than on bytes.
    content_by_bytes: Dict[str, str] = {}

    def store(frames: Sequence[Frame]) -> List[RecordedFrame]:
        recorded = []
        for frame in frames:
            digest = None
            if frame.payload is not None:
                raw = hashlib.sha256(frame.payload).hexdigest()
                digest = content_by_bytes.get(raw)
                if digest is None:
                    digest = payload_content_hash(frame.payload)
                    content_by_bytes[raw] = digest
                payloads.setdefault(digest, frame.payload)
            data = frame.data
            if frame.type == "workflow_state":
                data = _annotate_workflow_state(spec, data)
            recorded.append(RecordedFrame(frame.type, data, digest))
        return recorded

    pending: deque[_Task] = deque([_Task(path=[])])
    expanded: set[str] = set()
    replays = 0
    started_with_data = False

    while pending:
        task = pending.popleft()
        replays += 1
        outcome = run_path(spec.app, task.path)
        state = outcome.state
        assert state is not None  # run_path guarantees it
        fingerprint = state.fingerprint
        emptied = bool(
            task.parent is not None and started_with_data and not state.names
        )

        # Finishing a workflow clears the session. A recording cannot load data
        # again, so publishing that empty Welcome screen greys out both buttons.
        # Restarting at the initial state is the demo equivalent of a reload.
        if emptied:
            node_id = initial_node
        else:
            node_id = ids_by_fingerprint.get(fingerprint)
            if node_id is None:
                if len(nodes) >= spec.limits.max_nodes:
                    raise DemoLimitExceeded(
                        f"Recording reached {spec.limits.max_nodes} states. Narrow the "
                        "scenario or raise DemoLimits.max_nodes."
                    )
                node_id = f"n{len(nodes)}"
                ids_by_fingerprint[fingerprint] = node_id
                nodes[node_id] = RecordedNode(node_id, selection=list(state.selection))

        if task.parent is None:
            initial_node = node_id
            started_with_data = bool(state.names)
            connect_frames = store(outcome.last_frames)
            report(f"initial state {node_id}: {', '.join(state.names) or 'no data'}")
        else:
            key = edge_key(
                task.message["type"], task.message["data"], app_only_actions=app_only
            )
            frames = store(outcome.last_frames)
            if emptied:
                frames = [*frames, *connect_frames]
            nodes[task.parent].edges[key] = RecordedEdge(
                message=task.message,
                frames=frames,
                target=node_id,
            )
            report(f"{task.parent} -> {node_id}: {_describe(task.message)}")

        total = sum(len(payload) for payload in payloads.values())
        if total > spec.limits.max_bytes:
            raise DemoLimitExceeded(
                f"Recorded payloads reached {total / 1024 / 1024:.0f} MB, over the "
                f"{spec.limits.max_bytes / 1024 / 1024:.0f} MB limit. Record fewer "
                "values, use smaller datasets, or raise DemoLimits.max_bytes."
            )

        if emptied:
            continue
        if fingerprint in expanded or len(task.path) >= spec.limits.max_depth:
            continue
        expanded.add(fingerprint)

        candidates = _action_candidates(spec, descriptors, state, task.path)
        candidates += _workflow_candidates(spec, state)
        for candidate in candidates:
            if candidate["type"] not in RECORDABLE_MESSAGE_TYPES:
                raise UnsupportedDemoInteraction(
                    f"Cannot record message type {candidate['type']!r}"
                )
            pending.append(
                _Task(
                    path=[*task.path, candidate],
                    parent=node_id,
                    message=candidate,
                )
            )

    warnings += _review(config, nodes, handlers)
    report(f"recorded {len(nodes)} state(s) from {replays} replay(s)")
    graph = RecordedGraph(
        config=config,
        actions=descriptors,
        handlers=handlers,
        initial_node=initial_node,
        connect_frames=connect_frames,
        nodes=nodes,
        payloads=payloads,
        warnings=warnings,
    )
    _align_workflow_navigation(graph)
    return graph


@dataclass(frozen=True)
class AppMetadata:
    """The application's own description of itself, read once before recording."""

    config: Dict[str, Any]
    actions: List[Dict[str, Any]]
    branding: Dict[str, Optional[str]]
    sample_datasets: List[Dict[str, Optional[str]]]


def inspect_app(spec: StaticDemoSpec) -> AppMetadata:
    """Read the configuration and actions from a throwaway application.

    The `/config` response is taken from the registered route rather than
    rebuilt, so the fixture cannot drift from what a live server would send.
    ``allowed_values`` is added to each parameter because that is what makes
    snapping possible: a control offering a value nobody recorded would reach a
    dead end the visitor cannot explain.
    """
    import asyncio

    app = spec.app()
    try:
        endpoint = next(
            route.endpoint
            for route in app._fastapi_app.routes  # noqa: SLF001
            if getattr(route, "path", None) == "/config"
        )
        config = asyncio.run(endpoint())
        descriptors = app.action_registry.list_action_descriptors()
        branding = {
            "logo": str(app.branding.logo) if app.branding.logo else None,
            "favicon": str(app.branding.favicon) if app.branding.favicon else None,
        }
        samples = [
            {
                "name": dataset.name,
                "path": str(dataset.path),
                "thumbnail": str(dataset.thumbnail) if dataset.thumbnail else None,
            }
            for dataset in app._sample_datasets  # noqa: SLF001
        ]
    finally:
        app.sdk_runtime.stop()

    for descriptor in descriptors:
        name = str(descriptor["name"])
        scenario = spec.scenario_for(name)
        if scenario.handler is not None:
            descriptor["handler"] = scenario.handler
            continue
        for parameter_name, parameter in (descriptor.get("parameters") or {}).items():
            _restrict(
                parameter,
                spec.parameter_values(
                    name,
                    parameter_name,
                    parameter.get("default", parameter.get("value")),
                ),
            )
    return AppMetadata(config, descriptors, branding, samples)


def _review(
    config: Dict[str, Any],
    nodes: Dict[str, RecordedNode],
    handlers: Dict[str, str],
) -> List[str]:
    """Report the ways a recording can mislead whoever publishes it."""
    notes: List[str] = []
    for node in nodes.values():
        for edge in node.edges.values():
            if any(frame.type == "job_failed" for frame in edge.frames):
                notes.append(
                    f"{_describe(edge.message)} failed while recording, and the "
                    f"failure is now part of the demo. Fix the application or "
                    f"narrow the scenario so this is not reachable."
                )
    if not handlers and not any(node.edges for node in nodes.values()):
        notes.append(
            "No interaction was recorded, so the demo is only a viewer. Check "
            "include_actions and the workflow scenario."
        )
    if config.get("show_export_button"):
        notes.append(
            "Export is enabled but needs Python to produce anything but IMF. Build "
            "the demo application with show_export_button=False."
        )
    if config.get("show_load_button"):
        notes.append(
            "The load button is enabled. A visitor can load their own data, but no "
            "recorded action will match it, so they reach the notice instead. "
            "Consider show_load_button=False."
        )
    if config.get("algorithms_enabled"):
        notes.append(
            "Algorithm discovery is enabled but is not recorded, so the panel stays "
            "empty."
        )
    if (config.get("sidebar") or {}).get("show_annotations"):
        notes.append(
            "The annotations panel is enabled. A visitor can draw, but the "
            "geometry is never the recorded geometry, so Python sees nothing and "
            "they reach the notice instead. Build the demo application with "
            "SidebarConfig(show_annotations=False)."
        )
    return notes


def _describe(message: Dict[str, Any]) -> str:
    """One-line summary of a client message, for build output."""
    data = message.get("data") or {}
    if message["type"] == "execute_action":
        parts = [str(data.get("action"))]
        if data.get("parameters"):
            parts.append(canonical_json(data["parameters"]))
        return " ".join(parts)
    if message["type"] == "workflow_step_data":
        return f"step data {canonical_json(data.get('data') or {})}"
    if message["type"] == "workflow_run" and data.get("action"):
        return f"run {data['action']}"
    return message["type"]
