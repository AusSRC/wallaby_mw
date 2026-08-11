#!/usr/bin/env python3

"""
Mosaic two WALLABY Milky Way SBID cubes into a single combined image.

Alternative to askapsoft linmos: uses the pure-Python `reproject` package
(reproject_and_coadd) to reproject and combine the two input images onto a
common optimal celestial WCS, plane-by-plane for spectral cubes.
"""

import os
import sys
import logging
from argparse import ArgumentParser

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from reproject import reproject_interp
from reproject.mosaicking import find_optimal_celestial_wcs, reproject_and_coadd


logging.basicConfig(level=logging.INFO)


def mosaic_2d(data1, wcs1, data2, wcs2):
    """Mosaic two 2D images (with celestial WCS) onto a common optimal frame."""
    if data1.ndim != 2 or data2.ndim != 2:
        raise ValueError('mosaic_2d requires two 2D arrays')

    wcs_out, shape_out = find_optimal_celestial_wcs([(data1, wcs1), (data2, wcs2)])
    combined, _ = reproject_and_coadd(
        [(data1, wcs1), (data2, wcs2)],
        wcs_out,
        shape_out=shape_out,
        reproject_function=reproject_interp,
    )
    return combined, wcs_out


def mosaic_cube(data1, wcs1, data2, wcs2):
    """Mosaic two spectral cubes plane-by-plane.

    Accepts 3D (freq, dec, ra) or 4D (freq, stokes, dec, ra) arrays - the
    normal FITS data array ordering (celestial axes last). Every leading
    axis (freq, and stokes if present) is looped over independently; each
    (dec, ra) plane is mosaicked with `mosaic_2d`.

    Assumes both cubes share the same leading axes (i.e. correspond to the
    same field's frequency/stokes grid).
    """
    if data1.ndim not in (3, 4) or data2.ndim not in (3, 4):
        raise ValueError('mosaic_cube requires two 3D or 4D arrays')
    if data1.ndim != data2.ndim:
        raise ValueError(
            f'Dimensionality mismatch: {data1.ndim}D vs {data2.ndim}D'
        )
    if data1.shape[:-2] != data2.shape[:-2]:
        raise ValueError(
            f'Leading axis shape mismatch: {data1.shape[:-2]} vs {data2.shape[:-2]}'
        )

    celestial1 = wcs1.celestial
    celestial2 = wcs2.celestial

    leading_shape = data1.shape[:-2]
    cube_out = None
    wcs_out = None
    for idx in np.ndindex(leading_shape):
        combined, wcs_out = mosaic_2d(data1[idx], celestial1, data2[idx], celestial2)
        if cube_out is None:
            cube_out = np.empty(leading_shape + combined.shape)
        cube_out[idx] = combined

    return cube_out, wcs_out


def main(argv):
    parser = ArgumentParser()
    parser.add_argument('-a', '--image1', type=str, required=True, help='First SBID cube (fits)')
    parser.add_argument('-b', '--image2', type=str, required=True, help='Second SBID cube (fits)')
    parser.add_argument('-o', '--output', type=str, required=True, help='Output mosaicked cube (fits)')
    args = parser.parse_args(argv)

    assert os.path.exists(args.image1), f'Image does not exist: {args.image1}'
    assert os.path.exists(args.image2), f'Image does not exist: {args.image2}'

    with fits.open(args.image1) as hdul1, fits.open(args.image2) as hdul2:
        data1 = hdul1[0].data
        wcs1 = WCS(hdul1[0].header)
        header1 = hdul1[0].header
        data2 = hdul2[0].data
        wcs2 = WCS(hdul2[0].header)

    logging.info(f'Mosaicking {args.image1} and {args.image2}')
    if data1.ndim >= 3:
        mosaic, wcs_out = mosaic_cube(data1, wcs1, data2, wcs2)
    else:
        mosaic, wcs_out = mosaic_2d(data1, wcs1, data2, wcs2)

    header_out = wcs_out.to_header()
    header_out['BUNIT'] = header1.get('BUNIT', '')
    fits.writeto(args.output, mosaic, header=header_out, overwrite=True)
    logging.info(f'Wrote mosaic to {args.output}')


if __name__ == '__main__':
    main(sys.argv[1:])
