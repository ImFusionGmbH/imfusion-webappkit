"""Run a configured MONAI Model Zoo segmentation model on ImFusion images."""

from functools import lru_cache
from pathlib import Path

import imfusion
import numpy as np

# This starter uses one concrete bundle. Change these values together with the
# preprocessing and postprocessing below when adapting another MONAI model.
BUNDLE_NAME = "spleen_ct_segmentation"
BUNDLE_VERSION = "0.6.1"

# ImFusion's patient/world coordinates follow the DICOM LPS convention, while
# MONAI/nibabel affines use RAS. Voxel indices remain ordered X, Y, Z.
LPS_TO_RAS = np.diag((-1.0, -1.0, 1.0, 1.0))


def image_to_monai(image: imfusion.SharedImage) -> tuple[np.ndarray, np.ndarray]:
    """Return channel-first X/Y/Z voxels and a RAS pixel-to-world affine."""
    # image.numpy() applies the ImFusion shift/scale, which is required to
    # recover the original CT values in Hounsfield units.
    voxels = image.numpy()
    if voxels.ndim != 4 or voxels.shape[-1] != 1:
        raise ValueError(
            "The configured model expects a single-channel 3D image; "
            f"received ImFusion array shape {voxels.shape!r}."
        )

    # ImFusion exposes (Z, Y, X, C); MONAI expects (C, X, Y, Z).
    channel_first = np.ascontiguousarray(
        voxels.transpose(3, 2, 1, 0),
        dtype=np.float32,
    )
    pixel_to_world_lps = np.asarray(
        image.pixel_to_world_matrix,
        dtype=np.float64,
    )
    pixel_to_world_ras = LPS_TO_RAS @ pixel_to_world_lps
    return channel_first, pixel_to_world_ras


def monai_to_imfusion(prediction: np.ndarray) -> np.ndarray:
    """Convert a one-channel MONAI X/Y/Z prediction to ImFusion Z/Y/X/C."""
    if prediction.ndim != 4 or prediction.shape[0] != 1:
        raise ValueError(
            "Expected a one-channel MONAI prediction with shape (C, X, Y, Z); "
            f"received {prediction.shape!r}."
        )
    return np.ascontiguousarray(
        prediction.transpose(3, 2, 1, 0),
        dtype=np.uint8,
    )


def create_label_image(
    mask: np.ndarray,
    reference: imfusion.SharedImage,
) -> imfusion.SharedImage:
    """Create an ImFusion label image aligned with its source image."""
    expected_shape = reference.numpy().shape
    if mask.shape != expected_shape:
        raise ValueError(
            "The segmentation does not match the source voxel grid: "
            f"expected {expected_shape!r}, received {mask.shape!r}."
        )
    output = imfusion.SharedImage(mask)
    output.image_to_world_matrix = reference.image_to_world_matrix
    output.spacing = reference.spacing
    return output


def _bundle_root() -> Path:
    """Return MONAI's shared per-user bundle cache."""
    import torch

    return Path(torch.hub.get_dir()) / "bundle"


@lru_cache(maxsize=2)
def _load_model(device_name: str):
    """Download when needed, then load and cache the configured bundle model."""
    import torch
    from monai.bundle import ConfigParser, download

    root = _bundle_root()
    bundle = root / BUNDLE_NAME
    model_file = bundle / "models" / "model.pt"
    if not model_file.is_file():
        download(
            name=BUNDLE_NAME,
            version=BUNDLE_VERSION,
            bundle_dir=str(root),
            progress=True,
        )

    parser = ConfigParser()
    parser.read_config(bundle / "configs" / "inference.json")
    model = parser.get_parsed_content("network_def")
    checkpoint = torch.load(
        model_file,
        map_location=torch.device(device_name),
        weights_only=True,
    )
    state_dict = checkpoint.get("model", checkpoint)
    model.load_state_dict(state_dict)
    model.to(device_name)
    model.eval()
    return model


