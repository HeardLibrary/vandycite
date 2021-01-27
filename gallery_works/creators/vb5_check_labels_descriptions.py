# VanderBot v1.5 (2020-09-08) vb5_check_labels_descriptions.py
# (c) 2020 Vanderbilt University. This program is released under a GNU General Public License v3.0 http://www.gnu.org/licenses/gpl-3.0
# Author: Steve Baskauf
# For more information, see https://github.com/HeardLibrary/linked-data/tree/master/vanderbot

# See http://baskauf.blogspot.com/2020/02/vanderbot-python-script-for-writing-to.html
# for a series of blog posts about VanderBot.

# This script is the fifth in a series of five that are used to prepare researcher/scholar ("employee") data 
# for upload to Wikidata. It inputs data output from the previous script, vb4_download_wikidata.py and
#  
# It outputs data into a file for ingestion by the a script used to upload data to 
# Wikidata, vb6_upload_wikidata.py .

# The last part of the script sets the deptShortName in the csv-metadata.json file, a necessary
# precursor before running the upload script. 
# -----------------------------------------
# Version 1.1 change notes: 
# - no changes
# -----------------------------------------
# Version 1.2 change notes: 
# - No substantive changes
# -----------------------------------------
# Version 1.3 change notes (2020-08-06):
# - no changes
# -----------------------------------------
# Version 1.5 change notes (2020-09-08):
# - no changes

import json
from time import sleep
import csv

import vb_common_code as vbc

sparqlSleep = 0.25

filename = 'creators_to_write.csv'
employees = vbc.readDict(filename)

for employeeIndex in range(0, len(employees)):
    if employees[employeeIndex]['qid'] == '':
    #if employeeIndex == 1:
        #employees[employeeIndex]['labelEn'] = 'Muktar H Aliyu'
        #employees[employeeIndex]['description'] = 'researcher'
        query = '''select distinct ?entity where {
          ?entity rdfs:label "'''+ employees[employeeIndex]['label_en'] + '''"@en.
          ?entity schema:description "'''+ employees[employeeIndex]['description_en'] + '''"@en.
          }'''
        print('Checking label: "' + employees[employeeIndex]['label_en'] + '", description: "' + employees[employeeIndex]['description_en'] + '"')
        match = vbc.Query(uselabel = False, sleep=sparqlSleep).generic_query(query)
        if len(match) > 0:
            print('\nWarning! Row ' + str(employeeIndex + 2) + ' is the same as ' + match[0])
            print('This must be fixed before writing to the API !!!\n')
        sleep(0.25)

print('done')