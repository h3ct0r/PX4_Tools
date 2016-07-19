#!/usr/bin/env python
#
#  Tag the images recorded during a flight with geo location extracted from
#  a PX4 binary log file.
#
#  This file accepts *.jpg format images and reads position information
#  from a *.bin file
#
#  Example Syntax:
#  python geotag.py --logfile=log001.bin --input=images/ --output=imagesWithTag/ --offset=-0.4 -v
#
#   Author: Hector Azpurua
#   Based on the script of Andreas Bircher

import os
import re
import sys
import csv
import bisect
import pyexiv2
import argparse
from lxml import etree
import datetime, calendar
from shutil import copyfile
from pykml.factory import KML_ElementMaker as K


class GpsPosition(object):
    def __init__(self, timestamp, lat, lon, alt):
        self.timestamp = timestamp
        self.lat = float(lat)
        self.lon = float(lon)
        self.alt = float(alt)


class Main:
    def __init__(self):
        """

        :param logfile:
        :param input:
        :param output:
        :param offset:
        :param verbose:
        :return:
        """
        args = self.get_arg()

        self.logfile = args['logfile']
        self.input = args['input']
        self.output = args['output']
        self.klm = args['klm']
        self.verbose = args['verbose']
        self.offset = args['offset']
        self.time_tresh = args['treshold']

        self.tdiff_list = []
        self.non_processed_files = []
        self.tagged_gps = []
        self.gps_list = self.load_gps_from_log(self.logfile, self.offset)
        self.img_list = self.load_image_list(self.input)

        if len(self.img_list) <= 0:
            print '[ERROR] Cannot load JPG images from input folder, please check filename extensions.'
            sys.exit(1)

        if not os.path.exists(self.output):
            os.makedirs(self.output)

        if not self.output.endswith(os.path.sep):
            self.output += os.path.sep

        self.tag_images()

        if self.klm:
            self.gen_klm()

    @staticmethod
    def to_degree(value, loc):
        """
        Convert a lat or lon value to degrees/minutes/seconds
        :param value: the latitude or longitude value
        :param loc: could be ["S", "N"] or ["W", "E"]
        :return:
        """
        if value < 0:
            loc_value = loc[0]
        elif value > 0:
            loc_value = loc[1]
        else:
            loc_value = ""

        absolute_value = abs(value)
        deg = int(absolute_value)
        t1 = (absolute_value-deg) * 60
        minute = int(t1)
        sec = round((t1 - minute) * 60, 5)

        return deg, minute, sec, loc_value

    @staticmethod
    def gps_week_seconds_to_datetime(gpsweek, gpsmillis, leapmillis=0):
        """
        Convert GPS week and seconds to datetime object, using leap milliseconds if necessary
        :param gpsweek:
        :param gpsmillis:
        :param leapmillis:
        :return:
        """
        datetimeformat = "%Y-%m-%d %H:%M:%S.%f"
        epoch = datetime.datetime.strptime("1980-01-06 00:00:00.000", datetimeformat)
        elapsed = datetime.timedelta(days=(gpsweek * 7), milliseconds=(gpsmillis + leapmillis))

        return Main.utc_to_local(epoch + elapsed)

    @staticmethod
    def utc_to_local(utc_dt):
        """
        Convert UTC time in local time
        :param utc_dt:
        :return:
        """
        timestamp = calendar.timegm(utc_dt.timetuple())  # use integer timestamp to avoid precision lost
        local_dt = datetime.datetime.fromtimestamp(timestamp)
        assert utc_dt.resolution >= datetime.timedelta(microseconds=1)

        return local_dt.replace(microsecond=utc_dt.microsecond)

    def gen_klm(self):
        _doc = K.kml()

        doc = etree.SubElement(_doc, 'Document')

        for i, item in enumerate(self.tagged_gps):
            doc.append(K.Placemark(
                K.name('pl'+str(i+1)),
                K.Point(
                    K.coordinates(
                        str(item).strip('[]').replace(' ', '')
                        )
                )
            )
        )

        doc.append(K.Placemark(
            K.name('path'),
            K.LineStyle(
                K.color('#00FFFF'),
                K.width(10)
            ),
            K.LineString(
                K.coordinates(
                    ' '.join([str(item).strip('[]').replace(' ', '') for item in self.tagged_gps])
                )
            )
        ))

        s = etree.tostring(_doc)

        file_path = self.output + 'GoogleEarth_points.kml'
        f = open(file_path,'w')
        f.write(s)
        f.close()

        print '[INFO] KML file generated on:', file_path

    def get_closest_datetime_index(self, datetime_list, elem):
        """
        Get the closest element between a list of datetime objects and a date
        :param datetime_list:
        :param elem:
        :return:
        """
        i = bisect.bisect_left(datetime_list, elem)
        date = datetime_list[i]
        diff = (date - elem).total_seconds()

        if diff > self.time_tresh:
            return -1, diff

        return i, diff

    def set_gps_location(self, file_name, lat, lng, alt):
        """
        Add the GPS tag and altitude to a image file
        :param file_name:
        :param lat:
        :param lng:
        :param alt:
        :return:
        """
        lat_deg = self.to_degree(lat, ["S", "N"])
        lng_deg = self.to_degree(lng, ["W", "E"])

        exiv_lat = (pyexiv2.Rational(lat_deg[0] * 60 + lat_deg[1], 60),
                    pyexiv2.Rational(lat_deg[2] * 100, 6000), pyexiv2.Rational(0, 1))
        exiv_lng = (pyexiv2.Rational(lng_deg[0] * 60 + lng_deg[1], 60),
                    pyexiv2.Rational(lng_deg[2] * 100, 6000), pyexiv2.Rational(0, 1))

        try:
            exiv_image = pyexiv2.ImageMetadata(file_name)
            exiv_image.read()

            exiv_image["Exif.GPSInfo.GPSLatitude"] = exiv_lat
            exiv_image["Exif.GPSInfo.GPSLatitudeRef"] = lat_deg[3]
            exiv_image["Exif.GPSInfo.GPSLongitude"] = exiv_lng
            exiv_image["Exif.GPSInfo.GPSLongitudeRef"] = lng_deg[3]
            exiv_image["Exif.GPSInfo.GPSAltitude"] = pyexiv2.Rational(alt, 1)
            exiv_image["Exif.GPSInfo.GPSAltitudeRef"] = '0'
            exiv_image["Exif.Image.GPSTag"] = 654
            exiv_image["Exif.GPSInfo.GPSMapDatum"] = "WGS-84"
            exiv_image["Exif.GPSInfo.GPSVersionID"] = '2 0 0 0'

            exiv_image.write(True)
        except Exception as e:
            print '[ERROR]', e

    def load_gps_from_log(self, log_file, offset):
        """
        Load gps list from PX4 binary log
        :param log_file:
        :param offset:
        :return:
        """
        os.system('python sdlog2_dump.py ' + log_file + ' -f log.csv')
        f = open('log.csv', 'rb')
        reader = csv.reader(f)
        headers = reader.next()
        line = {}
        for h in headers:
            line[h] = []

        for row in reader:
            for h, v in zip(headers, row):
                line[h].append(v)

        gps_list = []
        for seq in range(0, len(line['GPS_Lat']) - 1):
            gps_time = int(line['GPS_TimeMS'][seq + 1])
            gps_week = int(line['GPS_Week'][seq + 1])
            gps_lat = float(line['GPS_Lat'][seq + 1])
            gps_lon = float(line['GPS_Lng'][seq + 1])
            gps_alt = float(line['GPS_RelAlt'][seq + 1])

            date = self.gps_week_seconds_to_datetime(gps_week, gps_time, leapmillis=offset * 1000)
            gps_list.append(GpsPosition(date, gps_lat, gps_lon, gps_alt))

        return gps_list

    def load_image_list(self, input_folder, file_type='jpg'):
        """
        Load image list from a folder given a file type
        :param input_folder:
        :param file_type:
        :return:
        """
        self.img_list = [input_folder + filename for filename in os.listdir(input_folder)
                         if re.search(r'\.'+file_type+'$', filename, re.IGNORECASE)]
        self.img_list = sorted(self.img_list)
        return self.img_list

    def tag_images(self):
        """
        Tag the image list using the GPS loaded from the LOG file
        :return:
        """
        tagged_gps = []
        img_size = len(self.img_list)
        print '[INFO] Number of images:', img_size

        dt_list = [x.timestamp for x in self.gps_list]

        for i in xrange(img_size):
            base_path, filename = os.path.split(self.img_list[i])
            cdate = datetime.datetime.fromtimestamp(os.path.getmtime(self.img_list[i]))
            gps_i, img_tdiff = self.get_closest_datetime_index(dt_list, cdate)

            if gps_i == -1:
                self.non_processed_files.append(filename)
                continue

            closest_gps = self.gps_list[gps_i]
            self.tdiff_list.append(img_tdiff)

            if self.verbose:
                msg = "[DEBUG] %s/%s %s | img %s -> gps %s (%ss)".ljust(60) %\
                        (i+1, img_size, filename, cdate, closest_gps.timestamp, img_tdiff)
                print msg

            copyfile(self.img_list[i], self.output + filename)

            self.set_gps_location(self.output + filename, closest_gps.lat, closest_gps.lon, closest_gps.alt)
            self.tagged_gps.append([closest_gps.lon, closest_gps.lat, 0])

        if len(self.tdiff_list) > 0:
            print '[INFO] Mean diff in seconds:', sum(self.tdiff_list) / float(len(self.tdiff_list))

    @staticmethod
    def get_arg():
        parser = argparse.ArgumentParser(
            description='Geotag script to add GPS info to pictures from PX4 binary log files.'\
                        'It uses synchronized time to allocate GPS positions.'
        )

        parser.add_argument(
            '-l', '--logfile', help='PX4 log file containing recorded positions.', required=True
        )
        parser.add_argument(
            '-i', '--input', help='Input folder containing untagged images.', required=True
        )
        parser.add_argument(
            '-o', '--output', help='Output folder to contain tagged images.', required=True
        )
        parser.add_argument(
            '-t', '--treshold', help='Time treshold between the GPS time and the local image time.',
            default=1, required=False, type=float
        )
        parser.add_argument(
            '-of', '--offset', help='Time offset in SECONDS between the GPS time and the local time.',
            default=-0.4, required=False, type=float
        )
        parser.add_argument(
            '-klm', '--klm', help='Save the in KML format the information of all tagged images.',
            required=False, action='store_true'
        )
        parser.add_argument(
            '-v', '--verbose', help='Prints lots of information.',
            required=False, action='store_true'
        )

        args = vars(parser.parse_args())
        return args


if __name__ == "__main__":
    m = Main()