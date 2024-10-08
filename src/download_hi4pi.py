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


logging.basicConfig(level=logging.INFO)


def parse_args(argv):
    parser = ArgumentParser()
    parser.add_argument('-f', '--file', help='Image cube file for reference centre coordinate', required=True)
    parser.add_argument(
        '-r', '--radius',
        help='Search width [deg] from the reference centre coordinate to search for HI4PI file',
        required=False,
        default=20.0
    )
    parser.add_argument('-u', '--url', required=False, default='https://cdsarc.u-strasbg.fr/ftp/J/A+A/594/A116/CUBES/EQ2000/SIN/')
    parser.add_argument('-c', '--catalog', required=False, default='J/A+A/594/A116/cubes_eq')
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
    assert os.path.exists(args.file), f'File does not exist {args.file}'
    with fits.open(args.file) as hdul:
        header = hdul[0].header
        c_ra = header['CRVAL1'] + header['CRPIX1'] * header['CDELT1']
        c_dec = header['CRVAL2'] + header['CRPIX2'] * header['CDELT2']
        logging.info(f'Centre coordinates for image: ({round(c_ra, 2)}, {round(c_dec, 2)})')
    output_dir = os.path.dirname(args.file)
    files = download_hi4pi(c_ra, c_dec, args.radius, args.url, args.catalog, output_dir)
    logging.info(files)
    return files


if __name__ == '__main__':
    argv = sys.argv[1:]
    main(argv)
