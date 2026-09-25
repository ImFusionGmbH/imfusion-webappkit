# {{PROJECT_TITLE}}

A guided WebAppKit example that runs a MONAI Model Zoo bundle directly with
PyTorch. The starter is configured with `spleen_ct_segmentation`, but its
structure is intended as a starting point for other segmentation bundles. It
does not use the ImFusion machine-learning inference API.

This model and application are examples for research and development. They are
not medical devices and must not be used for diagnosis.

## Set up

Install the project dependencies:

```bash
uv sync
```

Start the application:

```bash
uv run python app.py
```

Then open <http://127.0.0.1:8000>, load a single-channel 3D CT volume whose
intensities represent Hounsfield units, select it as the model input, and follow
the workflow. The explicit selection keeps repeat inference tied to the source
volume after a label map has been published. Inference starts only when you
click **Run Segmentation** on the processing step.

The first inference automatically downloads the configured bundle. MONAI stores
it in PyTorch's shared per-user cache under `torch.hub.get_dir()/bundle`, so
other generated applications reuse the same files. Set `TORCH_HOME` before
launching the app to choose a different common cache directory. CUDA is used
when PyTorch detects it; otherwise inference runs on the CPU and may take
several minutes.

## How image conversion works

`algorithm.py` keeps the conversion explicit:

1. `SharedImage.numpy()` obtains original CT intensities with ImFusion
   shift/scale applied.
2. ImFusion's `(Z, Y, X, C)` NumPy layout is transposed to MONAI's
   channel-first `(C, X, Y, Z)` layout.
3. The ImFusion pixel-to-world matrix is converted from DICOM LPS coordinates
   to the RAS coordinates used by MONAI and nibabel.
4. MONAI records the resampled grid in a `MetaTensor`; the prediction logits
   are resampled from that affine directly onto the original affine and shape.
5. The mask is transposed back to `(Z, Y, X, C)`. Its ImFusion spacing and
   image-to-world matrix are copied from the source image so both datasets
   overlay correctly.

The current preprocessing uses RAS orientation, spacing `(1.5, 1.5, 2.0)` mm,
HU clipping to `[-57, 164]`, and scaling to `[0, 1]`. Inference uses 96³
sliding windows with 50% overlap, followed by softmax and argmax.

## Adapt another MONAI model

Update these sections in `algorithm.py` together:

- `BUNDLE_NAME`, `BUNDLE_VERSION`, and `_load_model()` for the model artifact;
- `_preprocessing()` to exactly match the bundle's inference configuration;
- `_run_inference()` for patch size, overlap, activation, and discretization;
- the output name and label metadata in `run_segmentation()`.

Do not reuse intensity ranges, spacing, orientation, or postprocessing unless
the new model was trained with the same pipeline.

MONAI Model Zoo bundles are maintained by the MONAI Consortium. Review the
downloaded bundle's `docs/README.md`, `docs/data_license.txt` (when present),
and `LICENSE` files for model and data terms.
