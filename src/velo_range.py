#!/usr/bin/env python3

"""
This script takes a position in J2000 equatorial coordinates
and prints out the approximate frequency range occupied by
Galactic HI emission in that direction.

This Python script was adapted from Tobias Westmeier's original code velo_range.c
Compilation: gcc -O3 -o velo_range velo_range.c -lm
"""

import sys
import math
import numpy as np


VDEV = 70.0
RMAX = 20.0
ZDISC = 5.0
RSUN = 8.5
FHI = 1.42040575e+9
SOL = 299792.458


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


def main():
    if len(sys.argv) != 3:
        print("Usage: ./velo_range <ra> <dec>\n")

    ra = float(sys.argv[1])
    dec = float(sys.argv[2])
    v1, v2 = velocity_range(ra, dec)

    # Convert to frequency
    f1 = FHI / (1.0 + v1 / SOL)
    f2 = FHI / (1.0 + v2 / SOL)

    print(f"{v1}\t{v2}")
    print(f"{f2}\t{f1}")
    return


if __name__ == '__main__':
    main()