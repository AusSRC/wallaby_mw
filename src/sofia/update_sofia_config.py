#!/usr/bin/env python3

"""Custom method to update the SoFiA-2 parameter files for WALLABY Milky Way + SD joint source finding
Will create two separate parameter files for the positive and negative velocity ranges.

Velocity range calculation:
This script takes a position in J2000 equatorial coordinates
and prints out the approximate frequency range occupied by
Galactic HI emission in that direction.

This Python script was adapted from Tobias Westmeier's original code velo_range.c
Compilation: gcc -O3 -o velo_range velo_range.c -lm
"""

import os
import sys
import math
import numpy as np
import logging
from astropy.io import fits
from astropy.wcs import WCS
import astropy.units as u
from astropy.coordinates import SkyCoord
from argparse import ArgumentParser


logging.basicConfig(level=logging.INFO)


VDEV = 70.0
RMAX = 20.0
ZDISC = 5.0
RSUN = 8.5
FHI = 1.42040575e+9
SOL = 299792.458


def get_centre(hdu):
    w = WCS(hdu.header)
    c_ra_pix = hdu.header['NAXIS1'] // 2
    c_dec_pix = hdu.header['NAXIS2'] // 2
    centre = SkyCoord.from_pixel(c_ra_pix, c_dec_pix, wcs=w)
    return centre


def pixel_from_frequency(hdu, freq):
    header = hdu.header
    if header['CTYPE3'] == 'FREQ':
        crval = header['CRVAL3']
        cdelt = header['CDELT3']
        crpix = header['CRPIX3']
    elif header['CTYPE4'] == 'FREQ':
        crval = header['CRVAL4']
        cdelt = header['CDELT4']
        crpix = header['CRPIX4']
    else:
        raise Exception('CTYPE3 and CTYPE4 are not frequency axes...')

    pixel = (freq - crval) / cdelt + crpix
    return pixel


def rotation_curve(r):
    """Function to return rotation velocity for given radius

    """
    r = abs(r)
    if r > RMAX:
        r = RMAX

    # MW rotation curve from Clemens (1985) for R0 = 8.5 kpc, v0 = 220 km/s:
    rotcur = np.array([
        [    0.0000, 3069.81000, -15809.80000, 43980.100000, -68287.3000000, 54904.0000000, -17731.00000000, 0.00000000],
		[  325.0912, -248.14670,    231.87099,  -110.735310,     25.0730060,    -2.1106250,      0.00000000, 0.00000000],
		[-2342.6564, 2507.60391,  -1024.06876,   224.562732,    -28.4080026,     2.0697271,     -0.08050808, 0.00129348],
		[  234.8800,    0.00000,      0.00000,     0.000000,      0.0000000,     0.0000000,      0.00000000, 0.00000000]
    ])
    breaks = np.array([0.00, 0.09, 0.45, 1.60])

    index = 3
    while (r < 8.5 * breaks[index]):
        index = index - 1

    vrot = 0.0
    for order in range(0, 8):
        vrot += rotcur[index][order] * pow(r, order)
    return vrot


def scale_height(r):
    """Function to return scale height of disc for given radius
    Note: r and z are expected to be in kpc.

    """
    r = abs(r)
    if (r < RSUN / 2.0):
        return ZDISC / 2.0
    return ZDISC * (r / RSUN)


def velocity_range(ra, dec):
    """Main function of original velo_range.c code converted into a Python function for use in pipeline.

    """
    # J2000 input coordinates in deg
    alpha = math.pi * float(ra) / 180.0
    delta = math.pi * float(dec) / 180.0

    # Constants for J2000 -> Galactic coordinate transformation
    a0 = 192.859496 * math.pi / 180.0
    d0 = 27.128353 * math.pi / 180.0
    l0 = 122.932000 * math.pi / 180.0

    # Convert Equatorial to Galactic coordinates
    glon = l0 - math.atan2(math.cos(delta) * math.sin(alpha - a0), math.sin(delta) * math.cos(d0) - math.cos(delta) * math.sin(d0) * math.cos(alpha - a0))
    glat = math.asin(math.sin(delta) * math.sin(d0) + math.cos(delta) * math.cos(d0) * math.cos(alpha - a0))

    # Initiate velocity range with arbitrary large values:
    v1 = 1.0e+9
    v2 = -1.0e+9

    # Cast ray away from the sun to determine radial velocity range of gas:
    distance_values = np.arange(0.0, RSUN + RMAX, 0.1)
    for distance in distance_values:
        height  = distance * abs(math.sin(glat))
        targetX = distance * math.sin(glon) * math.cos(glat)
        targetY = RSUN - distance * math.cos(glon) * math.cos(glat)
        radius  = math.sqrt(targetX * targetX + targetY * targetY)

        if (height > ZDISC):
            break

        vRad = (rotation_curve(radius) * (RSUN / radius) - rotation_curve(RSUN)) * math.sin(glon) * math.cos(glat)
        if (vRad < v1):
            v1 = vRad
        if (vRad > v2):
            v2 = vRad

    # Include deviation velocity:
    if (v1 > 0.0):
        v1 = 0.0
    if (v2 < 0.0):
        v2 = 0.0
    v1 -= VDEV
    v2 += VDEV
    return (v1, v2)


