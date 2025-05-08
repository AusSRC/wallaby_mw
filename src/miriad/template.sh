#!/bin/csh

# Usage:
# miriad combinemw.sh <hi4pi.fits> <wallaby_milkyway.fits> <output.fits> <region>
#
# For region input see imsub docs:
# https://www.atnf.csiro.au/computing/software/miriad/doc/imsub.html

# Read files
fits in=$1 op=xyin out=/data/hi4pi
fits in=$2 op=xyin out=/data/wallaby

# Preprocess hi4pi
hanning in=/data/hi4pi out=/data/hi4pi_hann
imsub in=/data/hi4pi_hann out=/data/hi4pi_imsub_incr incr=1,1,2
imsub in=/data/hi4pi_imsub_incr out=/data/hi4pi_imsub "region=images(42,426)"

# Preprocess wallaby
velsw in=/data/wallaby axis=freq options=altspc
velsw in=/data/wallaby axis=freq,lsrk
imsub in=/data/wallaby out=/data/wallaby_trim "$4"

# Regrid
regrid in=/data/hi4pi_imsub tin=/data/wallaby_trim out=/data/hi4pi_regrid

# Merge
immerge in=/data/wallaby_trim,/data/hi4pi_regrid out=/data/combined uvrange=25,35,meters options=notaper
fits in=/data/combined op=xyout out=$3
exit