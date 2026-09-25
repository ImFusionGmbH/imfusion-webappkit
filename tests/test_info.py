import asyncio

import pytest

from imfusion_webappkit import ImFusionWebApp, InfoConfig


def test_info_config_is_exposed_to_client():
    webapp = ImFusionWebApp(
        info=InfoConfig(
            button_label="Project",
            title="About this project",
            content="Read the [paper](https://example.com/paper).",
        )
    )
    endpoint = next(
        route.endpoint
        for route in webapp._fastapi_app.routes
        if getattr(route, "path", None) == "/config"
    )

    config = asyncio.run(endpoint())

    assert config["info"] == {
        "button_label": "Project",
        "title": "About this project",
        "content": "Read the [paper](https://example.com/paper).",
    }


def test_info_is_disabled_by_default():
    webapp = ImFusionWebApp()
    endpoint = next(
        route.endpoint
        for route in webapp._fastapi_app.routes
        if getattr(route, "path", None) == "/config"
    )

    assert asyncio.run(endpoint())["info"] is None


@pytest.mark.parametrize("field", ["content", "title", "button_label"])
def test_info_config_rejects_blank_fields(field):
    values = {
        "content": "Project details",
        "title": "About",
        "button_label": "About",
    }
    values[field] = "  "

    with pytest.raises(ValueError, match=field):
        InfoConfig(**values)
