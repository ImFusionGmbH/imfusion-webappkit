"""Tests for schema-driven action parameters."""

import pytest

from imfusion_webappkit import (
    BoolParameter,
    ChoiceParameter,
    FloatParameter,
    IntParameter,
)
from imfusion_webappkit.action_registry import ActionRegistry


def test_parameterized_action_receives_validated_keyword_values():
    registry = ActionRegistry()
    app = object()
    image = object()
    observed = {}

    def segment(image, *, threshold, model, postprocess, app):
        observed.update(
            image=image,
            threshold=threshold,
            model=model,
            postprocess=postprocess,
            app=app,
        )
        return image

    registry.register(
        "Segment",
        segment,
        parameters=[
            FloatParameter(
                "threshold", default=0.5, minimum=0.0, maximum=1.0, step=0.05
            ),
            ChoiceParameter("model", options=["Fast", "Accurate"], default="Fast"),
            BoolParameter("postprocess", default=True),
        ],
    )

    assert (
        registry.execute_action(
            "Segment",
            image,
            {"threshold": 0.75, "model": "Accurate", "postprocess": False},
            app=app,
        )
        is image
    )
    assert observed == {
        "image": image,
        "threshold": 0.75,
        "model": "Accurate",
        "postprocess": False,
        "app": app,
    }

    descriptor = registry.list_action_descriptors()[0]
    assert descriptor["parameters"]["threshold"] == {
        "name": "threshold",
        "type": "float",
        "label": "Threshold",
        "value": 0.5,
        "default": 0.5,
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
    }


def test_parameter_defaults_and_server_validation():
    registry = ActionRegistry()

    def repeat(image, *, count):
        return image, count

    registry.register(
        "Repeat",
        repeat,
        parameters=[IntParameter("count", default=2, minimum=1, maximum=5)],
    )

    image = object()
    assert registry.execute_action("Repeat", image) == (image, 2)
    with pytest.raises(ValueError, match="at most 5"):
        registry.execute_action("Repeat", image, {"count": 6})
    with pytest.raises(ValueError, match="Unknown action parameters"):
        registry.execute_action("Repeat", image, {"other": 2})


def test_parameterized_app_only_action_needs_no_dataset():
    registry = ActionRegistry()
    app = object()

    def generate(*, size, app):
        return size, app

    registry.register(
        "Generate phantom",
        generate,
        parameters=[IntParameter("size", default=64, minimum=16, maximum=512)],
    )

    metadata = registry.get_action_metadata("Generate phantom")
    assert metadata["is_app_only"] is True
    assert metadata["inputs"] == []
    assert registry.execute_action(
        "Generate phantom", parameters={"size": 128}, app=app
    ) == (
        128,
        app,
    )


def test_parameter_schema_must_match_callback_signature():
    registry = ActionRegistry()

    with pytest.raises(ValueError, match="missing from callback signature"):
        registry.register(
            "Invalid",
            lambda image: image,
            parameters=[BoolParameter("enabled", default=True)],
        )


def test_unparameterized_app_only_action_receives_session_controller():
    registry = ActionRegistry()
    app = object()
    observed = []

    registry.register("Clear", lambda app: observed.append(app))
    registry.execute_action("Clear", app=app)

    assert observed == [app]
    assert registry.get_action_metadata("Clear")["inputs"] == []
