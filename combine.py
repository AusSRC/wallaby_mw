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
    workdir = config['pipeline']['workdir']
    repo_dir = config['pipeline']['repo_dir']
    python_image = config['pipeline']['python_image']
    footprint_a = config['pipeline']['footprint_a']
    footprint_b = config['pipeline']['footprint_b']
    canfar_get_images()
    if not client.isdir(path_to_vos(config['pipeline']['workdir'])):
        client.mkdir(path_to_vos(config['pipeline']['workdir']))

    contsub = config['casda'].getboolean('contsub')
    casda_username = config['casda'].get('username') or os.environ.get('CASDA_USERNAME')
    casda_password = config['casda'].get('password') or os.environ.get('CASDA_PASSWORD')
    casda_keyring_file = config['casda'].get('keyring_file') or None
    assert casda_username, 'CASDA username must be set via config.ini [casda] username or CASDA_USERNAME env var'
    assert casda_password, 'CASDA password must be set via config.ini [casda] password or CASDA_PASSWORD env var'
    casda_env = {'CASDA_USERNAME': casda_username, 'CASDA_PASSWORD': casda_password}
    if casda_keyring_file:
        casda_env['CASDA_KEYRING_FILE'] = casda_keyring_file

    # Download footprint A from CASDA
    logger.info(f'CASDA download {footprint_a}')
    casda_image_a = os.path.join(workdir, config['casda']['filename_footprint_a'])
    if client.isfile(path_to_vos(casda_image_a)):
        logger.info(f'CASDA image {casda_image_a} already exists. Skipping step')
    else:
        job('casda_download_footprint_a', {
            'name': "casda-download-footprint-a",
            'image': python_image,
            'cores': 1,
            'ram': 4,
            'kind': "headless",
            'cmd': 'python3',
            'args': f"{os.path.join(repo_dir, config['casda']['script'])} -s {footprint_a} -o {casda_image_a}" + (' --contsub' if contsub else ''),
            'env': casda_env
        }, interval=sleep_interval)

    # Download footprint B from CASDA
    logger.info(f'CASDA download {footprint_b}')
    casda_image_b = os.path.join(workdir, config['casda']['filename_footprint_b'])
    if client.isfile(path_to_vos(casda_image_b)):
        logger.info(f'CASDA image {casda_image_b} already exists. Skipping step')
    else:
        job('casda_download_footprint_b', {
            'name': "casda-download-footprint-b",
            'image': python_image,
            'cores': 1,
            'ram': 4,
            'kind': "headless",
            'cmd': 'python3',
            'args': f"{os.path.join(repo_dir, config['casda']['script'])} -s {footprint_b} -o {casda_image_b}" + (' --contsub' if contsub else ''),
            'env': casda_env
        }, interval=sleep_interval)

    # Mosaic the two footprint cubes into a single WALLABY image
    logger.info('Mosaicking footprint cubes')
    image = os.path.join(workdir, config['mosaic']['filename'])
    if client.isfile(path_to_vos(image)):
        logger.info(f'Mosaic image {image} already exists. Skipping step')
    else:
        job('mosaic', {
            'name': "mosaic",
            'image': python_image,
            'cores': 4,
            'ram': 16,
            'kind': "headless",
            'cmd': 'python3',
            'args': f"{os.path.join(repo_dir, config['mosaic']['script'])} -a {casda_image_a} -b {casda_image_b} -o {image}",
            'env': {}
        }, interval=sleep_interval)
    assert client.isfile(path_to_vos(image)), f"Mosaicked WALLABY image file does not exist in VO storage space {path_to_vos(image)}"

    # Subfits
    logger.info('Subfits')
    subfits_image = os.path.join(workdir, config['subfits']['filename'])
    if client.isfile(path_to_vos(subfits_image)):
        logger.info(f'Subfits image {subfits_image} already exists. Skipping step')
    else:
        job('subfits', {
            'name': "subfits",
            'image': python_image,
            'cores': 4,
            'ram': 32,
            'kind': "headless",
            'cmd': 'python3',
            'args': f"{os.path.join(repo_dir, config['subfits']['script'])} -i {image} -o {subfits_image} -r",
            'env': {}
        }, interval=sleep_interval)

    # Download HI4PI
    logger.info('HI4PI download')
    hi4pi_image = os.path.join(workdir, config['hi4pi']['filename'])
    vizier_width = float(config['hi4pi']['vizier_query_width'])
    if client.isfile(path_to_vos(hi4pi_image)):
        logger.info(f'HI4PI image {hi4pi_image} already exists. Skipping step')
    else:
        job('hi4pi_download', {
            'name': "hi4pi-download",
            'image': python_image,
            'cores': 1,
            'ram': 4,
            'kind': "headless",
            'cmd': 'python3',
            'args': f"{os.path.join(repo_dir, config['hi4pi']['script'])} -i {image} -o {hi4pi_image} -w {vizier_width}",
            'env': {}
        }, interval=sleep_interval)

    # Generate miriad bash script
    logger.info('Generate miriad bash script')
    miriad_script = os.path.join(workdir, config['miriad_script']['output_filename'])
    if client.isfile(path_to_vos(miriad_script)):
        logger.info('Miriad script exists. Skipping step')
    else:
        job('miraid_script', {
            'name': "miriad-script",
            'image': config['miriad_script']['image'],
            'cores': 1,
            'ram': 4,
            'kind': "headless",
            'cmd': 'python3',
            'args': f"{config['miriad_script']['script']} -wd {workdir} -f {os.path.join(workdir, config['miriad_script']['output_filename'])} -o {os.path.join(workdir, config['miriad_script']['combination_filename'])} -w {subfits_image} -sd {os.path.join(workdir, config['hi4pi']['filename'])} -r {config['miriad_script']['region']} -cw {config['miriad_script']['wallaby_spectral_range']}",
            'env': {}
        }, interval=sleep_interval)

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
    }, interval=sleep_interval)
    return


if __name__ == '__main__':
    main(sys.argv[1:])