def _preprocessing():
    """Build preprocessing matching the configured bundle."""
    from monai.transforms import (
        Compose,
        EnsureTyped,
        Orientationd,
        ScaleIntensityRanged,
        Spacingd,
    )

    return Compose(
        [
            Orientationd(
                keys="image",
                axcodes="RAS",
                labels=(("L", "R"), ("P", "A"), ("I", "S")),
            ),
            Spacingd(
                keys="image",
                pixdim=(1.5, 1.5, 2.0),
                mode="bilinear",
            ),
            ScaleIntensityRanged(
                keys="image",
                a_min=-57,
                a_max=164,
                b_min=0,
                b_max=1,
                clip=True,
            ),
            EnsureTyped(keys="image", track_meta=True),
        ]
    )


def _run_inference(image: imfusion.SharedImage, model, device_name: str) -> np.ndarray:
    """Preprocess, infer, and restore one prediction to the input voxel grid."""
    import torch
    from monai.data import MetaTensor
    from monai.inferers import sliding_window_inference
    from monai.transforms import SpatialResample

    voxels, affine = image_to_monai(image)
    preprocessing = _preprocessing()
    processed = preprocessing(
        {
            "image": MetaTensor(
                torch.as_tensor(voxels),
                affine=torch.as_tensor(affine, dtype=torch.float64),
            )
        }
    )

    device = torch.device(device_name)
    input_batch = processed["image"].unsqueeze(0).to(device)
    with (
        torch.inference_mode(),
        torch.autocast(
            device_type=device.type,
            enabled=device.type == "cuda",
        ),
    ):
        prediction = sliding_window_inference(
            inputs=input_batch,
            roi_size=(96, 96, 96),
            sw_batch_size=4,
            predictor=model,
            overlap=0.5,
        )

    # Restore the two-channel logits directly with the source and destination
    # affines. This avoids relying on transform-history bookkeeping across a
    # manually created batch while preserving the bundle's interpolate-then-
    # argmax postprocessing order.
    prediction_tensor = prediction[0]
    if isinstance(prediction_tensor, MetaTensor):
        prediction_tensor = prediction_tensor.as_tensor()
    logits = MetaTensor(
        prediction_tensor,
        affine=processed["image"].affine,
    )
    restored_logits = SpatialResample(
        mode="bilinear",
        padding_mode="border",
        align_corners=False,
    )(
        logits,
        dst_affine=torch.as_tensor(affine, dtype=torch.float64),
        spatial_size=voxels.shape[1:],
    )
    restored = (
        torch.softmax(restored_logits.float(), dim=0)
        .argmax(dim=0, keepdim=True)
        .detach()
        .cpu()
        .numpy()
    )
    mask = monai_to_imfusion(restored)

    if mask.shape != image.numpy().shape:
        raise RuntimeError("MONAI did not restore the prediction to the input grid.")
    return mask


def run_segmentation(imageset: imfusion.SharedImageSet, *, app):
    """Run the configured segmentation model on each 3D image."""
    import torch

    if not len(imageset):
        raise ValueError("Load at least one 3D image before running inference.")

    device_name = "cuda:0" if torch.cuda.is_available() else "cpu"
    app.update_progress(
        0.05,
        f"Downloading or loading MONAI model on {device_name}",
    )
    model = _load_model(device_name)

    label_map = imfusion.SharedImageSet()
    for index, image in enumerate(imageset):
        if app.cancellation_requested:
            raise RuntimeError("Segmentation was cancelled.")
        app.update_progress(
            0.1 + 0.8 * index / len(imageset),
            f"Segmenting image {index + 1} of {len(imageset)}",
        )
        mask = _run_inference(image, model, device_name)
        label_map.add(create_label_image(mask, image))

    label_map.name = "MONAI segmentation"
    label_map.modality = imfusion.Data.Modality.LABEL
    app.update_progress(1.0, "Segmentation complete")
    return label_map
