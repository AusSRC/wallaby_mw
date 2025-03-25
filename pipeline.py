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
def job(name, params, interval=1, *args, **kwargs):
    """Job wrapper for CANFAR containers

    """
    logger = get_run_logger()
    logger.info(name)
    completed = False
    session_id = create_canfar_session(params)
    logger.info(f'Session: {session_id}')
    while not completed:
        res = info_canfar_session(session_id, logs=False)
        status = json.loads(res.text)['status']
        completed = status in COMPLETE_STATES
        failed = status in FAILED_STATES
        if failed:
            res = info_canfar_session(session_id, logs=True)
            raise Exception(f'Job failed {res.text}')

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
    canfar_get_images()
    if not client.isdir(path_to_vos(config['pipeline']['workdir'])):
        client.mkdir(path_to_vos(config['pipeline']['workdir']))
    assert client.isfile(path_to_vos(image)), f"WALLABY image file does not exist in VO storage space {path_to_vos(image)}"

    # Subfits
    logger.info('Subfits')
    subfits_image = os.path.join(config['pipeline']['workdir'], config['subfits']['filename'])
    params = {
        'name': "subfits",
        'image': config['subfits']['image'],
        'cores': 4,
        'ram': 32,
        'kind': "headless",
        'cmd': 'python3',
        'args': f"{config['subfits']['script']} -i {image} -o {subfits_image} -r",
        'env': {}
    }
    # job(params['name'], params, interval=sleep_interval)

    # Download HI4PI
    logger.info('HI4PI download')
    hi4pi_image = os.path.join(config['pipeline']['workdir'], config['hi4pi']['filename'])
    vizier_width = float(config['hi4pi']['vizier_query_width'])
    params = {
        'name': "hi4pi-download",
        'image': config['hi4pi']['image'],
        'cores': 2,
        'ram': 8,
        'kind': "headless",
        'cmd': 'python3',
        'args': f"{config['hi4pi']['script']} -i {image} -o {hi4pi_image} -w {vizier_width}",
        'env': {}
    }
    job(params['name'], params, interval=sleep_interval)


if __name__ == '__main__':
    main(sys.argv[1:])
