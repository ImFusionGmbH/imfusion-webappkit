import numpy as np
import imfusion


@imfusion.algorithm.register(display_name="My Add Noise")
class AddNoiseAlgorithm:
    """
    Algorithm that adds random noise to an image by setting random voxels to 0.
    """

    imageset = imfusion.algorithm.Input(imfusion.SharedImageSet)
    num_voxels = imfusion.algorithm.ParamInt(
        "Number of noise voxels",
        default=100000,
        min=1,
        max=10000000,
    )

    def __call__(self) -> imfusion.SharedImageSet:
        """Add noise by setting random voxels to 0."""
        self.imageset_out = imfusion.SharedImageSet()

        for image in self.imageset:
            arr = np.array(image, copy=True)
            total_voxels = arr.size
            num_noise_pixels = min(self.num_voxels, total_voxels)
            indices = np.random.randint(0, total_voxels, size=num_noise_pixels)
            arr.flat[indices] = 0

            image_out = imfusion.SharedImage(arr)
            image_out.image_to_world_matrix = image.image_to_world_matrix
            image_out.spacing = image.spacing
            self.imageset_out.add(image_out)

        return self.imageset_out
