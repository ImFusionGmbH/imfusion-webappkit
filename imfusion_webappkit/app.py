"""FastAPI application for the ImFusion WebSDK."""

# The app coordinates private synchronization state owned by its collaborators.
# pylint: disable=protected-access

import logging
import threading
import uuid
from pathlib import Path
from typing import (
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Sequence,
    TYPE_CHECKING,
    Union,
)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from .action_registry import ActionRegistry
from .algorithm_registry import AlgorithmRegistry
from .config import (
    BrandingConfig,
    InfoConfig,
    LayoutConfig,
    SampleDataset,
    SidebarConfig,
    ThemeConfig,
)
from .data_export import ExportFormat, SUPPORTED_EXPORT_FORMATS
from .data_model import WebAppDataModel
from .image_protocol import ImageProtocol
from .operation_registration import OperationRegistrationMixin
from .routes import setup_routes
from .sdk_runtime import MainThreadSDKRuntime
from .operation_runner import OperationRunner
from .session import Session
from .websocket_handler import WebSocketHandler
from .workflow import Workflow, WorkflowStep

if TYPE_CHECKING:
    from .application_controller import WebApplicationController

logger = logging.getLogger(__name__)


class ImFusionWebApp(OperationRegistrationMixin):
    """FastAPI-based web application for ImFusion WebSDK Python integration."""

    def __init__(
        self,
        title: str = "ImFusion WebApp",
        sidebar: Optional[SidebarConfig] = None,
        show_load_button: bool = True,
        show_export_button: bool = False,
        branding: Optional[BrandingConfig] = None,
        info: Optional[InfoConfig] = None,
        theme: Optional[ThemeConfig] = None,
        layout: Optional[LayoutConfig] = None,
        export_formats: Optional[Sequence[Union[str, ExportFormat]]] = None,
        sample_datasets: Optional[Sequence[SampleDataset]] = None,
        algorithm_selector: Optional[Literal["sidebar", "header"]] = None,
    ):
        """Initialize the ImFusion WebSDK web application."""
        self._fastapi_app = FastAPI(title=title)
        self.action_registry = ActionRegistry()
        self.algorithm_registry = AlgorithmRegistry()
        if algorithm_selector is not None:
            self._validate_placement(algorithm_selector)
        self.algorithm_selector_placement: Literal["sidebar", "header"] = (
            algorithm_selector or "sidebar"
        )
        if algorithm_selector is not None:
            self.algorithm_registry.enable()
        self.protocol = ImageProtocol()
        self.sdk_runtime = MainThreadSDKRuntime(owner_thread_id=threading.get_ident())
        self.title = title
        self.sidebar_config = sidebar
        self.branding = branding or BrandingConfig()
        self.info = info
        self.theme = theme or ThemeConfig()
        self.layout = layout or LayoutConfig()
        self._sample_datasets = []
        for dataset in sample_datasets or ():
            data_path = Path(dataset.path).expanduser().resolve()
            if not data_path.is_file():
                raise FileNotFoundError(
                    f"Sample dataset file does not exist: {data_path}"
                )
            thumbnail_path = None
            if dataset.thumbnail is not None:
                thumbnail_path = Path(dataset.thumbnail).expanduser().resolve()
                if not thumbnail_path.is_file():
                    raise FileNotFoundError(
                        f"Sample dataset thumbnail does not exist: {thumbnail_path}"
                    )
            self._sample_datasets.append(
                SampleDataset(dataset.name, data_path, thumbnail_path)
            )
        self.show_load_button = show_load_button
        self.show_export_button = show_export_button
        requested_formats = export_formats or SUPPORTED_EXPORT_FORMATS
        self.export_formats = list(
            dict.fromkeys(ExportFormat(value) for value in requested_formats)
        )

        self._sessions: Dict[str, Session] = {}
        self._session_callbacks: List[Callable[["WebApplicationController"], None]] = []
        self._workflow_factory: Optional[
            Callable[["WebApplicationController"], Workflow]
        ] = None
        self.initial_data = WebAppDataModel(self, session=None)
        self.operation_runner = OperationRunner(self)
        self.websocket_handler = WebSocketHandler(self)

        self.static_dir = Path(__file__).parent / "static"
        dist_dir = self.static_dir / "dist"
        self._missing_client_bundle = not dist_dir.exists()
        client_dir = dist_dir if dist_dir.exists() else self.static_dir

        setup_routes(self)
        # Catch-all mount that serves static/dist/index.html for any path not
        # already handled above. That page loads the transpiled static/src/main.tsx,
        # which initializes and renders the WebSDK viewer in the browser.
        self._fastapi_app.mount(
            "/", StaticFiles(directory=str(client_dir), html=True), name="static"
        )

    def _create_session(self) -> Session:
        """Create a session and copy pre-loaded data into it."""
        session_id = str(uuid.uuid4())
        session = Session(self, session_id)
        self._sessions[session_id] = session
        logger.info("Created new session: %s", session_id)
        return session

    def _remove_session(self, session: Session) -> None:
        """Remove a session."""
        if session.session_id in self._sessions:
            del self._sessions[session.session_id]
            logger.info("Removed session: %s", session.session_id)

    def on_session_created(
        self, callback: Callable[["WebApplicationController"], None]
    ) -> None:
        """Register a callback run once per browser connection.

        The place to hook up per-session listeners that no action or workflow
        step owns — ``app.annotation_model.on_annotation_added`` for an
        application that lets the user draw whenever they like. Called on the
        ImFusion SDK owner thread with that session's controller, after its seed
        data and workflow exist.
        """
        self._session_callbacks.append(callback)

    def set_workflow(
        self,
        workflow: Union[
            Callable[["WebApplicationController"], Workflow],
            Sequence[WorkflowStep],
        ],
    ):
        """Configure the workflow used to create an isolated instance per session.

        Accepts either a factory ``Callable[[app], Workflow]`` for advanced or
        session-conditional workflows, or a plain sequence of steps that is
        cloned into a fresh ``Workflow`` for each session.
        """
        if isinstance(workflow, (list, tuple)):
            steps = list(workflow)

            def factory(app: "WebApplicationController") -> Workflow:
                return Workflow(app, steps=[step.clone() for step in steps])

            self._workflow_factory = factory
        else:
            self._workflow_factory = workflow
        logger.info("Set workflow factory")

    def run(self, host: str = "localhost", port: int = 8000, **kwargs):
        """Start the server."""
        if self._missing_client_bundle:
            logger.warning(
                "Built client not found. Run 'npm run build' in imfusion_webappkit/static/ "
                "or use Vite dev server for development (npm run dev on port 3000)."
            )
        logger.info("Starting server on %s:%s", host, port)
        logger.info("Registered actions: %s", self.action_registry.list_actions())
        config = uvicorn.Config(
            self._fastapi_app,
            host=host,
            port=port,
            ws_max_size=1000 * 1024 * 1024,
            timeout_keep_alive=300,
            **kwargs,
        )
        server = uvicorn.Server(config)
        server_errors = []

        def run_server():
            try:
                server.run()
            except (Exception, SystemExit) as exc:
                server_errors.append(exc)

        server_thread = threading.Thread(
            target=run_server,
            name="imfusion-webappkit-server",
            daemon=True,
        )
        server_thread.start()
        try:
            self.sdk_runtime.run_until(server_thread)
        except KeyboardInterrupt:
            logger.info("Stopping server")
            server.should_exit = True
        finally:
            server.should_exit = True
            forced_shutdown = False
            try:
                while server_thread.is_alive():
                    self.sdk_runtime.run_once(timeout=0.05)
            except KeyboardInterrupt:
                logger.info("Forcing server shutdown")
                forced_shutdown = True
            finally:
                self.sdk_runtime.stop()
                server_thread.join(timeout=10 if forced_shutdown else None)
        if server_thread.is_alive():
            raise RuntimeError("Web server did not stop after forced shutdown")
        if server_errors:
            raise RuntimeError("Web server failed") from server_errors[0]
