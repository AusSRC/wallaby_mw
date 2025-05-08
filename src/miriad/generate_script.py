#!/usr/bin/env python3

"""
Code to help generate a bash script for running within the miriad container.
"""

import os
import sys
import logging
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
import astropy.units as u
from argparse import ArgumentParser


logging.basicConfig(level=logging.INFO)


def get_centre(header):
    w = WCS(header)
    c_ra_pix = header['NAXIS1'] // 2
    c_dec_pix = header['NAXIS2'] // 2
    centre = SkyCoord.from_pixel(c_ra_pix, c_dec_pix, wcs=w)
    return centre


def wallaby_pixel_region(header, size):
    """Define the region of the WALLABY cube extract from imsub for miriad single dish combination

    """
    w = WCS(header)
    centre = get_centre(header)
    dr = size // 2 * u.arcmin
    ra_max, dec_max = SkyCoord(ra=centre.ra - dr, dec=centre.dec + dr).to_pixel(wcs=w)
    ra_min, dec_min = SkyCoord(ra=centre.ra + dr, dec=centre.dec - dr).to_pixel(wcs=w)
    return int(ra_min), int(dec_min), int(ra_max), int(dec_max)


def main(argv):
    parser = ArgumentParser(argv)
    parser.add_argument('-wd', '--workdir', required=True, help='Working directory where all miriad files are stored')
    parser.add_argument('-f', '--filename', required=True, help='Output miriad bash script filename and path')
    parser.add_argument('-o', '--output', required=True, help='Output single-dish WALLABY combined fits filename')
    parser.add_argument('-w', '--wallaby', required=True, help='WALLABY image file')
    parser.add_argument('-sd', '--singledish', required=True, help='HI4PI single dish image file')
    parser.add_argument(
        '-c',
        '--imsub_channels',
        help='[Optional] Argument for channel range to keep in the HI4PI observation',
        required=False,
        default='42,426'
    )
    parser.add_argument(
        '-uv',
        '--immerge_uvrange',
        help='[Optional] Argument for immerge',
        required=False,
        default='25,35,meters'
    )
    parser.add_argument(
        '-sz',
        '--size',
        help='[Optional] Width/height of WALLABY Milky Way spatial subcube [arcmin]',
        required=False,
        type=int,
        default=320
    )
    args = parser.parse_args(argv)

    # Assert exists
    workdir = args.workdir
    assert os.path.exists(workdir), f'Working directory {workdir} does not exists'
    assert os.path.exists(args.wallaby), f'WALLABY image {args.wallaby} does not exists'
    assert os.path.exists(args.singledish), f'Single dish HI4PI image {args.singledish} does not exists'
    if os.path.exists(args.filename):
        logging.warning(f'Miriad script already exists at {args.filename}. Overwriting.')
    if os.path.exists(args.output):
        logging.error(f'Output single-dish WALLABY combination already produced: {args.output}')

    # Open fits file
    logging.info('Reading WALLABY fits header for spatial combination region')
    with fits.open(args.wallaby) as hdul:
        header = hdul[0].header
        region = wallaby_pixel_region(header, args.size)
        logging.info(f'WALLABY spatial region: {region}')

    region_str = str(region).strip('()').replace(' ', '')

    # Generate bash script
    logging.info(f'Creating miriad script: {args.filename}')
    with open(args.filename, 'w') as f:
        f.writelines('#!/bin/csh\n')
        f.writelines('miriad\n')

        # Reading files
        f.writelines(f'fits in={args.singledish} op=xyin out={os.path.join(workdir, "sd")}\n')
        f.writelines(f'fits in={args.wallaby} op=xyin out={os.path.join(workdir, "wallaby")}\n')

        # Preprocess single dish data
        f.writelines(f'hanning in={os.path.join(workdir, "sd")} out={os.path.join(workdir, "sd_hann")}\n')
        f.writelines(f'imsub in={os.path.join(workdir, "sd_hann")} out={os.path.join(workdir, "sd_imsub_incr")}\n')
        f.writelines(f'imsub in={os.path.join(workdir, "sd_imsub_incr")} out={os.path.join(workdir, "sd_imsub")} "region=images({args.imsub_channels})"\n')

        # Preprocess WALLABY Milky Way observation
        f.writelines(f'velsw in={os.path.join(workdir, "wallaby")} axis=freq options=altspc\n')
        f.writelines(f'velsw in={os.path.join(workdir, "wallaby")} axis=freq,lsrk\n')
        f.writelines(f'imsub in={os.path.join(workdir, "wallaby")} out={os.path.join(workdir, "wallaby_trim")} "region=boxes({region_str})({"141,394"})"\n')

        # Regrid and merge
        f.writelines(f'regrid in={os.path.join(workdir, "sd_imsub")} tin={os.path.join(workdir, "wallaby_trim")} out={os.path.join(workdir, "sd_regrid")}\n')
        f.writelines(f'immerge in={os.path.join(workdir, "wallaby_trim")},{os.path.join(workdir, "sd_regrid")} out={os.path.join(workdir, "combined")} uvrange=25,35,meters options=notaper\n')
        f.writelines(f'fits in={os.path.join(workdir, "combined")} op=xyout out={args.output}\n')
        f.writelines('quit\n')

    logging.info('Changing permissons (+x)')
    os.chmod(args.filename, 0o770)

    logging.info('Complete')


if __name__ == '__main__':
    argv = sys.argv[1:]
    main(argv)
