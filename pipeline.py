#!/usr/bin/env python3

import os
import sys
import time
import shutil
import docker
from astropy.io import fits
from argparse import ArgumentParser
from prefect import task, flow, get_run_logger
from src.pixel_region import wallaby_pixel_region


MIRIAD_CMD = "$1 $2 $3 $4 $5"


@task
def pixel_region(hdu, size, logger):
    region = wallaby_pixel_region(hdu, size)
    logger.info(region)
    return region


@task
def miriad(image, volume, cmd, logger):
    try:
        client = docker.from_env()
        client.images.pull(image)
        container = client.containers.run(image, cmd, volumes=volume, detach=True)
        container_id = container.id
        logs = None
        while (container.status != 'exited'):
            container = client.containers.get(container_id)
            logs_upd = container.logs()
            if logs_upd != logs:
                logger.info(logs_upd)
                logs = logs_upd
            time.sleep(10)
        logger.info('Miriad completed')
    except Exception as e:
        logger.error(e)
        return
    finally:
        client.containers.prune()
        logger.info('Containers pruned')
    return


def parse_args(argv):
    parser = ArgumentParser()
    parser.add_argument('--directory', type=str, required=True, help='Working directory containing input files')
    parser.add_argument('--wallaby_image', type=str, required=True, default=None, help='Input WALLABY milkyway fits file')
    parser.add_argument('--hi4pi_image', type=str, required=True, default=None, help='Input HI4PI single dish image file')
    parser.add_argument('--output_image', type=str, required=False, default="combined.fits", help='Filename for combined fits image')
    parser.add_argument('--hdu_index', required=False, default=0, help='Default HDU index for WALLABY cube')
    parser.add_argument('--size', required=False, default=320, help='Height and width of the WALLABY milkyway cube [arcmin]')
    parser.add_argument('--miriad_image', type=str, required=False, default='miriad/miriad-dev', help='Docker image for Miriad')
    parser.add_argument('--miriad_script', type=str, required=False, default='src/combinemw.sh', help='Miriad script for combining single dish HI4PI and WALLABY Milkyway observation')
    parser.add_argument('--miriad_mount', type=str, required=False, default='/data', help='Miriad container mount point for directory')
    args = parser.parse_args(argv)
    return args


@flow
def main(argv):
    logger = get_run_logger()
    args = parse_args(argv)

    # Check args
    assert os.path.exists(args.directory), f"Working directory does not exist: {args.directory}"
    assert os.path.exists(os.path.join(args.directory, args.wallaby_image)), f"WALLABY milkyway image file does not exist in working directory: {args.wallaby_image}"
    assert os.path.exists(os.path.join(args.directory, args.hi4pi_image)), f"HI4PI single dish image file does not exist: {args.hi4pi_image}"
    assert os.path.exists(args.miriad_script), f"Miriad script does not exist: {args.miriad_script}"

    # Open file
    with fits.open(os.path.join(args.directory, args.wallaby_image)) as hdul:
        hdu = hdul[args.hdu_index]

    # Run flow
    # 0. download hi4pi
    # 1. subfits
    # 2. velorange
    region = pixel_region(hdu, args.size, logger)
    ra_min, dec_min, ra_max, dec_max = region
    region_str = f'\"region=boxes({ra_min},{dec_min},{ra_max},{dec_max})\"'

    # Miriad
    wallaby_image = os.path.join(args.miriad_mount, os.path.basename(args.wallaby_image))
    hi4pi_image = os.path.join(args.miriad_mount, os.path.basename(args.hi4pi_image))
    output_image = os.path.join(args.miriad_mount, os.path.basename(args.output_image))
    script_filename = os.path.basename(args.miriad_script)
    shutil.copy(args.miriad_script, os.path.join(args.directory, script_filename))
    miriad_script = os.path.join(args.miriad_mount, script_filename)
    miriad_cmd = MIRIAD_CMD.replace('$1', miriad_script)
    miriad_cmd = miriad_cmd.replace('$2', hi4pi_image)
    miriad_cmd = miriad_cmd.replace('$3', wallaby_image)
    miriad_cmd = miriad_cmd.replace('$4', output_image)
    miriad_cmd = miriad_cmd.replace('$5', region_str)
    logger.info(f'Miriad command: {miriad_cmd}')
    volume = {args.directory: {'bind': '/data', 'mode': 'rw'}}
    miriad(args.miriad_image, volume, miriad_cmd, logger)

    # Cleanup
    hdul.close()


if __name__ == '__main__':
    argv = sys.argv[1:]
    main(argv)