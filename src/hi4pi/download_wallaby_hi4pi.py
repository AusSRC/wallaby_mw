#!/usr/bin/env python3

"""
Download the HI4PI image corresponding to a WALLABY observation.
Specifically to be used for the generation of WALLABY Milky Way data products
"""

import os
import sys
import time
import wget
import logging
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from astroquery.vizier import Vizier
from argparse import ArgumentParser
from configparser import ConfigParser


logging.basicConfig(level=logging.INFO)

URL = 'https://cdsarc.u-strasbg.fr/ftp/J/A+A/594/A116/CUBES/EQ2000/SIN/'
CATALOG = 'J/A+A/594/A116/cubes_eq'


def get_centre(header):
    w = WCS(header)
    c_ra_pix = header['NAXIS1'] // 2
    c_dec_pix = header['NAXIS2'] // 2
    centre = SkyCoord.from_pixel(c_ra_pix, c_dec_pix, wcs=w)
    return centre


def download_hi4pi(ra, dec, width, url, catalog, output_file):
    centre = SkyCoord(ra=ra*u.deg, dec=dec*u.deg)
    vizier = Vizier(columns=['*'], catalog=catalog)
    res = vizier.query_region(centre, width=width*u.deg)[0]
    mask = res['WCSproj'] == 'SIN'
    sin_res = res[mask]
    if len(sin_res) > 1:
        raise Exception('More than 1 HI4PI image matched. Edge case to handle...')
    logging.info('HI4PI files to download:')
    logging.info(sin_res)
    for f in sin_res:
        filename = f['FileName']
        logging.info(f'Downloading HI4PI image {filename} as {output_file}')
        url = os.path.join(url, filename)
        if os.path.exists(output_file):
            logging.info(f'File {output_file} has already been downloaded. Skipping.')
            continue
        logging.info(f'Downloading file {output_file}')
        wget.download(url, output_file)
    return output_file


def main(argv):
    # Args and config
    parser = ArgumentParser()
    parser.add_argument('-i', '--image', type=str, required=True, help='WALLABY Milky Way fits file path')
    parser.add_argument('-o', '--output', type=str, required=True, help='Output file for the HI4PI image')
    parser.add_argument(
        '-w', '--width', type=float, required=False, default=20.0,
        help='Width (degrees) of region to query for HI4PI images from WALLABY observation centre'
    )
    args = parser.parse_args(argv)

    assert os.path.exists(args.image), f'WALLABY Milky Way fits file does not exist: {args.image}'

    # Open WALLABY observation
    with fits.open(args.image) as hdul:
        header = hdul[0].header
    centre = get_centre(header)
    c_ra = centre.ra
    c_dec = centre.dec
    logging.info(f'Centre coordinate: ({c_ra}, {c_dec})')

    # Download HI4PI images
    download_hi4pi(c_ra.value, c_dec.value, args.width, URL, CATALOG, args.output)
    logging.info('Download complete')


if __name__ == '__main__':
    argv = sys.argv[1:]
    main(argv)
