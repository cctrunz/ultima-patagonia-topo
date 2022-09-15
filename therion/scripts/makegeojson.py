import os
from os.path import isfile, join, dirname, abspath
import sys
import re
import argparse
import shutil
import subprocess
import tempfile
import pandas as pd

import shapefile
from json import dumps
import pyproj as proj
transformer = proj.Transformer.from_crs("epsg:32718", "epsg:4326")

# produce the cave centrelines

CONFIG_FILE = """
source ../data/index.th

export map -fmt esri -o ../data/gis
export model -fmt esri -o ../data/gis

export database -o ../data/gis/database.csv
"""



# write temporary config file
with open("temp.thconfig", 'w') as f:
    f.write(CONFIG_FILE)
    f.close()
subprocess.check_output("therion temp.thconfig", shell = True)
subprocess.check_output("rm temp.thconfig", shell = True)
subprocess.check_output("rm therion.log", shell = True)

CONFIG_FILE = """
source ../data/{sector}/{survey}/{survey}.th
export model -fmt survex -o temp.3d
"""

def findSurvey(CAD_NUM):
    try:
        SURVEY_ADDRESS = database[[(CAD_NUM in value) for value in database['From'].values]]['To'].values[0]
        SURVEY = SURVEY_ADDRESS.split('@')[1].split('.')[-1]
        print(SURVEY)
    except IndexError:
        SURVEY = "NaN"
    return SURVEY

def getDepthLength(CAD_NUM):
    SURVEY = findSurvey(CAD_NUM)
    if SURVEY != "NaN" and SURVEY !='(null)':
        print(SURVEY)
        with open('temp.thconfig', 'w') as f:
            FORMATTED = CONFIG_FILE.format(sector = CAD_NUM.split('ENT_')[1][:3], survey =SURVEY)
            f.write(FORMATTED)
            f.close()

        subprocess.check_output("therion temp.thconfig", shell = True)
        subprocess.check_output("rm temp.thconfig", shell = True)
        subprocess.check_output("rm temp.3d", shell = True)

        # open the log and get the depth.

        with open("therion.log", 'r') as f:
            LOG = f.readlines()

            for LINE in LOG:
                if "Total length of survey legs" in LINE:
                    NUMS = LINE.split("Total length of survey legs =")[1].strip(" ")
                    print(NUMS.split('(')[0].strip(" ").strip("m"))
                    LENGTH = float(NUMS.split('(')[0].strip(" ").strip("m"))
                elif "Vertical range" in LINE:
                    DEPTH = float(LINE.split(" ")[4].strip('m'))

            f.close()
        subprocess.check_output("rm therion.log", shell = True)


    else:
        DEPTH = "NaN"
        LENGTH = "NaN"
    return (LENGTH,DEPTH)

# read the database
database =  pd.read_csv('../data/gis/database.csv')

# read the synthesis
DATA = pd.read_csv('../data/BROUILLON_cadastre/UP_MDD_DDA_Temp_synthese_Cavites_NumCad.csv')

SYNTHESE = DATA[['CAD_NUM','NomCadastre','Alt.','Dev. Topo','Prof.','UP','Explorateurs']]


reader = shapefile.Reader("../data/gis/stations3d.shp")
fields = reader.fields[1:]
field_names = [field[0] for field in fields]
POINTS_FIXES = []

for sr in reader.shapeRecords():
    atr = dict(zip(field_names, sr.record))
    # filter by centerline

    if 'ENT' in atr['_NAME']:

        try:
            vals = (SYNTHESE[SYNTHESE['CAD_NUM'] == atr['_NAME']].values[0])
            LENGTH,DEPTH = getDepthLength(atr['_NAME'])
            if LENGTH != 'NaN':
                atr['_LENGTH'] = "{:.0f}".format(LENGTH)
                atr['_DEPTH'] = "{:.0f}".format(DEPTH)
            else:
                atr['_LENGTH'] = str(vals[3])
                atr['_DEPTH'] = str(vals[4])

            ROOT  = 'https://tr1813.github.io/ultima-patagonia-topo/therion/data/'
            CAVE_URL = ROOT+vals[0].strip('ENT_')[:3]+'/'+vals[1]+'/'+vals[1]+'.html'
            print(CAVE_URL)
            atr['_CAD_NUM'] = vals[0].strip('ENT_')
            atr['_CAVENAME'] = vals[1]
            atr['_ALTITUDE'] = str(vals[2])
            atr['_EXPED'] = vals[5]
            atr['_EXPLORATEURS'] = str(vals[6])
            atr['_URL'] = "{}".format(CAVE_URL)
        except IndexError:
            atr['_CAD_NUM'] = atr['_NAME'].strip('ENT_')
            atr['_CAVENAME'] = 'not known'
            atr['_LENGTH'] = "not known"
            atr['_DEPTH'] = "not known"
            atr['_ALTITUDE'] = "not known"
            atr['_EXPED'] = "not known"
            atr['_EXPLORATEURS'] = "not known"
            atr['_URL'] = "not known"
            pass

        #print(atr)
        geom = sr.shape.__geo_interface__
        X,Y = geom['coordinates']

        X2,Y2 =  transformer.transform(X,Y)
        geom['coordinates'] = (Y2,X2)


        POINTS_FIXES.append(dict(type="Feature", geometry=geom, properties=atr))

geojson = open("../data/gis/points_fixes.js", "w")
geojson.write("var pointsFixes = \n")
geojson.write(dumps({"type": "FeatureCollection", "features": POINTS_FIXES}, indent=2) + "\n")
geojson.close()

reader = shapefile.Reader("../data/gis/shots3d.shp")
fields = reader.fields[1:]
field_names = [field[0] for field in fields]
SURVEY_LINES = []

for sr in reader.shapeRecords():
    atr = dict(zip(field_names, sr.record))
    geom = sr.shape.__geo_interface__

    if atr['_SPLAY'] ==0 :
        nodes = geom['coordinates']
        newnodes = []
        for node in nodes:
            x2,y2 = transformer.transform(node[0],node[1])

            newnodes.append((y2,x2))
        geom['coordinates'] =  newnodes

        SURVEY_LINES.append(dict(type="Feature", geometry=geom, properties=atr))

print(SURVEY_LINES)

geojson = open("../data/gis/lines2D.js", "w")
geojson.write("var lines2D = \n")
geojson.write(dumps({"type": "FeatureCollection", "features": SURVEY_LINES}, indent=2) + "\n")
geojson.close()
