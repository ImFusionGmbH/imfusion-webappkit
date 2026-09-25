"""Run the {{PROJECT_TITLE}} demo."""

from imfusion_webappkit import (
    FloatParameter,
    ImFusionWebApp,
    InfoConfig,
    SidebarConfig,
    ThemeConfig,
    ThemePreset,
)

from algorithm import process_image

webapp = ImFusionWebApp(
    title="{{PROJECT_TITLE}}",
    theme=ThemeConfig(preset=ThemePreset.{{THEME_PRESET}}),
    sidebar=SidebarConfig(),
    show_export_button=True,
    info=InfoConfig(
        title="About {{PROJECT_TITLE}}",
        content="Replace this text with your method description and citation.",
    ),
)


webapp.register(
    "Segment Image",
    process_image,
    parameters=[
        FloatParameter(
            "threshold",
            label="Intensity Threshold",
            default=100.0,
            minimum=-1000.0,
            maximum=4096.0,
            step=1.0,
        ),
    ],
)


if __name__ == "__main__":
    webapp.run(host="127.0.0.1", port=8000)
