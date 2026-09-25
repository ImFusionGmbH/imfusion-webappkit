import asyncio

import pytest

from imfusion_webappkit import ImFusionWebApp


def _client_config(webapp: ImFusionWebApp) -> dict:
    endpoint = next(
        route.endpoint
        for route in webapp._fastapi_app.routes
        if getattr(route, "path", None) == "/config"
    )
    return asyncio.run(endpoint())


@pytest.mark.parametrize("placement", ["sidebar", "header"])
def test_generic_algorithm_placement_is_exposed(placement):
    webapp = ImFusionWebApp(algorithm_selector=placement)

    config = _client_config(webapp)
    assert config["algorithms_enabled"] is True
    assert config["algorithms_placement"] == placement


def test_algorithm_selector_is_disabled_by_default():
    webapp = ImFusionWebApp()

    assert _client_config(webapp)["algorithms_enabled"] is False
    assert _client_config(webapp)["algorithms_placement"] == "sidebar"


def test_invalid_algorithm_selector_placement_is_rejected():
    with pytest.raises(ValueError, match="placement"):
        ImFusionWebApp(algorithm_selector="footer")


def test_dedicated_algorithm_controller_placement_is_exposed(monkeypatch):
    monkeypatch.setattr(
        "imfusion_webappkit.algorithm_registry.imfusion.algorithm.list_available",
        lambda: ["Base.MorphologicalOperations"],
    )
    webapp = ImFusionWebApp()

    webapp.register(
        "Morphological Operations",
        algorithm="Base.MorphologicalOperations",
        placement="header",
    )

    [controller] = _client_config(webapp)["algorithm_controllers"]
    assert controller["placement"] == "header"
