"""
Test the mask-extracting utilities.
"""
import types

from nose.tools import assert_true, assert_false, assert_equal, assert_raises

import numpy as np
from nibabel import Nifti1Image
from numpy.testing import assert_array_equal

from ..masking import apply_mask, compute_epi_mask, unmask, intersect_masks

def test_mask():
    mean_image = np.ones((9, 9))
    mean_image[3:-3, 3:-3] = 10
    mean_image[5, 5] = 100
    mask1 = compute_epi_mask(mean_image, opening=False)
    mask2 = compute_epi_mask(mean_image, exclude_zeros=True,
                             opening=False)
    # With an array with no zeros, exclude_zeros should not make
    # any difference
    yield np.testing.assert_array_equal, mask1, mask2
    # Check that padding with zeros does not change the extracted mask
    mean_image2 = np.zeros((30, 30))
    mean_image2[:9, :9] = mean_image
    mask3 = compute_epi_mask(mean_image2, exclude_zeros=True,
                             opening=False)
    yield np.testing.assert_array_equal, mask1, mask3[:9, :9]
    # However, without exclude_zeros, it does
    mask3 = compute_epi_mask(mean_image2, opening=False)
    yield assert_false, np.allclose(mask1, mask3[:9, :9])


def test_apply_mask():
    """ Test smoothing of timeseries extraction
    """
    # A delta in 3D
    data = np.zeros((40, 40, 40, 2))
    data[20, 20, 20] = 1
    mask = np.ones((40, 40, 40))
    for affine in (np.eye(4), np.diag((1, 1, -1, 1)),
                   np.diag((.5, 1, .5, 1))):
        series = apply_mask(Nifti1Image(data, affine),
                            Nifti1Image(mask, affine), smooth=9)
        series = np.reshape(series[0, :], (40, 40, 40))
        vmax = series.max()
        # We are expecting a full-width at half maximum of
        # 9mm/voxel_size:
        above_half_max = series > .5 * vmax
        for axis in (0, 1, 2):
            proj = np.any(np.any(np.rollaxis(above_half_max,
                          axis=axis), axis=-1), axis=-1)
            np.testing.assert_equal(proj.sum(),
                                    9 / np.abs(affine[axis, axis]))

    # Check that NaNs in the data do not propagate
    data[10, 10, 10] = np.NaN
    series = apply_mask(Nifti1Image(data, affine),
                        Nifti1Image(mask, affine), smooth=9)
    assert_true(np.all(np.isfinite(series)))


def test_unmask():
    """ Test the unmask_optimized function
    """
    # A delta in 3D
    shape = (10, 20, 30, 40)
    generator = np.random.RandomState(42)
    data4D = generator.rand(*shape)
    data3D = data4D[..., 0]
    mask = generator.randint(2, size=shape[:3]).astype(np.bool)

    masked4D = data4D[mask, :].T
    unmasked4D = data4D.copy()
    unmasked4D[-mask, :] = 0
    masked3D = data3D[mask]
    unmasked3D = data3D.copy()
    unmasked3D[-mask] = 0

    # 4D Test
    t = unmask(masked4D, mask)
    assert_equal(t.ndim, 4)
    assert_array_equal(t, unmasked4D)
    t = unmask([masked4D], mask)
    assert_true(isinstance(t, types.ListType))
    assert_equal(t[0].ndim, 4)
    assert_array_equal(t[0], unmasked4D)

    # 3D Test
    t = unmask(masked3D, mask)
    assert_equal(t.ndim, 3)
    assert_array_equal(t, unmasked3D)
    t = unmask([masked3D], mask)
    assert_true(isinstance(t, types.ListType))
    assert_equal(t[0].ndim, 3)
    assert_array_equal(t[0], unmasked3D)

    # 5D test
    shape5D = (10, 20, 30, 40, 41)
    data5D = generator.rand(*shape5D)
    mask = generator.randint(2, size=shape5D[:-1]).astype(np.bool)

    masked5D = data5D[mask, :].T
    unmasked5D = data5D.copy()
    unmasked5D[-mask, :] = 0

    t = unmask(masked5D, mask)
    assert_equal(t.ndim, len(shape5D))
    assert_array_equal(t, unmasked5D)
    t = unmask([masked5D], mask)
    assert_true(isinstance(t, types.ListType))
    assert_equal(t[0].ndim, len(shape5D))
    assert_array_equal(t[0], unmasked5D)

    # Error test
    dummy = generator.rand(500)
    assert_raises(ValueError, unmask, dummy, mask)
    assert_raises(ValueError, unmask, [dummy], mask)


def test_intersect_masks():
    """ Test the intersect_masks function
    """

    # Create dummy masks
    mask_a = np.zeros((4, 4), dtype=np.bool)
    mask_a[2:4, 2:4] = 1

    # +---+---+---+---+
    # |   |   |   |   |
    # +---+---+---+---+
    # |   |   |   |   |
    # +---+---+---+---+
    # |   |   | X | X |
    # +---+---+---+---+
    # |   |   | X | X |
    # +---+---+---+---+

    mask_b = np.zeros((4, 4), dtype=np.bool)
    mask_b[1:3, 1:3] = 1

    # +---+---+---+---+
    # |   |   |   |   |
    # +---+---+---+---+
    # |   | X | X |   |
    # +---+---+---+---+
    # |   | X | X |   |
    # +---+---+---+---+
    # |   |   |   |   |
    # +---+---+---+---+

    mask_c = np.zeros((4, 4), dtype=np.bool)
    mask_c[:, 2] = 1
    mask_c[0, 0] = 1

    # +---+---+---+---+
    # | X |   | X |   |
    # +---+---+---+---+
    # |   |   | X |   |
    # +---+---+---+---+
    # |   |   | X |   |
    # +---+---+---+---+
    # |   |   | X |   |
    # +---+---+---+---+

    mask_ab = np.zeros((4, 4), dtype=np.bool)
    mask_ab[2, 2] = 1
    mask_ab_ = intersect_masks([mask_a, mask_b], threshold=1.)
    assert_array_equal(mask_ab, mask_ab_)

    mask_abc = mask_a + mask_b + mask_c
    mask_abc_ = intersect_masks([mask_a, mask_b, mask_c], threshold=0.,
                                connected=False)
    assert_array_equal(mask_abc, mask_abc_)

    mask_abc[0, 0] = 0
    mask_abc_ = intersect_masks([mask_a, mask_b, mask_c], threshold=0.)
    assert_array_equal(mask_abc, mask_abc_)

    mask_abc = mask_ab
    mask_abc_ = intersect_masks([mask_a, mask_b, mask_c], threshold=1.)
    assert_array_equal(mask_abc, mask_abc_)

    mask_abc[1, 2] = 1
    mask_abc[3, 2] = 1
    mask_abc_ = intersect_masks([mask_a, mask_b, mask_c])
    assert_array_equal(mask_abc, mask_abc_)
