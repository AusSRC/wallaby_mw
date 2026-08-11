import numpy as np
import pytest
from astropy.wcs import WCS

from mosaic_cubes import mosaic_2d, mosaic_cube


def make_wcs(crpix, crval=(50.0, -30.0), cdelt=1e-3):
    w = WCS(naxis=2)
    w.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    w.wcs.crval = crval
    w.wcs.crpix = crpix
    w.wcs.cdelt = [-cdelt, cdelt]
    return w


def test_mosaic_2d_overlap_is_averaged():
    # Two 10x10 tiles offset by 5 pixels in x, same value fill, overlapping half.
    shape = (10, 10)
    data1 = np.full(shape, 1.0)
    data2 = np.full(shape, 3.0)
    wcs1 = make_wcs(crpix=[5, 5])
    wcs2 = make_wcs(crpix=[0, 5])  # shifted 5 pixels to the left in reference frame

    combined, wcs_out = mosaic_2d(data1, wcs1, data2, wcs2)

    # Combined footprint must be big enough to hold both non-overlapping halves
    assert combined.shape[0] >= shape[0]
    assert combined.shape[1] >= shape[0] + 5

    # Somewhere in the mosaic the overlap of tile1 (=1) and tile2 (=3) should
    # average to ~2, and somewhere only tile2's value (~3) should survive
    # untouched since tile1 doesn't cover it.
    assert np.any(np.isclose(combined, 2.0, atol=0.05))
    assert np.any(np.isclose(combined, 3.0, atol=0.05))


def test_mosaic_2d_raises_on_mismatched_shapes():
    wcs1 = make_wcs(crpix=[5, 5])
    wcs2 = make_wcs(crpix=[5, 5])
    with pytest.raises(ValueError):
        mosaic_2d(np.zeros((10, 10)), wcs1, np.zeros((3, 3, 3)), wcs2)


def test_mosaic_cube_combines_each_channel_independently():
    n_chan = 3
    shape2d = (10, 10)
    wcs1 = make_wcs(crpix=[5, 5])
    wcs2 = make_wcs(crpix=[0, 5])

    data1 = np.stack([np.full(shape2d, 1.0 + c) for c in range(n_chan)])
    data2 = np.stack([np.full(shape2d, 3.0 + c) for c in range(n_chan)])

    cube, wcs_out = mosaic_cube(data1, wcs1, data2, wcs2)

    assert cube.shape[0] == n_chan
    # Channel 0 should reflect the same base values as the 2D case (1 and 3)
    assert np.any(np.isclose(cube[0], 2.0, atol=0.05))
    # Channel 2 base values are 3 and 5, overlap should average to ~4
    assert np.any(np.isclose(cube[2], 4.0, atol=0.05))


def test_mosaic_cube_raises_on_channel_count_mismatch():
    wcs1 = make_wcs(crpix=[5, 5])
    wcs2 = make_wcs(crpix=[0, 5])
    data1 = np.zeros((3, 10, 10))
    data2 = np.zeros((2, 10, 10))
    with pytest.raises(ValueError):
        mosaic_cube(data1, wcs1, data2, wcs2)


def test_mosaic_cube_accepts_4d_freq_stokes_dec_ra_cubes():
    n_freq, n_stokes = 2, 1
    shape2d = (10, 10)
    wcs1 = make_wcs(crpix=[5, 5])
    wcs2 = make_wcs(crpix=[0, 5])

    data1 = np.zeros((n_freq, n_stokes, *shape2d))
    data2 = np.zeros((n_freq, n_stokes, *shape2d))
    data1[0, 0] = 1.0
    data2[0, 0] = 3.0
    data1[1, 0] = 2.0
    data2[1, 0] = 4.0

    cube, wcs_out = mosaic_cube(data1, wcs1, data2, wcs2)

    assert cube.shape[:2] == (n_freq, n_stokes)
    assert np.any(np.isclose(cube[0, 0], 2.0, atol=0.05))
    assert np.any(np.isclose(cube[1, 0], 3.0, atol=0.05))


def test_mosaic_cube_raises_on_leading_shape_mismatch_for_4d():
    wcs1 = make_wcs(crpix=[5, 5])
    wcs2 = make_wcs(crpix=[0, 5])
    data1 = np.zeros((2, 1, 10, 10))
    data2 = np.zeros((2, 2, 10, 10))
    with pytest.raises(ValueError):
        mosaic_cube(data1, wcs1, data2, wcs2)
