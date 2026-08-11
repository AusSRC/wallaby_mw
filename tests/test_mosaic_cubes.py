import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from mosaic_cubes import mosaic_2d, mosaic_cube, patch_celestial_header


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


def make_4d_header():
    header = fits.Header()
    header['NAXIS'] = 4
    header['NAXIS1'] = 10
    header['NAXIS2'] = 10
    header['NAXIS3'] = 1
    header['NAXIS4'] = 5
    header['CTYPE1'] = 'RA---SIN'
    header['CRVAL1'] = 10.0
    header['CRPIX1'] = 5.0
    header['CDELT1'] = -1e-3
    header['CTYPE2'] = 'DEC--SIN'
    header['CRVAL2'] = -20.0
    header['CRPIX2'] = 5.0
    header['CDELT2'] = 1e-3
    header['CTYPE3'] = 'STOKES'
    header['CRVAL3'] = 1.0
    header['CRPIX3'] = 1.0
    header['CDELT3'] = 1.0
    header['CTYPE4'] = 'FREQ'
    header['CRVAL4'] = 1.4e9
    header['CRPIX4'] = 1.0
    header['CDELT4'] = 1000.0
    header['BUNIT'] = 'Jy/beam'
    return header


def test_patch_celestial_header_preserves_spectral_and_stokes_axes():
    header = make_4d_header()
    celestial_wcs = make_wcs(crpix=[7, 8], crval=(11.0, -21.0), cdelt=2e-3)

    patched = patch_celestial_header(header, celestial_wcs, shape_out=(20, 15))

    # Spectral/stokes axes untouched
    assert patched['CTYPE3'] == 'STOKES'
    assert patched['CRVAL3'] == 1.0
    assert patched['CTYPE4'] == 'FREQ'
    assert patched['CRVAL4'] == 1.4e9
    assert patched['CDELT4'] == 1000.0
    assert patched['BUNIT'] == 'Jy/beam'

    # Celestial axes updated to the new mosaic frame/shape
    assert patched['NAXIS2'] == 20
    assert patched['NAXIS1'] == 15
    assert patched['CRVAL1'] == pytest.approx(11.0)
    assert patched['CRVAL2'] == pytest.approx(-21.0)
    assert patched['CRPIX1'] == pytest.approx(7.0)
    assert patched['CRPIX2'] == pytest.approx(8.0)
