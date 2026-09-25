"""Tests for WebApp action and SDK algorithm registration."""

import imfusion
import numpy as np
import pytest

from imfusion_webappkit import ImFusionWebApp, InputSpec


def _image() -> imfusion.SharedImageSet:
    return imfusion.SharedImageSet(np.ones((1, 2, 2, 1), dtype=np.float32))


def test_register_decorates_functions_without_replacing_them():
    app = ImFusionWebApp()

    @app.register("Identity")
    def identity(image):
        return image

    image = _image()
    assert app.action_registry.execute_action("Identity", image) is image
    assert identity(image) is image


def test_register_accepts_an_existing_callable():
    app = ImFusionWebApp()

    def identity(image):
        return image

    assert app.register("Identity", identity) is identity
    image = _image()
    assert app.action_registry.execute_action("Identity", image) is image


def test_stacked_decorators_expose_one_sdk_algorithm_to_suite_and_webapp():
    app = ImFusionWebApp()

    @app.register("Web threshold", inputs=[InputSpec("image", "Image")])
    @imfusion.algorithm.register(display_name="Web threshold")
    class WebThresholdAlgorithm:
        image = imfusion.algorithm.Input(imfusion.SharedImageSet)
        threshold = imfusion.algorithm.ParamDouble(
            "Threshold",
            default=0.5,
            min=0.0,
            max=1.0,
            step=0.1,
        )

        def __call__(self):
            return self.image

    assert WebThresholdAlgorithm.id in imfusion.algorithm.list_available()
    [panel] = app.algorithm_registry.get_controllers()
    assert panel["id"] == WebThresholdAlgorithm.id
    assert panel["title"] == "Web threshold"

    image = _image()
    details = app.algorithm_registry.get_controller_with_compatibility(
        WebThresholdAlgorithm.id, [image]
    )
    assert details["compatible"] is True
    assert details["parameters"]["Threshold"]["default"] == 0.5
    assert details["parameters"]["Threshold"]["min"] == 0.0
    assert details["parameters"]["Threshold"]["max"] == 1.0
    assert details["parameters"]["Threshold"]["step"] == 0.1
    output = app.algorithm_registry.execute_algorithm(
        WebThresholdAlgorithm.id,
        [image],
        {"Threshold": 0.75},
    )
    assert len(output) == 1
    assert isinstance(output[0], imfusion.SharedImageSet)
    np.testing.assert_array_equal(np.asarray(output[0][0]), np.asarray(image[0]))


def test_register_exposes_native_algorithm_by_id(monkeypatch):
    monkeypatch.setattr(
        "imfusion_webappkit.algorithm_registry.imfusion.algorithm.list_available",
        lambda: ["Base.MorphologicalOperations"],
    )
    app = ImFusionWebApp()

    assert (
        app.register(
            "Morphology",
            algorithm="Base.MorphologicalOperations",
            placement="header",
        )
        == "Base.MorphologicalOperations"
    )

    [panel] = app.algorithm_registry.get_controllers()
    assert panel["id"] == "Base.MorphologicalOperations"
    assert panel["title"] == "Morphology"
    assert panel["placement"] == "header"


def test_unregistered_classes_are_not_treated_as_web_actions():
    app = ImFusionWebApp()

    with pytest.raises(TypeError, match="imfusion.algorithm.register"):

        @app.register("Invalid")
        class Invalid:
            def __call__(self, app):
                pass


def test_algorithm_parameters_cannot_be_redeclared():
    app = ImFusionWebApp()

    with pytest.raises(ValueError, match="Properties"):
        app.register(
            "Invalid",
            algorithm="Base.MorphologicalOperations",
            parameters=[{"name": "size", "type": "int", "default": 1}],
        )
