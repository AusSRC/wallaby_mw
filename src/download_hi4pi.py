#!/usr/bin/env python3

from astropy.io import fits
from astroquery.skyview import SkyView


SURVEY = "HI4PI"


def download_hi4pi():
    SkyView.list_surveys()
    position = f"{194.0}d {6.0}d"
    res = SkyView.get_image_list(position=position, survey=SURVEY)
    print(res)
    paths = SkyView.get_images(position=position, survey=SURVEY)
    print(paths)


if __name__ == '__main__':
    download_hi4pi()
