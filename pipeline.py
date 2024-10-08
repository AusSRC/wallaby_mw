#!/usr/bin/env python3

'''
Run flow
    1. download hi4pi (block 1)
    2. subfits        (block 1)
    3. velorange      (block 1)
    4. pixel_region   (block 1)
    5. miriad script  (block 2)
    6. source finding (block 3, parallel)
    7. sofiax         (block 4)
'''

import os
import sys
import time
import shutil
import docker
import asyncio
from astropy.io import fits
from argparse import ArgumentParser
from configparser import ConfigParser
from prefect import task, flow, get_run_logger
from src import pixel_region
from src import download_hi4pi
from src import velo_range


MIRIAD_CMD = "$1 $2 $3 $4 $5"


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


@flow
def main(argv):
    # Args and config
    logger = get_run_logger()
    parser = ArgumentParser()
    parser.add_argument('-c', '--config', type=str, required=True, help='Config file')
    args = parser.parse_args(argv)
    assert os.path.exists(args.config), f'Config file does not exist: {args.config}'
    config = ConfigParser()
    config.read(args.config)

    img = config['default']['wallaby_image_file']
    workdir = config['default']['workdir']

    # Check config
    if not os.path.exists(workdir):
        os.mkdir(workdir)
    assert os.path.exists(os.path.join(workdir, img)), f"WALLABY milkyway image file does not exist in working directory: {img}"
    assert os.path.exists(config['miriad']['script']), f"Miriad script does not exist: {config['miriad']['script']}"

    # Open file
    with fits.open(os.path.join(workdir, img)) as hdul:
        hdu = hdul[int(config['default']['hdul'])]
    centre = pixel_region.get_centre(hdu)
    c_ra = centre.ra
    c_dec = centre.dec
    logger.info(f'Centre coordinate: ({c_ra}, {c_dec})')

    # Run processes
    region = pixel_region.main(['--file', img])
    ra_min, dec_min, ra_max, dec_max = region
    region_str = f'\"region=boxes({ra_min},{dec_min},{ra_max},{dec_max})\"'
    logger.info(region_str)

    v1, v2 = velo_range.velocity_range(c_ra.value, c_dec.value)
    logger.info(f'Velocity range: {v1} - {v2}')

    hi4pi_files = download_hi4pi.download_hi4pi(
        c_ra.value,
        c_dec.value,
        float(config['default']['hi4pi_width']),
        download_hi4pi.URL,
        download_hi4pi.CATALOG,
        workdir
    )
    logger.info(f'HI4PI files: {hi4pi_files}')

    exit()

    # Miriad
    wallaby_image = os.path.join(args.miriad_mount, os.path.basename(img))
    hi4pi_image = os.path.join(args.miriad_mount, os.path.basename(args.hi4pi_image))
    output_image = os.path.join(args.miriad_mount, os.path.basename(args.output_image))
    script_filename = os.path.basename(config['miriad']['script'])
    shutil.copy(config['miriad']['script'], os.path.join(workdir, script_filename))
    miriad_script = os.path.join(args.miriad_mount, script_filename)
    miriad_cmd = MIRIAD_CMD.replace('$1', miriad_script)
    miriad_cmd = miriad_cmd.replace('$2', hi4pi_image)
    miriad_cmd = miriad_cmd.replace('$3', wallaby_image)
    miriad_cmd = miriad_cmd.replace('$4', output_image)
    miriad_cmd = miriad_cmd.replace('$5', region_str)
    logger.info(f'Miriad command: {miriad_cmd}')
    volume = {workdir: {'bind': '/data', 'mode': 'rw'}}
    miriad(args.miriad_image, volume, miriad_cmd, logger)

    # Cleanup
    hdul.close()


if __name__ == '__main__':
    argv = sys.argv[1:]
    main(argv)
