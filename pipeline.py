#!/usr/bin/env python3

from astropy.io import fits
from prefect import task, flow
from prefect_docker.images import pull_docker_image
from prefect_docker.containers import (
    create_docker_container,
    start_docker_container,
    get_docker_container_logs,
    stop_docker_container,
    remove_docker_container
)
from src.pixel_region import wallaby_pixel_region


@task
def pixel_region(hdu, size):
    region = wallaby_pixel_region(hdu, size)
    return region


@task
def miriad(image, cmd):
    pull_docker_image(image)
    container = create_docker_container(image, command=cmd)
    start_docker_container(container_id=container.id)
    logs = get_docker_container_logs(container_id=container.id)
    print(logs)
    stop_docker_container(container_id=container.id)
    remove_docker_container(container_id=container.id)
    return


@flow
def main():
    # Args
    miriad_image = 'miriad/miriad-dev'
    file = '/Users/she393/Downloads/data/milkyway/ngc4808_subfits.fits'
    size = 320

    # Run
    hdul = fits.open(file)
    hdu = hdul[0]
    region = pixel_region(hdu, size)
    print(region)

    # miriad(miriad_image, f'fits in={file} out=data/test op=xyin')
    miriad(miriad_image, f'echo "{region}"')


if __name__ == '__main__':
    main()