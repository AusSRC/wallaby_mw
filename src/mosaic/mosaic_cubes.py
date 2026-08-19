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


def _reproject_plane(data1, wcs1, data2, wcs2, wcs_out, shape_out):
    """Coadd one pair of 2D planes onto an already-solved output frame."""
    combined, _ = reproject_and_coadd(
        [(data1, wcs1), (data2, wcs2)],
        wcs_out,
        shape_out=shape_out,
        reproject_function=reproject_interp,
    )
    return combined


def mosaic_2d(data1, wcs1, data2, wcs2):
    """Mosaic two 2D images (with celestial WCS) onto a common optimal frame."""
    if data1.ndim != 2 or data2.ndim != 2:
        raise ValueError('mosaic_2d requires two 2D arrays')

    wcs_out, shape_out = find_optimal_celestial_wcs([(data1, wcs1), (data2, wcs2)])
    combined = _reproject_plane(data1, wcs1, data2, wcs2, wcs_out, shape_out)
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


def _as_primary_header(header, shape, bitpix=-32):
    """Return `header` rebuilt as a valid primary header describing `shape`.

    StreamingHDU only writes the header it is given as the primary HDU when
    that header declares SIMPLE; otherwise it silently prepends an empty
    primary and the data lands in an extension, where the downstream steps
    do not look for it. Rebuilding guarantees the mandatory keywords are
    present and in the order the standard requires.
    """
    source = header.copy()
    structural = ['SIMPLE', 'BITPIX', 'NAXIS', 'XTENSION', 'PCOUNT', 'GCOUNT', 'EXTEND']
    structural += [f'NAXIS{i}' for i in range(1, 10)]
    for key in structural:
        if key in source:
            del source[key]

    out = fits.Header()
    out.set('SIMPLE', True, 'conforms to FITS standard')
    out.set('BITPIX', bitpix, 'array data type')
    out.set('NAXIS', len(shape), 'number of array dimensions')
    for axis, length in enumerate(reversed(shape), start=1):
        out.set(f'NAXIS{axis}', length)
    out.set('EXTEND', True)
    for card in source.cards:
        if card.keyword:
            out.append(card, end=True)
    return out


def mosaic_cube_to_file(data1, wcs1, data2, wcs2, output_file, header):
    """Mosaic two spectral cubes plane by plane, streaming the result to disk.

    A combined WALLABY footprint pair runs to tens of GB - far more than a job
    container has - so planes are written sequentially with StreamingHDU rather
    than accumulated in one array the way `mosaic_cube` does.
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

    # Every plane shares one output frame, so solve it once instead of
    # re-deriving it per plane the way mosaic_2d would.
    wcs_out, shape_out = find_optimal_celestial_wcs(
        [(data1.shape[-2:], celestial1), (data2.shape[-2:], celestial2)]
    )

    leading_shape = data1.shape[:-2]
    out_shape = tuple(leading_shape) + tuple(shape_out)
    total = int(np.prod(leading_shape))

    header_out = _as_primary_header(
        patch_celestial_header(header, wcs_out, shape_out), out_shape
    )

    if os.path.exists(output_file):
        os.remove(output_file)

    # np.ndindex walks the leading axes in C order, which is the order FITS
    # stores planes in, so sequential writes land in the right place.
    stream = fits.StreamingHDU(output_file, header_out)
    try:
        for n, idx in enumerate(np.ndindex(leading_shape), start=1):
            plane = _reproject_plane(
                data1[idx], celestial1, data2[idx], celestial2, wcs_out, shape_out
            )
            stream.write(np.asarray(plane, dtype=np.float32))
            if n % 25 == 0 or n == total:
                logging.info(f'Mosaicked plane {n}/{total}')
    finally:
        stream.close()

    return output_file


def patch_celestial_header(header, celestial_wcs, shape_out):
    """Replace only the celestial (RA/Dec) axis keywords in a FITS header.

    `wcs_out.to_header()` alone only describes 2 axes, so writing it
    directly onto 3D/4D cube data silently drops the spectral/stokes WCS
    (CTYPE3/4, CRVAL3/4, ...). This keeps every other axis from the
    original header untouched and only overwrites axes 1/2 with the new
    mosaic frame, dropping any rotation terms since
    find_optimal_celestial_wcs returns an unrotated frame.
    """
    header = header.copy()
    ny, nx = shape_out
    header['NAXIS1'] = nx
    header['NAXIS2'] = ny
    header['CTYPE1'] = celestial_wcs.wcs.ctype[0]
    header['CTYPE2'] = celestial_wcs.wcs.ctype[1]
    header['CRVAL1'] = celestial_wcs.wcs.crval[0]
    header['CRVAL2'] = celestial_wcs.wcs.crval[1]
    header['CRPIX1'] = celestial_wcs.wcs.crpix[0]
    header['CRPIX2'] = celestial_wcs.wcs.crpix[1]
    header['CDELT1'] = celestial_wcs.wcs.cdelt[0]
    header['CDELT2'] = celestial_wcs.wcs.cdelt[1]
    for key in ('PC1_1', 'PC1_2', 'PC2_1', 'PC2_2', 'CD1_1', 'CD1_2', 'CD2_1', 'CD2_2'):
        if key in header:
            del header[key]
    return header


def main(argv):
    parser = ArgumentParser()
    parser.add_argument('-a', '--image1', type=str, required=True, help='First SBID cube (fits)')
    parser.add_argument('-b', '--image2', type=str, required=True, help='Second SBID cube (fits)')
    parser.add_argument('-o', '--output', type=str, required=True, help='Output mosaicked cube (fits)')
    args = parser.parse_args(argv)

    assert os.path.exists(args.image1), f'Image does not exist: {args.image1}'
    assert os.path.exists(args.image2), f'Image does not exist: {args.image2}'

    # The work stays inside the `with` block: hdul[0].data is memory mapped and
    # is only readable while the file is open.
    with fits.open(args.image1) as hdul1, fits.open(args.image2) as hdul2:
        header1 = hdul1[0].header
        data1 = hdul1[0].data
        wcs1 = WCS(header1)
        data2 = hdul2[0].data
        wcs2 = WCS(hdul2[0].header)

        logging.info(f'Mosaicking {args.image1} and {args.image2}')
        if data1.ndim >= 3:
            mosaic_cube_to_file(data1, wcs1, data2, wcs2, args.output, header1)
        else:
            mosaic, wcs_out = mosaic_2d(data1, wcs1, data2, wcs2)
            header_out = patch_celestial_header(header1, wcs_out, mosaic.shape[-2:])
            fits.writeto(args.output, mosaic, header=header_out, overwrite=True)

    logging.info(f'Wrote mosaic to {args.output}')


if __name__ == '__main__':
    main(sys.argv[1:])
