#!/usr/bin/env python3

import os
import sys
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
import astropy.units as u
from argparse import ArgumentParser


def get_centre(hdu):
    w = WCS(hdu.header)
    c_ra_pix = hdu.header['NAXIS1'] // 2
    c_dec_pix = hdu.header['NAXIS2'] // 2
    centre = SkyCoord.from_pixel(c_ra_pix, c_dec_pix, wcs=w)
    return centre


def wallaby_pixel_region(hdu, size):
    """Define the region of the WALLABY cube extract from imsub for miriad single dish combination

    """
    w = WCS(hdu.header)
    centre = get_centre(hdu)
    dr = size // 2 * u.arcmin
    ra_max, dec_max = SkyCoord(ra=centre.ra - dr, dec=centre.dec + dr).to_pixel(wcs=w)
    ra_min, dec_min = SkyCoord(ra=centre.ra + dr, dec=centre.dec - dr).to_pixel(wcs=w)
    return int(ra_min), int(dec_min), int(ra_max), int(dec_max)


def parse_args(argv):
    parser = ArgumentParser()
    parser.add_argument('--file', type=str, required=True, default=None, help='Input WALLABY milkyway fits file')
    parser.add_argument('--size', required=False, default=320, help='Height and width of the WALLABY milkyway cube [arcmin]')
    parser.add_argument('--hdu_index', required=False, default=0, help='Default HDU index for cube data')
    args = parser.parse_args(argv)
    return args


def main(argv):
    args = parse_args(argv)
    assert os.path.exists(args.file), f"Provided WALLABY milkyway fits file {args.file} does not exist"
    with fits.open(args.file) as hdul:
        region = wallaby_pixel_region(hdu=hdul[args.hdu_index], size=args.size)
    return region


if __name__ == '__main__':
    main(sys.argv[1:])
