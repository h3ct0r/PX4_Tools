# PX4_Tools
Set of scripts and tools to help parsing, interpret and analyse the log data coming from the PX4 controller board.
Also some geotagging scripts for GoPRO cameras and PX4 controller board.

### How to use

#### sdlog2_dump 

Use this command to extract the information on the binary file extracted using the APM planner or Mission Planner

```sh
python sdlog2_dump.py test_files/16-07-13_17-52-16.bin -f "export.csv" -t "TIME" -d "," -n ""
```

#### geo_tag_images

Use this script to geotag a set of images. It uses the difference between UTC and GPS time (17 s) to accomodate images on the local time of the PC running the script.

```sh
python geo_tag_images.py --logfile=mylog.bin --input=images/ --output=taggedImages/
```

# Based on
These tools are based on the tools already avaliable on: https://github.com/PX4/Firmware/tree/master/Tools/sdlog2
