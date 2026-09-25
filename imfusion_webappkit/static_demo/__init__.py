"""Record an application as a static demo that runs without a Python backend.

A static demo is the real client bundle with its two server touchpoints answered
from files: the configuration it fetches on start-up, and the WebSocket it uses
for everything else. Because the browser already renders through WebAssembly,
viewing, layout and display controls keep working; what a static host cannot
provide is Python, so the results of the interactions worth showing are recorded
in advance from a genuine application.

See ``docs/guides/static-demos.md`` for the authoring guide.
"""

from .spec import (
    ActionScenario,
    AVAILABLE_HANDLERS,
    DemoLimits,
    StaticDemoSpec,
    WorkflowScenario,
)

__all__ = [
    "ActionScenario",
    "AVAILABLE_HANDLERS",
    "DemoLimits",
    "StaticDemoSpec",
    "WorkflowScenario",
]
