import asyncio

import pytest

from imfusion_webappkit import ImFusionWebApp, ThemeConfig, ThemePreset


def test_theme_config_is_exposed_to_client():
    theme = ThemeConfig(
        preset=ThemePreset.LIGHT,
        primary="#005f73",
        primary_hover="#004c5c",
        font_family="Inter, sans-serif",
    )
    webapp = ImFusionWebApp(theme=theme)
    endpoint = next(
        route.endpoint
        for route in webapp._fastapi_app.routes
        if getattr(route, "path", None) == "/config"
    )

    config = asyncio.run(endpoint())

    assert config["theme"]["preset"] == "light"
    assert config["theme"]["primary"] == "#005f73"
    assert config["theme"]["primary_hover"] == "#004c5c"
    assert config["theme"]["font_family"] == "Inter, sans-serif"


def test_theme_defaults_to_dark():
    assert ThemeConfig().preset is ThemePreset.DARK


def test_theme_accepts_and_normalizes_string_preset():
    assert ThemeConfig(preset="light").preset is ThemePreset.LIGHT
    assert ThemeConfig(preset="gray").preset is ThemePreset.GRAY


def test_unknown_theme_preset_is_rejected():
    with pytest.raises(ValueError, match="Unknown theme preset 'sepia'"):
        ThemeConfig(preset="sepia")
