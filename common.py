#!/usr/bin/env python3

import os
import time
import json
import requests
from prefect import task, flow, get_run_logger


CADC_DEFAULT_CERTIFICATE = '/Users/she393/.ssl/cadcproxy.pem'
CANFAR_IMAGE_URL = 'https://ws-uv.canfar.net/skaha/v1/image'
CANFAR_SESSION_URL = 'https://ws-uv.canfar.net/skaha/v1/session'
# CANFAR occasionally accepts a connection and then never answers. Without a
# timeout the flow blocks forever while the remote job keeps running.
REQUEST_TIMEOUT = 60
# Consecutive failed status polls tolerated before giving up on a session.
MAX_POLL_FAILURES = 120
RUNNING_STATES = ['Pending', 'Running', 'Terminating']
COMPLETE_STATES = ['Succeeded', 'Completed']
FAILED_STATES = ['Failed']


def path_to_vos(path):
    """Convert a file path for the CANFAR file system to a VOS project space

    """
    vos_path = path.replace('/arc/', 'arc:')
    return vos_path


def vos_file_exists(client, path):
    """Check whether a file exists in CANFAR storage.

    vos raises NotFoundException from isfile() for a node that is not there
    rather than returning False, so listing the parent directory and testing
    for membership is the reliable check. Listing fresh each time also picks
    up files written by earlier steps of the same run.
    """
    directory, filename = os.path.split(path)
    return filename in client.listdir(path_to_vos(directory))


def canfar_get_images(type='headless'):
    logger = get_run_logger()
    cert = os.getenv('CADC_CERTIFICATE', CADC_DEFAULT_CERTIFICATE)

    url = f'{CANFAR_IMAGE_URL}?type={type}'
    r = requests.get(url, cert=cert, timeout=REQUEST_TIMEOUT)
    logger.info(r.status_code)
    print(r.text)
    return json.loads(r.text)


def create_canfar_session(params):
    logger = get_run_logger()
    cert = os.getenv('CADC_CERTIFICATE', CADC_DEFAULT_CERTIFICATE)

    # Skaha expects repeated env=KEY=VALUE parameters. A dict is form-encoded
    # to its keys alone, silently dropping every value.
    params = dict(params)
    env = params.get('env')
    if isinstance(env, dict):
        params['env'] = [f'{k}={v}' for k, v in env.items()]

    r = requests.post(CANFAR_SESSION_URL, data=params, cert=cert, timeout=REQUEST_TIMEOUT)
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
    r = requests.get(url, cert=cert, timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        logger.error(r.status_code)
        logger.error(r.content)
    return r


def _session_logs(session_id, logger):
    """Fetch a session's logs, tolerating a failure to retrieve them.

    Only ever used to report what a job did, so losing the logs must not
    replace the real outcome with a request error.
    """
    try:
        return info_canfar_session(session_id, logs=True).text
    except Exception as e:
        logger.exception(e)
        return f'<logs unavailable for session {session_id}: {e}>'


@task(task_run_name='{name}')
def job(name, params, interval=10, *args, **kwargs):
    """Job wrapper for CANFAR containers

    """
    logger = get_run_logger()
    logger.info(name)
    completed = False
    session_id = create_canfar_session(params).strip('\n')
    logger.info(f'Session: {session_id}')
    poll_failures = 0
    while not completed:
        try:
            # The request belongs inside the try: CANFAR times out or answers
            # with an HTML error page often enough that a failed poll must not
            # end the task, since the job itself is running server-side and is
            # unaffected. Sleeping here also stops the retry from spinning on
            # the API for the length of an outage.
            res = info_canfar_session(session_id, logs=False)
            status = json.loads(res.text)['status']
        except Exception as e:
            poll_failures += 1
            logger.exception(e)
            if poll_failures > MAX_POLL_FAILURES:
                raise Exception(
                    f'Giving up on session {session_id} after {poll_failures} '
                    'consecutive polling failures'
                )
            time.sleep(interval)
            continue

        poll_failures = 0

        completed = status in COMPLETE_STATES
        failed = status in FAILED_STATES
        if failed:
            raise Exception(f'Job failed {_session_logs(session_id, logger)}')

        time.sleep(interval)
        logger.info(f'Job {session_id} {status}')

    # Logging to stdout
    logger.info(_session_logs(session_id, logger))
    return