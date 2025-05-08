#!/usr/bin/env python3

import os
import sys
import time
import json
import asyncio
import requests
from argparse import ArgumentParser
from configparser import ConfigParser
from prefect import task, flow, get_run_logger
from vos import Client


CADC_DEFAULT_CERTIFICATE = '/Users/she393/.ssl/cadcproxy.pem'
CANFAR_IMAGE_URL = 'https://ws-uv.canfar.net/skaha/v0/image'
CANFAR_SESSION_URL = 'https://ws-uv.canfar.net/skaha/v0/session'
RUNNING_STATES = ['Pending', 'Running', 'Terminating']
COMPLETE_STATES = ['Succeeded']
FAILED_STATES = ['Failed']


def path_to_vos(path):
    """Convert a file path for the CANFAR file system to a VOS project space

    """
    vos_path = path.replace('/arc/', 'arc:')
    return vos_path


def canfar_get_images(type='headless'):
    logger = get_run_logger()
    cert = os.getenv('CADC_CERTIFICATE', CADC_DEFAULT_CERTIFICATE)

    url = f'{CANFAR_IMAGE_URL}?type={type}'
    r = requests.get(url, cert=cert)
    logger.info(r.status_code)
    return json.loads(r.text)


def create_canfar_session(params):
    logger = get_run_logger()
    cert = os.getenv('CADC_CERTIFICATE', CADC_DEFAULT_CERTIFICATE)

    r = requests.post(CANFAR_SESSION_URL, data=params, cert=cert)
    if r.status_code != 200:
        logger.error(r.status_code)
        raise Exception(f'Request failed {r.content}')
    return r.content.decode('utf-8')


def info_canfar_session(id, logs=False):
    logger = get_run_logger()
    cert = os.getenv('CADC_CERTIFICATE', CADC_DEFAULT_CERTIFICATE)

    url = f'{CANFAR_SESSION_URL}/{id}'
    if logs:
        url = f'{url}?view=logs'
    r = requests.get(url, cert=cert)
    if r.status_code != 200:
        logger.error(r.status_code)
        logger.error(r.content)
    return r


@task(task_run_name='{name}')
def job(params, name=None, interval=1, *args, **kwargs):
    """Job wrapper for CANFAR containers

    """
    if not name:
        name = params['name']
    logger = get_run_logger()
    logger.info(name)
    completed = False
    session_id = create_canfar_session(params).strip('\n')
    logger.info(f'Session: {session_id}')
    while not completed:
        res = info_canfar_session(session_id, logs=False)
        status = json.loads(res.text)['status']

        completed = status in COMPLETE_STATES
        failed = status in FAILED_STATES
        if failed:
            logs = info_canfar_session(session_id, logs=True)
            logger.error(logs.content)
            raise Exception(f'Job failed {logs.text}')

        time.sleep(interval)
        logger.info(f'Job {session_id} {status}')

    # Logging to stdout
    res = info_canfar_session(session_id, logs=True)
    logger.info(res.text)
    return


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
    job({
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
    job({
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
    job({
        'name': "miriad-script",
        'image': config['miriad_script']['image'],
        'cores': 1,
        'ram': 4,
        'kind': "headless",
        'cmd': 'python3',
        'args': f"{config['miriad_script']['script']} -wd {workdir} -f {os.path.join(workdir, config['miriad_script']['output_filename'])} -o {os.path.join(workdir, config['miriad_script']['combination_filename'])} -w {config['pipeline']['wallaby_image']} -sd {os.path.join(workdir, config['hi4pi']['filename'])}",
        'env': {}
    })

    # Run miriad preprocessing and combination
    logger.info('Single-dish WALLABY image preprocessing and combination')
    job({
        'name': "miriad",
        'image': config['miriad']['image'],
        'cores': 8,
        'ram': 64,
        'kind': "headless",
        'cmd': '/bin/sh',
        'args': '/arc/projects/WALLABY_test/mw/ngc5044_1/cmd/combinemw.sh',
        'env': {}
    })

    # sofia parameter files
    logger.info('Generating sofia parameter files')
    combined_image = os.path.join(workdir, config['miriad_script']['combination_filename'])
    job({
        'name': "sofia-config-mw",
        'image': config['sofia']['sofia_config_mw_image'],
        'cores': 1,
        'ram': 4,
        'kind': "headless",
        'cmd': 'python3',
        'args': f"/app/update_sofia_config.py --image={combined_image} --input_parameter_file={config['sofia']['parameter_file']} --output_parameter_files={config['pipeline']['workdir']} --input_data={combined_image} --output_directory={workdir} --output_filename=outputs",
        'env': {}
    })

    # SoFiA negative velocity range
    logger.info('SoFiA negative velocity range')
    neg_par = os.path.join(workdir, config['sofia']['negative_parameter_file'])
    job({
        'name': "sofia-neg",
        'image': config['sofia']['sofia_image'],
        'cores': 8,
        'ram': 64,
        'kind': "headless",
        'cmd': 'sofia',
        'args': neg_par,
        'env': {}
    })

    # SoFiA positive velocity range
    logger.info('SoFiA positive velocity range')
    pos_par = os.path.join(workdir, config['sofia']['positive_parameter_file'])
    job({
        'name': "sofia-pos",
        'image': config['sofia']['sofia_image'],
        'cores': 8,
        'ram': 64,
        'kind': "headless",
        'cmd': 'sofia',
        'args': pos_par,
        'env': {}
    })

    # SoFiAX config generation
    logger.info('Updating sofiax config file')
    sofiax_run_config = os.path.join(workdir, config['sofia']['sofiax_config_run'])
    job({
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
    job({
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
