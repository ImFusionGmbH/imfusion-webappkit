"""Run the {{PROJECT_TITLE}} assistant."""

from imfusion_webappkit import (
    ImFusionWebApp,
    LayoutConfig,
    MessageStep,
    SidebarConfig,
    SidePosition,
    ThemeConfig,
    ThemePreset,
    TitlePosition,
    Workflow,
)

from conversation import ConversationStep, answer


webapp = ImFusionWebApp(
    title="{{PROJECT_TITLE}}",
    theme=ThemeConfig(preset=ThemePreset.{{THEME_PRESET}}),
    sidebar=SidebarConfig(
        show_datamodel=True,
        show_views=True,
        show_display_options=True,
        collapsed=True,
    ),
    layout=LayoutConfig(
        workflow_panel_position=SidePosition.LEFT,
        workflow_panel_width=360,
        sidebar_position=SidePosition.RIGHT,
        sidebar_width=300,
        header_title_position=TitlePosition.CENTER,
    ),
    show_load_button=True,
    show_export_button=False,
)


def build_workflow(app) -> Workflow:
    """Create one independent conversation per browser session."""
    return Workflow(
        app,
        steps=[
            MessageStep(
                "Welcome",
                (
                    "Load an image, select it in the sidebar, then ask the "
                    "assistant about it. Replies come from a placeholder "
                    "handler until you connect your own model."
                ),
                step_id="welcome",
            ),
            ConversationStep(handler=answer, step_id="conversation"),
        ],
    )


webapp.set_workflow(build_workflow)


if __name__ == "__main__":
    webapp.run(host="127.0.0.1", port=8000)
