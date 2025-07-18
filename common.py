#!/usr/bin/env python3

import os
import time
import json
import requests
from prefect import task, flow, get_run_logger


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
def job(name, params, interval=10, *args, **kwargs):
    """Job wrapper for CANFAR containers

    """
    logger = get_run_logger()
    logger.info(name)
    completed = False
    session_id = create_canfar_session(params).strip('\n')
    logger.info(f'Session: {session_id}')
    while not completed:
        res = info_canfar_session(session_id, logs=False)
        try:
            status = json.loads(res.text)['status']
        except Exception as e:
            logger.exception(e)
            continue

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