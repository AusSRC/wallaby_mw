#!/usr/bin/env python3

import os
import sys
from argparse import ArgumentParser
from configparser import ConfigParser
from prefect import task, flow, get_run_logger
from vos import Client
from common import *



@flow(name='wallaby-mw-pipeline')
def main(argv):
    logger = get_run_logger()
    client = Client()

    # Read config
    logger.info('Parsing pipeline config')
    parser = ArgumentParser()
    parser.add_argument('-c', '--config', type=str, required=True, help='Pipeline configuration file')
    args = parser.parse_args(argv)
    assert os.path.exists(args.config), f'Config file does not exist: {args.config}'
    config = ConfigParser()
    config.read(args.config)
    sleep_interval = float(config['pipeline']['sleep_interval'])

    # Assert CANFAR paths exist
    image = config['pipeline']['wallaby_image']
    workdir = config['pipeline']['workdir']
    canfar_get_images()
    if not client.isdir(path_to_vos(config['pipeline']['workdir'])):
        client.mkdir(path_to_vos(config['pipeline']['workdir']))
    assert client.isfile(path_to_vos(image)), f"WALLABY image file does not exist in VO storage space {path_to_vos(image)}"

    # Subfits
    logger.info('Subfits')
    subfits_image = os.path.join(workdir, config['subfits']['filename'])
    try:
        client.isfile(path_to_vos(subfits_image))
        logger.info(f'Subfits image {subfits_image} already exists. Skipping step')
    except:
        job('subfits', {
            'name': "subfits",
            'image': config['subfits']['image'],
            'cores': 4,
            'ram': 32,
            'kind': "headless",
            'cmd': 'python3',
            'args': f"{config['subfits']['script']} -i {image} -o {subfits_image} -r",
            'env': {}
        })

    # Download HI4PI
    logger.info('HI4PI download')
    hi4pi_image = os.path.join(workdir, config['hi4pi']['filename'])
    vizier_width = float(config['hi4pi']['vizier_query_width'])
    try:
        client.isfile(path_to_vos(hi4pi_image))
        logger.info(f'HI4PI image {hi4pi_image} already exists. Skipping step')
    except:
        job('hi4pi_download', {
            'name': "hi4pi-download",
            'image': config['hi4pi']['image'],
            'cores': 1,
            'ram': 4,
            'kind': "headless",
            'cmd': 'python3',
            'args': f"{config['hi4pi']['script']} -i {image} -o {hi4pi_image} -w {vizier_width}",
            'env': {}
        })

    # Generate miriad bash script
    logger.info('Generate miriad bash script')
    miriad_script = os.path.join(workdir, config['miriad_script']['output_filename'])
    try:
        client.isfile(path_to_vos(miriad_script))
        logger.info('Miriad script exists. Skipping step')
    except:
        job('miraid_script', {
            'name': "miriad-script",
            'image': config['miriad_script']['image'],
            'cores': 1,
            'ram': 4,
            'kind': "headless",
            'cmd': 'python3',
            'args': f"{config['miriad_script']['script']} -wd {workdir} -f {os.path.join(workdir, config['miriad_script']['output_filename'])} -o {os.path.join(workdir, config['miriad_script']['combination_filename'])} -w {subfits_image} -sd {os.path.join(workdir, config['hi4pi']['filename'])} -r {config['miriad_script']['region']}",
            'env': {}
        })

    # Run miriad preprocessing and combination
    logger.info('Single-dish WALLABY image preprocessing and combination')
    job('miriad', {
        'name': "miriad",
        'image': config['miriad']['image'],
        'cores': 4,
        'ram': 32,
        'kind': "headless",
        'cmd': '/bin/sh',
        'args': miriad_script,
        'env': {}
    })
    return


if __name__ == '__main__':
    main(sys.argv[1:])
