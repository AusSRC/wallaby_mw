#!/usr/bin/env python3

import os
import sys
import wget
import logging
from argparse import ArgumentParser
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astroquery.vizier import Vizier


URL = 'https://cdsarc.u-strasbg.fr/ftp/J/A+A/594/A116/CUBES/EQ2000/SIN/'
CATALOG = 'J/A+A/594/A116/cubes_eq'


def parse_args(argv):
    parser = ArgumentParser()
    parser.add_argument('--ra', help='RA centre coordinate', required=True)
    parser.add_argument('--dec', help='Declination centre coordinate', required=True)
    parser.add_argument('-r', '--radius', required=False, default=20.0)
    args = parser.parse_args(argv)
    return args


def download_hi4pi(ra, dec, width, url, catalog, output_dir='./'):
    files = []
    centre = SkyCoord(ra=ra*u.deg, dec=dec*u.deg)
    vizier = Vizier(columns=['*'], catalog=catalog)
    res = vizier.query_region(centre, width=width*u.deg)[0]
    mask = res['WCSproj'] == 'SIN'
    sin_res = res[mask]
    logging.info('HI4PI download files:')
    logging.info(sin_res)
    for f in sin_res:
        filename = f['FileName']
        url = os.path.join(url, filename)
        output_file = os.path.join(output_dir, filename)
        files.append(output_file)
        if os.path.exists(output_file):
            logging.info(f'File {output_file} has already been downloaded. Skipping.')
            continue
        logging.info(f'Downloading file {filename}')
        wget.download(url, output_file)
    return files


def main(argv):
    args = parse_args(argv)
    logging.info(f'Centre coordinates for image: ({round(args.ra, 2)}, {round(args.dec, 2)})')
    output_dir = os.path.dirname(args.file)
    files = download_hi4pi(args.ra, args.dec, args.radius, URL, CATALOG, output_dir)
    logging.info(files)
    return files


if __name__ == '__main__':
    argv = sys.argv[1:]
    logging.debug(f'Args: {argv}')
    main(argv)
