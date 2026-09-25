---
name: integrate-monai-model
description: Adapt a MONAI or PyTorch medical-imaging model to the generated WebAppKit inference workflow. Use when replacing the starter model, changing preprocessing or postprocessing, handling model tensor geometry, or validating inference output.
---

# Integrate a MONAI model

1. Inspect the model's training or reference inference pipeline. Reproduce its
   intensity mapping, orientation, spacing, crop strategy, activation, and
   label conversion exactly; do not infer them from the architecture.
2. Keep heavyweight MONAI and torch imports inside model-loading or inference
   functions so importing `app.py` remains lightweight. Cache the loaded model
   by device and use `eval()` with inference mode.
3. Convert ImFusion `(Z, Y, X, C)` arrays to the exact model tensor layout.
   Convert the ImFusion LPS pixel-to-world affine when the model pipeline uses
   nibabel/RAS. Use the `work-with-imfusion-images` skill for these conventions.
4. Apply postprocessing as the spatial inverse of preprocessing and resample
   predictions to the original input grid before creating output data.
5. Check output rank, channels, shape, dtype, and label semantics explicitly.
   Preserve source spacing and world geometry only after confirming that the
   prediction is on the source voxel grid.
6. Keep model name, version, checkpoint loading, and transforms together.
   Changing a bundle requires reviewing all of them.

Validate against the model's reference Python inference on a representative
volume. Also test an asymmetric synthetic volume with non-unit spacing and a
non-identity affine to catch axis and LPS/RAS errors. Treat generated output as
non-diagnostic unless the complete model and application have been validated
for the intended clinical use.
