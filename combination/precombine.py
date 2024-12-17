#!/usr/bin/env python3

"""
Prepare the data required
"""

import os
import sys
import time
import shutil
import asyncio
import logging
from astropy.io import fits
from argparse import ArgumentParser
from configparser import ConfigParser
from src import pixel_region
from src import download_hi4pi
from src import velo_range


logging.basicConfig(level=logging.INFO)


def main(argv):
    # Args and config
    parser = ArgumentParser()
    parser.add_argument('-c', '--config', type=str, required=True, help='Config file')
    parser.add_argument('-i', '--input_image', type=str, required=False, help='Input image', default=None)
    parser.add_argument('-o', '--combined_image', type=str, required=False, help='Output combined image filename', default=None)
    parser.add_argument('-s', '--output_filename', type=str, required=False, help='Output miriad script filename', default=None)
    args = parser.parse_args(argv)
    assert os.path.exists(args.config), f'Config file does not exist: {args.config}'
    config = ConfigParser()
    config.read(args.config)
    workdir = config['default']['workdir']

    # Choose argument over config for certain parameters
    if args.input_image is not None:
        img = args.input_image
    else:
        img = config['default']['wallaby_image_file']
    img_file = os.path.join(workdir, img)

    if args.output_filename is not None:
        output_filename = args.output_filename
    else:
        output_filename = config['miriad']['output_script']

    if args.combined_image is not None:
        combined_image_filename = args.combined_image
    else:
        combined_image_filename = os.path.basename(config['default']['output_image'])

    # Check config
    assert os.path.exists(workdir), f'Working directory does not exist: {workdir}'
    assert os.path.exists(img_file), f"WALLABY milkyway image file does not exist in working directory: {img_file}"
    assert os.path.exists(config['miriad']['template']), f"Miriad template does not exist: {config['miriad']['template']}"

    # Open file
    with fits.open(img_file) as hdul:
        hdu = hdul[0]
    centre = pixel_region.get_centre(hdu)
    c_ra = centre.ra
    c_dec = centre.dec
    logging.info(f'Centre coordinate: ({c_ra}, {c_dec})')

    # Run processes
    region = pixel_region.main(['--file', img_file])
    ra_min, dec_min, ra_max, dec_max = region
    region_str = f'\"region=boxes({ra_min},{dec_min},{ra_max},{dec_max})\"'
    logging.info(region_str)

    v1, v2 = velo_range.velocity_range(c_ra.value, c_dec.value)
    logging.info(f'Velocity range: {v1} - {v2}')

    hi4pi_files = download_hi4pi.download_hi4pi(
        c_ra.value,
        c_dec.value,
        float(config['default']['hi4pi_width']),
        download_hi4pi.URL,
        download_hi4pi.CATALOG,
        workdir
    )
    logging.info(f'HI4PI files ({len(hi4pi_files)}): {hi4pi_files}')
    if len(hi4pi_files) > 1:
        logging.warning('More than 1 corresponding HI4PI image found. Will create multiple miriad scripts.')
    logging.info('Completed. Starting miriad')

    # Miriad
    for idx, hi4pi_f in enumerate(hi4pi_files):
        wallaby_image = os.path.join(config['miriad']['mount'], os.path.basename(img_file))
        hi4pi_image = os.path.join(config['miriad']['mount'], os.path.basename(hi4pi_f))
        output_image = os.path.join(config['miriad']['mount'], combined_image_filename)
        write_file = os.path.join(workdir, output_filename)
        if len(hi4pi_files) > 1:
            write_file = os.path.join(workdir, f"{idx}.{output_filename}")

        # Read and replace in miriad template
        with open(config['miriad']['template']) as f:
            content = f.read()
            content = content.replace('$1', hi4pi_image)
            content = content.replace('$2', wallaby_image)
            content = content.replace('$3', output_image)
            content = content.replace('$4', region_str)

        logging.info(f'Writing miriad script to file {write_file}')
        with open(write_file, 'w') as f:
            f.write(content)


if __name__ == '__main__':
    argv = sys.argv[1:]
    main(argv)
