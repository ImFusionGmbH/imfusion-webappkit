"""Guided two-image registration using named workflow inputs."""

import imfusion

from imfusion_webappkit import (
    BrandingConfig,
    ImFusionWebApp,
    InputSelectionStep,
    InputSpec,
    ProcessingStep,
    SampleDataset,
    SidebarConfig,
    WebApplicationController,
)
from imfusion_webappkit.examples._assets import (
    BRAIN_PAIR,
    BRAIN_PAIR_THUMBNAIL,
    DEFAULT_LOGO,
)


def register_images(
    fixed: imfusion.SharedImageSet,
    moving: imfusion.SharedImageSet,
    app: WebApplicationController,
) -> imfusion.SharedImageSet:
    """Register the selected moving image to the selected fixed image.

    ``fixed`` and ``moving`` are unpacked from the ``InputSelectionStep``
    roles below because this callback declares a parameter per role.
    """
    app.update_progress(0.1, "Preparing registration")
    algorithm = imfusion.registration.ImageRegistrationAlgorithm(fixed, moving)
    algorithm()
    app.update_progress(0.8, "Applying deformation")
    registered = imfusion.registration.apply_deformation(moving)
    app.update_progress(1.0, "Registration complete")
    return registered


class RegistrationStep(ProcessingStep):
    """Registration that leaves only the fixed image and the result in view.

    The browser shows every dataset it receives, so the unregistered moving
    image would otherwise stay in the views and obscure the alignment. The
    selection is set after ``run`` because the result only enters the data
    model once the callback has returned.
    """

    def on_enter(self) -> None:
        super().on_enter()
        if self.result is None:
            return
        fixed = self.app.workflow.get_step(self.inputs_from).inputs["fixed"]
        self.app.select_data([fixed, self.result])


def main(host: str = "127.0.0.1", port: int = 8001) -> None:
    webapp = ImFusionWebApp(
        title="Registration Workflow",
        branding=BrandingConfig(logo=DEFAULT_LOGO),
        sidebar=SidebarConfig(show_datamodel=True, collapsed=True),
        show_load_button=False,
        # One file holding both sessions, so a single card fills both roles.
        sample_datasets=[
            SampleDataset("Brain MRI pair", BRAIN_PAIR, BRAIN_PAIR_THUMBNAIL),
        ],
    )
    webapp.set_workflow(
        [
            InputSelectionStep(
                title="Select Registration Inputs",
                step_id="registration_inputs",
                message="Load the fixed and moving images, then assign their roles.",
                inputs=[
                    InputSpec("fixed", "Fixed image"),
                    InputSpec("moving", "Moving image"),
                ],
            ),
            RegistrationStep(
                title="Register Images",
                callback=register_images,
                inputs_from="registration_inputs",
                auto_proceed=False,
                step_id="register",
            ),
        ]
    )
    webapp.run(host=host, port=port)


if __name__ == "__main__":
    main()
