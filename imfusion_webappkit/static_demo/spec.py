"""Declarative description of the static demo to record from an application.

A static demo is the real client bundle answered by precomputed results instead
of a Python process, so the author's job is to say which interactions are worth
recording. Everything else is derived from the application itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import ImFusionWebApp

# Handlers that compute in the browser instead of replaying a recorded result.
# The implementations live in `static/src/static-demo/handlers.ts`; this copy
# only exists so a misspelled name fails while building rather than in the
# browser of whoever opens the published page.
AVAILABLE_HANDLERS = frozenset({"threshold"})

DEFAULT_NOTICE = (
    "This page is a recorded demo. The application normally talks to a Python "
    "process, and this one has no server behind it, so only the interactions "
    "captured while it was built can be replayed."
)


@dataclass(frozen=True)
class ActionScenario:
    """How one registered action is represented in the demo.

    Args:
        parameters: Values to record per parameter name. Every combination is
            recorded, and the browser snaps its controls to these values.
            Parameters left out are recorded at their default only.
        handler: Name of a client-side handler that recomputes the result in the
            browser through the WebAssembly SDK. Handler-backed actions are not
            precomputed and keep continuous parameters. See
            :data:`AVAILABLE_HANDLERS`.
        inputs: Explicit role-to-index assignments to record. Defaults to every
            single dataset for one-input actions, and to the first matching
            datasets in role order otherwise.
        repeat: How many times the action may be applied along one path. Raising
            it records results computed from earlier results, which multiplies
            both build time and published size.
    """

    parameters: Mapping[str, Sequence[Any]] = field(default_factory=dict)
    handler: Optional[str] = None
    inputs: Optional[Sequence[Mapping[str, int]]] = None
    repeat: int = 1

    def __post_init__(self) -> None:
        if self.handler is not None and self.handler not in AVAILABLE_HANDLERS:
            raise ValueError(
                f"Unknown client-side handler: {self.handler!r}. "
                f"Available handlers: {sorted(AVAILABLE_HANDLERS)}"
            )
        if self.repeat < 1:
            raise ValueError("repeat must be at least 1")


@dataclass(frozen=True)
class WorkflowScenario:
    """How the application's workflow is explored while recording.

    Args:
        step_data: Candidate ``workflow_step_data`` payloads per step id,
            replacing the defaults derived from the step type. Use it to record
            a specific set of parameter values or input assignments.
        include_back: Record the **Back** transition as well as **Next**. Going
            back resets the step being left and invalidates the steps that
            depend on it, so it is a real transition rather than a return to an
            earlier state.
    """

    step_data: Mapping[str, Sequence[Mapping[str, Any]]] = field(default_factory=dict)
    include_back: bool = True


@dataclass(frozen=True)
class DemoLimits:
    """Ceilings that stop a recording before it becomes unpublishable.

    Every recorded result is a complete dataset, so an unbounded exploration
    produces hundreds of megabytes long before it produces anything useful.

    Args:
        max_nodes: Distinct application states to record.
        max_depth: Interactions to follow from the initial state.
        max_bytes: Total size of the recorded payloads.
    """

    max_nodes: int = 64
    max_depth: int = 24
    max_bytes: int = 200 * 1024 * 1024

    def __post_init__(self) -> None:
        if min(self.max_nodes, self.max_depth, self.max_bytes) < 1:
            raise ValueError("Demo limits must be positive")


@dataclass(frozen=True)
class StaticDemoSpec:
    """Everything needed to record one application as a static demo.

    Args:
        app: Factory returning a configured application. It is called once per
            recorded transition, because each is replayed from a fresh
            application rather than from a snapshot of a previous one, so it must
            build the same application every time.
        actions: Scenario per registered action name. Actions left out are
            recorded with their default parameters; pass ``actions={}`` together
            with ``include_actions=[]`` to record none.
        parameters: Values to record per parameter name, for every action and
            workflow step that declares a parameter of that name. Individual
            actions can override this through :class:`ActionScenario`.
        workflow: How to explore the workflow, when the application has one.
        include_actions: Restrict recording to these action names. Defaults to
            every registered action.
        notice: Message shown when the visitor reaches an interaction that was
            not recorded.
        limits: Recording ceilings.
    """

    app: Callable[[], "ImFusionWebApp"]
    actions: Mapping[str, ActionScenario] = field(default_factory=dict)
    parameters: Mapping[str, Sequence[Any]] = field(default_factory=dict)
    workflow: WorkflowScenario = field(default_factory=WorkflowScenario)
    include_actions: Optional[Sequence[str]] = None
    notice: str = DEFAULT_NOTICE
    limits: DemoLimits = field(default_factory=DemoLimits)

    def scenario_for(self, action: str) -> ActionScenario:
        """Return the scenario for an action, or the recorded-defaults scenario."""
        return self.actions.get(action, ActionScenario())

    def parameter_values(self, action: str, name: str, default: Any) -> Sequence[Any]:
        """Return the values to record for one parameter of one action."""
        scenario = self.scenario_for(action)
        if name in scenario.parameters:
            return tuple(scenario.parameters[name])
        if name in self.parameters:
            return tuple(self.parameters[name])
        return (default,)

    def step_parameter_values(self, name: str, default: Any) -> Sequence[Any]:
        """Return the values to record for one workflow step parameter."""
        return tuple(self.parameters.get(name, (default,)))
