import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from imfusion_webappkit import BrandingConfig, ImFusionWebApp
from imfusion_webappkit.routes import branding_config


def test_branding_config_uses_public_asset_urls(tmp_path):
    logo = tmp_path / "logo.svg"
    favicon = tmp_path / "favicon.ico"
    logo.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    favicon.write_bytes(b"icon")

    webapp = ImFusionWebApp(
        branding=BrandingConfig(
            logo=logo,
            favicon=favicon,
            landing_page_title="Welcome",
            landing_page_message="Drop a scan here",
        )
    )

    assert branding_config(webapp) == {
        "logo_url": "/branding/logo",
        "favicon_url": "/branding/favicon",
        "landing_page_title": "Welcome",
        "landing_page_message": "Drop a scan here",
    }


def test_branding_asset_route_serves_configured_file(tmp_path):
    logo = tmp_path / "logo.svg"
    logo.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    webapp = ImFusionWebApp(branding=BrandingConfig(logo=logo))
    endpoint = next(
        route.endpoint
        for route in webapp._fastapi_app.routes
        if getattr(route, "path", None) == "/branding/{asset_name}"
    )

    response = asyncio.run(endpoint("logo"))

    assert isinstance(response, FileResponse)
    assert Path(response.path) == logo.resolve()
    with pytest.raises(HTTPException, match="Branding asset not found"):
        asyncio.run(endpoint("favicon"))


def test_missing_branding_asset_fails_fast(tmp_path):
    missing_logo = tmp_path / "missing.svg"

    with pytest.raises(FileNotFoundError, match="Branding logo file does not exist"):
        ImFusionWebApp(branding=BrandingConfig(logo=missing_logo))
