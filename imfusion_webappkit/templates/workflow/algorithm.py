"""Intensity-threshold segmentation used by the workflow."""

import imfusion
import numpy as np


def process_image(imageset: imfusion.SharedImageSet, *, threshold, app):
    """Create a label map containing voxels at or above the threshold."""
    label_map = imfusion.SharedImageSet()

    for index, image in enumerate(imageset):
        source = image.numpy()
        segmentation = (source >= threshold).astype(np.uint8)
        output_image = imfusion.SharedImage(segmentation)
        output_image.image_to_world_matrix = image.image_to_world_matrix
        output_image.spacing = image.spacing
        label_map.add(output_image)
        app.update_progress(
            (index + 1) / len(imageset),
            f"Thresholding image {index + 1} of {len(imageset)}",
        )

    label_map.name = "Threshold segmentation"
    label_map.modality = imfusion.Data.Modality.LABEL
    return label_map