def main(argv):
    if len(argv) != 2:
        print("Usage: ./velo_range <ra> <dec>\n")

    ra = float(sys.argv[0])
    dec = float(sys.argv[1])
    v1, v2 = velocity_range(ra, dec)

    # Convert to frequency
    f1 = FHI / (1.0 + v1 / SOL)
    f2 = FHI / (1.0 + v2 / SOL)

    print(f"{v1}\t{v2}")
    print(f"{f2}\t{f1}")
    return (v1, v2)



def main(argv):
    parser = ArgumentParser(argv)
    parser.add_argument('-i', '--image', required=True, help='Image cube (for RA and Dec)')
    parser.add_argument('-f', '--input_parameter_file', required=True, help='SoFiA parameter file template')
    parser.add_argument('-o', '--output_parameter_files', required=True, help='Output SoFiA parameter file directory')
    parser.add_argument('-pf', '--positive_filename', default='pos.par', required=False, help='Parameter filename for positive velocity range')
    parser.add_argument('-nf', '--negative_filename', default='neg.par', required=False, help='Parameter filename for negative velocity range')
    parser.add_argument('-po', '--positive_output_filename', default='positive', required=False, help='Parameter filename for positive velocity range')
    parser.add_argument('-no', '--negative_output_filename', default='negative', required=False, help='Parameter filename for negative velocity range')
    parser.add_argument('-d', '--input_data', required=True, help='Parameter: input.data')
    parser.add_argument('-od', '--output_directory', required=True, help='Parameter: output.directory')
    args = parser.parse_args(argv)

    assert os.path.exists(args.image), 'Fits image does not exist'
    assert os.path.exists(args.input_parameter_file), 'SoFiA parameter file template does not exist'
    os.makedirs(args.output_parameter_files, exist_ok=True)
    os.makedirs(args.output_directory, exist_ok=True)
    assert os.path.exists(args.output_parameter_files), 'Output directory for SoFiA parameter files does not exist'
    assert os.path.exists(args.output_directory), 'Output directory for SoFiA output products'

    # Open image cube
    with fits.open(args.image) as hdul:
        hdu = hdul[0]
        centre = get_centre(hdu)
    logging.info(f'Image centre: {centre}')
    ra = centre.ra.value
    dec = centre.dec.value

    # Get milkyway frequency range
    v1, v2 = velocity_range(ra, dec)
    f1 = FHI / (1.0 + v1 / SOL)
    f2 = FHI / (1.0 + v2 / SOL)
    logging.info(f'Milky Way frequency range [Hz]: {f1} - {f2}')

    # Get equivalent pixel range
    fpix1 = math.ceil(pixel_from_frequency(hdu, f1))
    fpix2 = math.floor(pixel_from_frequency(hdu, f2))
    logging.info(f'Equivalent frequency pixel range: {fpix1} - {fpix2}')

    # Reading parameter file
    logging.info('Reading parameter file template')
    with open(args.input_parameter_file, 'r') as fi:
        parameters = fi.readlines()

    # Update content
    update_dict_neg = {
        'input.data': args.input_data,
        'input.region': f'0,99999,0,99999,{fpix1},99999',
        'output.directory': args.output_directory,
        'output.filename': args.negative_output_filename
    }
    update_dict_pos = {
        'input.data': args.input_data,
        'input.region': f'0,99999,0,99999,0,{fpix2}',
        'output.directory': args.output_directory,
        'output.filename': args.positive_output_filename
    }

    # Writing to parameter files
    logging.info('Writing output parameter files')
    pos = os.path.join(args.output_parameter_files, args.positive_filename)
    logging.info(f'Writing {pos}')
    with open(pos, 'w') as fo:
        for line in parameters:
            param = line.split('=')[0].strip()
            if param in update_dict_pos.keys():
                line = f'{param} = {update_dict_pos[param]}\n'
            fo.write(line)

    neg = os.path.join(args.output_parameter_files, args.negative_filename)
    logging.info(f'Writing {neg}')
    with open(neg, 'w') as fo:
        for line in parameters:
            param = line.split('=')[0].strip()
            if param in update_dict_neg.keys():
                line = f'{param} = {update_dict_neg[param]}\n'
            fo.write(line)

    logging.info('Writing updated parameter files complete')


if __name__ == '__main__':
    argv = sys.argv[1:]
    main(argv)
