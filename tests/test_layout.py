import asyncio

import pytest

from imfusion_webappkit import (
    ImFusionWebApp,
    LayoutConfig,
    SidebarConfig,
    SidePosition,
    TitlePosition,
    ViewLayout,
    ViewType,
)


def test_layout_config_is_exposed_to_client():
    webapp = ImFusionWebApp(
        layout=LayoutConfig(
            header_title_position=TitlePosition.CENTER,
            header_logo_position=SidePosition.RIGHT,
            sidebar_position=SidePosition.RIGHT,
            sidebar_width=280,
            sidebar_resizable=False,
            workflow_panel_position=SidePosition.RIGHT,
            workflow_panel_width=360,
            workflow_panel_resizable=False,
            show_status_bar=False,
            initial_view_layout=ViewLayout.FOCUS_PLUS_ROWS,
            initial_visible_views=(ViewType.TWO_D, ViewType.MPR, ViewType.THREE_D),
        )
    )
    endpoint = next(
        route.endpoint
        for route in webapp._fastapi_app.routes
        if getattr(route, "path", None) == "/config"
    )

    config = asyncio.run(endpoint())

    assert config["layout"] == {
        "header_title_position": "center",
        "header_logo_position": "right",
        "sidebar_position": "right",
        "sidebar_width": 280,
        "sidebar_resizable": False,
        "workflow_panel_position": "right",
        "workflow_panel_width": 360,
        "workflow_panel_resizable": False,
        "show_status_bar": False,
        "initial_view_layout": "FocusPlusRows",
        "initial_visible_views": ("2d", "mpr", "3d"),
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"header_title_position": "bottom"}, "header_title_position"),
        ({"header_logo_position": "center"}, "header_logo_position"),
        ({"sidebar_position": "top"}, "sidebar_position"),
        ({"sidebar_width": 100}, "sidebar_width"),
        ({"workflow_panel_position": "top"}, "workflow_panel_position"),
        ({"workflow_panel_width": 100}, "workflow_panel_width"),
        ({"sidebar_resizable": "yes"}, "sidebar_resizable"),
        ({"workflow_panel_resizable": 1}, "workflow_panel_resizable"),
        ({"initial_view_layout": "Grid"}, "initial_view_layout"),
        ({"initial_visible_views": ("oblique",)}, "initial_visible_views"),
    ],
)
def test_invalid_layout_config_is_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        LayoutConfig(**kwargs)


def test_header_title_defaults_to_left():
    assert LayoutConfig().header_title_position is TitlePosition.LEFT
    assert LayoutConfig().header_logo_position is SidePosition.LEFT


def test_panels_are_resizable_by_default():
    assert LayoutConfig().sidebar_resizable is True
    assert LayoutConfig().workflow_panel_resizable is True


@pytest.mark.parametrize(
    "view",
    list(ViewType),
)
def test_supported_initial_view_is_accepted(view):
    assert LayoutConfig(initial_visible_views=(view,)).initial_visible_views == (view,)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3d", ("3d",)),
        (["axial", "3d"], ("axial", "3d")),
        (("2d", "mpr"), ("2d", "mpr")),
    ],
)
def test_initial_views_accept_string_list_or_tuple(value, expected):
    views = LayoutConfig(initial_visible_views=value).initial_visible_views

    assert tuple(view.value for view in views) == expected
    assert all(isinstance(view, ViewType) for view in views)


def test_layout_accepts_and_normalizes_string_values():
    layout = LayoutConfig(
        header_title_position="center",
        sidebar_position="right",
        initial_view_layout="Rows",
    )

    assert layout.header_title_position is TitlePosition.CENTER
    assert layout.sidebar_position is SidePosition.RIGHT
    assert layout.initial_view_layout is ViewLayout.ROWS


def test_workflow_accepts_sidebar():
    webapp = ImFusionWebApp(sidebar=SidebarConfig())

    webapp.set_workflow(lambda *_args: None)
