## WALLABY MilkyWay

WALLABY MW cube workflow

* image cube
* velo_range.py download_hi4pi subfits.py pixel_region.py
* miriad
* source finding
* sofiax

### Config

You will need to provide a config file with the following parameters:

```
[default]
workdir = /data/milkyway/pipeline
wallaby_image_file = /data/milkyway/ngc5044_4/ngc5044_4.fits
hdul=0
output_image = /data/milkyway/ngc5044_4/ngc5044_4_combined.fits
hi4pi_width = 20.0

[miriad]
docker_image = miriad/miriad-dev
script = miriad/combinemw.sh
mount = /data
```