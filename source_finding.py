#!/usr/bin/env python3

import os
import sys
import time
import json
import requests
from argparse import ArgumentParser
from configparser import ConfigParser
from prefect import task, flow, get_run_logger
from vos import Client
from common import *


@flow(name='wallaby-mw-source-finding-pipeline')
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

    # sofia parameter files
    logger.info('Generating sofia parameter files')
    combined_image = os.path.join(workdir, config['miriad_script']['combination_filename'])
    job('sofia-config-mw', {
        'name': "sofia-config-mw",
        'image': config['sofia']['sofia_config_mw_image'],
        'cores': 1,
        'ram': 4,
        'kind': "headless",
        'cmd': 'python3',
        'args': f"/app/update_sofia_config.py --image={combined_image} --input_parameter_file={config['sofia']['parameter_file']} --output_parameter_files={config['pipeline']['workdir']} --input_data={combined_image} --output_directory={workdir}",
        'env': {}
    })

    # SoFiA negative velocity range
    logger.info('SoFiA negative velocity range')
    neg_par = os.path.join(workdir, config['sofia']['negative_parameter_file'])
    job('sofia-neg', {
        'name': "sofia-neg",
        'image': config['sofia']['sofia_image'],
        'cores': 4,
        'ram': 32,
        'kind': "headless",
        'cmd': 'sofia',
        'args': neg_par,
        'env': {}
    })

    # SoFiA positive velocity range
    logger.info('SoFiA positive velocity range')
    pos_par = os.path.join(workdir, config['sofia']['positive_parameter_file'])
    job('sofia-pos', {
        'name': "sofia-pos",
        'image': config['sofia']['sofia_image'],
        'cores': 4,
        'ram': 32,
        'kind': "headless",
        'cmd': 'sofia',
        'args': pos_par,
        'env': {}
    })

    # SoFiAX config generation
    logger.info('Updating sofiax config file')
    sofiax_run_config = os.path.join(workdir, config['sofia']['sofiax_config_run'])
    job('sofiax-update', {
        'name': "sofiax-update",
        'image': config['sofia']['update_sofiax_config_image'],
        'cores': 1,
        'ram': 4,
        'kind': "headless",
        'cmd': 'python3',
        'args': f"/app/update_sofiax_config.py --config={config['sofia']['sofiax_config_template']} --output={sofiax_run_config} --run_name={config['sofia']['run_name']}",
        'env': {}
    })

    # Run SoFiAX
    logger.info('Running SoFiAX')
    job('sofiax', {
        'name': "sofiax",
        'image': config['sofia']['sofiax_image'],
        'cores': 2,
        'ram': 16,
        'kind': "headless",
        'cmd': 'python3',
        'args': f"-m sofiax -c {sofiax_run_config} -p {neg_par} {pos_par}",
        'env': {}
    })


if __name__ == '__main__':
    main(sys.argv[1:])
