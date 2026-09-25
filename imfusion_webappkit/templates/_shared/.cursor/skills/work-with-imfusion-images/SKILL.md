---
name: work-with-imfusion-images
description: Process ImFusion image arrays without losing physical intensities, geometry, modality, or coordinate conventions. Use when reading pixels, creating derived images or labels, transforming coordinates, resampling, or integrating an imaging model in a WebAppKit app.
---

# Work with ImFusion images

## Pixel values and layout

- `np.asarray(image)` accesses storage values. Use `image.numpy()` when
  algorithms require physical values such as CT Hounsfield units because it
  applies the image shift and scale.
- Python image arrays use `(Z, Y, X, C)`. Image spacing is ordered `(X, Y, Z)`;
  do not apply spacing to array axes without reversing the spatial order.
- Validate dimensionality, channels, and value domain at algorithm boundaries.
  Do not silently squeeze or guess an external model's expected layout.

## Derived images

When output remains on the source voxel grid:

```python
output = imfusion.SharedImage(output_array)
output.spacing = source.spacing
output.image_to_world_matrix = source.image_to_world_matrix
```

Set `SharedImageSet.modality = imfusion.Data.Modality.LABEL` for segmentation
labels. If the grid changes, calculate geometry through an explicit resampling
or affine transform instead of copying source geometry.

## Coordinates

- Distinguish pixel indices, image coordinates in millimeters, and world
  coordinates. ImFusion image coordinates are centered on the image.
- Use `pixel_to_world_matrix` for pixel-to-world conversion. Do not insert
  spacing into `image_to_world_matrix`; spacing is represented separately.
- ImFusion patient/world coordinates use DICOM LPS. Libraries based on nibabel
  commonly use RAS; convert affines with
  `diag(-1, -1, 1, 1) @ pixel_to_world_matrix`.
- For meshes, points, tracking, or registration, verify whether an API expects
  a matrix to world or from world before composing transforms.

## Verification

Test with non-unit spacing, a non-identity world matrix, and asymmetric array
dimensions. Verify both voxel correspondence and world alignment after every
axis reorder, resampling, or model round trip.
