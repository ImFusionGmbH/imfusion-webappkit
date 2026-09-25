"""Two-image registration as a regular multi-input action."""

import imfusion

from imfusion_webappkit import BrandingConfig, ImFusionWebApp, InputSpec, SidebarConfig
from imfusion_webappkit.examples._assets import DEFAULT_LOGO


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    webapp = ImFusionWebApp(
        title="Multi-Input Registration",
        branding=BrandingConfig(logo=DEFAULT_LOGO),
        sidebar=SidebarConfig(show_datamodel=True),
        show_load_button=True,
        show_export_button=True,
    )

    @webapp.register(
        "Register Images",
        inputs=[
            InputSpec("fixed", "Fixed image"),
            InputSpec("moving", "Moving image"),
        ],
        result_input="moving",
    )
    @imfusion.algorithm.register(display_name="Register Images")
    class RegisterImages:
        fixed = imfusion.algorithm.Input(imfusion.SharedImageSet)
        moving = imfusion.algorithm.Input(imfusion.SharedImageSet)

        def __call__(self) -> imfusion.SharedImageSet:
            """Register the selected moving image to the fixed image."""
            algorithm = imfusion.registration.ImageRegistrationAlgorithm(
                self.fixed, self.moving
            )
            algorithm()
            return imfusion.registration.apply_deformation(self.moving)

    webapp.run(host=host, port=port)


if __name__ == "__main__":
    main()
