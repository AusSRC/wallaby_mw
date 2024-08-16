#!/bin/csh

# Usage:
# miriad combinemw.sh <directory> <single_dish.fits> <wallaby_cube.fits> <region>
#
# For region input see imsub docs:
# https://www.atnf.csiro.au/computing/software/miriad/doc/imsub.html

# Read files
fits in=$2 op=xyin out=$1/singledish
fits in=$3 op=xyin out=$1/wallaby

# Preprocess singledish
hanning in=$1/singledish out=$1/singledish_hann
imsub in=$1/singledish_hann out=$1/singledish_imsub_incr incr=1,1,2
imsub in=$1/singledish_imsub_incr out=$1/singledish_imsub "region=images(42,426)"

# Preprocess wallaby
velsw in=$1/wallaby axis=freq options=altspc
velsw in=$1/wallaby axis=freq,lsrk
imsub in=$1/wallaby out=$1/wallaby_trim "region=$4"

# Regrid
regrid in=$1/singledish_imsub tin=$1/wallaby_trim out=$1/singledish_regrid

# Merge
immerge in=$1/wallaby_trim,$1/singledish_regrid out=$1/combined uvrange=25,35,meters options=notaper
fits in=$1/combined op=xyout out=$1/combined.fits
