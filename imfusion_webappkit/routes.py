"""HTTP and WebSocket route registration for the web application."""

# Route registration is an internal collaborator of ImFusionWebApp.
# pylint: disable=protected-access

from typing import TYPE_CHECKING
from urllib.parse import quote

from fastapi import HTTPException, WebSocket
from fastapi.responses import FileResponse

if TYPE_CHECKING:
    from .app import ImFusionWebApp


def branding_config(webapp: "ImFusionWebApp") -> dict:
    """Return browser-safe branding settings without local file paths."""
    return {
        "logo_url": "/branding/logo" if webapp.branding.logo else None,
        "favicon_url": "/branding/favicon" if webapp.branding.favicon else None,
        "landing_page_title": webapp.branding.landing_page_title,
        "landing_page_message": webapp.branding.landing_page_message,
    }


def sample_datasets_config(webapp: "ImFusionWebApp") -> list[dict]:
    """Return browser-safe sample dataset settings."""
    return [
        {
            "name": dataset.name,
            "data_url": (
                f"/sample-datasets/{index}/data/{quote(dataset.path.name, safe='')}"
            ),
            "thumbnail_url": (
                f"/sample-datasets/{index}/thumbnail/"
                f"{quote(dataset.thumbnail.name, safe='')}"
                if dataset.thumbnail
                else None
            ),
        }
        for index, dataset in enumerate(webapp._sample_datasets)
    ]


def setup_routes(webapp: "ImFusionWebApp") -> None:
    """Register application routes before the static-file catch-all."""

    @webapp._fastapi_app.get("/config")
    async def get_config():
        return {
            "protocol_version": 7,
            "title": webapp.title,
            "branding": branding_config(webapp),
            "info": webapp.info.to_dict() if webapp.info else None,
            "theme": webapp.theme.to_dict(),
            "layout": webapp.layout.to_dict(),
            "sidebar": (
                webapp.sidebar_config.to_dict() if webapp.sidebar_config else None
            ),
            "algorithms_enabled": webapp.algorithm_registry.is_enabled(),
            "algorithms_placement": webapp.algorithm_selector_placement,
            "algorithm_controllers": webapp.algorithm_registry.get_controllers(),
            "show_load_button": webapp.show_load_button,
            "show_export_button": webapp.show_export_button,
            "export_formats": [fmt.value for fmt in webapp.export_formats],
            "workflow_enabled": webapp._workflow_factory is not None,
            "sample_datasets": sample_datasets_config(webapp),
        }

    @webapp._fastapi_app.get("/branding/{asset_name}", include_in_schema=False)
    async def get_branding_asset(asset_name: str):
        path = {"logo": webapp.branding.logo, "favicon": webapp.branding.favicon}.get(
            asset_name
        )
        if path is None:
            raise HTTPException(status_code=404, detail="Branding asset not found")
        return FileResponse(path)

    @webapp._fastapi_app.get(
        "/sample-datasets/{dataset_index}/{asset_type}/{filename}",
        include_in_schema=False,
    )
    async def get_sample_dataset_asset(
        dataset_index: int, asset_type: str, filename: str
    ):
        if dataset_index < 0 or dataset_index >= len(webapp._sample_datasets):
            raise HTTPException(status_code=404, detail="Sample dataset not found")
        dataset = webapp._sample_datasets[dataset_index]
        path = (
            dataset.path
            if asset_type == "data"
            else dataset.thumbnail if asset_type == "thumbnail" else None
        )
        if path is None or path.name != filename:
            raise HTTPException(
                status_code=404, detail="Sample dataset asset not found"
            )
        return FileResponse(path)

    @webapp._fastapi_app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await webapp.websocket_handler.handle_websocket(websocket)
