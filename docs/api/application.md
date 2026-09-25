# Application

The application class configures the browser UI, registers actions and
algorithms, creates per-browser sessions, and runs the web server.

::: imfusion_webappkit.app.ImFusionWebApp

## Session controller

Callbacks and workflow factories receive one controller per browser connection.
It exposes the portable `imfusion.app`-style surface and web-specific progress
and selection operations.

::: imfusion_webappkit.application_controller.WebApplicationController

## Execution policy

The HTTP and WebSocket server runs on its own thread. Operations that may touch
the ImFusion SDK are queued and executed serially on the thread that created
the application and owns ImFusion's OpenGL context.

Each session may have one queued or running operation. Cancelling queued work
prevents it from starting. Cancelling running native work marks it as
cancel-requested; the Python SDK does not expose a general algorithm
interruption API. WebAppKit suppresses automatic publication of returned
outputs when possible, but it cannot roll back in-place SDK mutations or
arbitrary callback side effects. Long callbacks should check
`app.cancellation_requested` before committing side effects.
