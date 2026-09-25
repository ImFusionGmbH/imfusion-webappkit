/**
 * Everything the page says that is not markup: the outbound links, the one
 * piece of copy that appears twice, and the snippets the code blocks show.
 *
 * Plain strings only — `vite.config.ts` imports from here to inject the
 * description into the HTML, so this module has to load outside the bundle.
 */

/**
 * Outbound destinations, in one place. GitHub Pages serves one site per
 * repository: this page is that site's root and the documentation is built
 * into `docs/` beneath it, which is the split `.github/workflows/pages.yml`
 * assembles.
 *
 * Both GitHub destinations fall back to the canonical site but can be set at
 * build time, so a deployment from anywhere else — a private trial repository
 * under another name, say — links to itself instead of to a site that may not
 * exist yet. `vite.config.ts` turns these lookups into literals when it
 * bundles, and reads them directly when it imports this module under Node.
 */
export const REPO_URL =
  process.env.WEBAPPKIT_REPO_URL || "https://github.com/ImFusionGmbH/imfusion-webappkit";
export const DOCS_URL =
  process.env.WEBAPPKIT_DOCS_URL || "https://imfusiongmbh.github.io/imfusion-webappkit/docs";
export const CONTACT_URL = "mailto:info@imfusion.com?subject=ImFusion%20WebAppKit";

/** mkdocs.yml sets `use_directory_urls: false`, so pages keep their .html suffix. */
export const docsPage = (page: string) => `${DOCS_URL}/${page}.html`;
export const repoPath = (path: string) => `${REPO_URL}/tree/master/${path}`;

/** Shown in the hero and as the page description, so the two cannot drift. */
export const HERO_LEAD =
  "The ImFusion WebAppKit serves your Python imaging algorithms in a medical web viewer over HTTP. Demo them to colleagues and clinicians without writing any web code.";

export const APP_PY = `import numpy as np
import imfusion

from imfusion_webappkit import FloatParameter, ImFusionWebApp

app = ImFusionWebApp(title="Image Tools")

@app.register(
    "Threshold",
    parameters=[
        FloatParameter(
            "threshold", default=100.0, minimum=0.0, maximum=1000.0,
        ),
    ],
)
def apply_threshold(
    imageset: imfusion.SharedImageSet,
    *,
    threshold: float,
) -> imfusion.SharedImageSet:
    image = imageset[0]
    label = imfusion.SharedImage((image.numpy() >= threshold).astype(np.uint8))
    label.image_to_world_matrix = image.image_to_world_matrix
    label.spacing = image.spacing

    mask = imfusion.SharedImageSet()
    mask.add(label)
    mask.modality = imfusion.Data.Modality.LABEL
    return mask

app.run()
`;

export const WORKFLOW_PY = `app.set_workflow([
    MessageStep("Welcome", "Load, segment, correct, export."),
    InputSelectionStep("Select Image", inputs=[image]),
    ParameterStep("Configure", parameters=[threshold]),
    ProcessingStep("Segment", callback=threshold_segment),
    BrushStep("Correct Segmentation", radius_mm=5.0),
    SegmentationSummaryStep(label_map_from="process"),
    ValidationStep("Review", "Is this acceptable?"),
    ExportStep("Export Segmentation"),
])
`;

export const INSTALL_COMMANDS = `uv sync
uv run imfusion-webappkit demo`;

export const PIP_COMMANDS = `pip install imfusion-webappkit --extra-index-url https://pypi.imfusion.com/simple
imfusion-webappkit demo`;

export const INIT_COMMANDS = `uv run imfusion-webappkit init my-demo
cd my-demo && uv sync
uv run python app.py`;
