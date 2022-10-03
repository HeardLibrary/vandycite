# acquire-wikidata-metadata.py 
# (c) 2022 Vanderbilt University. This program is released under a GNU General Public License v3.0 http://www.gnu.org/licenses/gpl-3.0
# Author: Steve Baskauf

# The CSV files generated by this script are compatible with the VanderBot v1.7 API-writing script vanderbot.py
# The generated CSVs go with the metadata description file generated by the convert_json_to_metadata_schema.py
# The input JSON is the same as that which is used for input by convert_json_to_metadata_schema.py and its format
# is described at https://github.com/HeardLibrary/linked-data/blob/master/vanderbot/convert-config.md

version = '1.1.1'
created = '2022-02-13'

# Note: if the single value of an existing property changes to another single value, the script will replace the data
# to be the current value without any comment. If this is not the desired behavior, the data should be checked for changes
# using a federated query first to discover potential vandalism, etc.
# -----------------------------------------
# Version 1.1 change notes: 
# - added support for somevalue snaks

from pathlib import Path
import requests
from time import sleep
import json
import yaml
import csv
import os
import sys # Read CLI arguments

# ----------------
# Configuration settings
# ----------------

sparql_sleep = 0.1 # number of seconds to wait between queries to SPARQL endpoint
home = str(Path.home()) # gets path to home directory; supposed to work for both Win and Mac
endpoint = 'https://query.wikidata.org/sparql'
accept_media_type = 'application/json'

# Set default values
config_path = 'config.yaml'
#config_path = 'config.json'
default_language = 'en'

arg_vals = sys.argv[1:]
# see https://www.gnu.org/prep/standards/html_node/_002d_002dversion.html
if '--version' in arg_vals or '-V' in arg_vals: # provide version information according to GNU standards 
    print('Acquire Wikidata data', version)
    print('Copyright ©', created[:4], 'Vanderbilt University')
    print('License GNU GPL version 3.0 <http://www.gnu.org/licenses/gpl-3.0>')
    print('This is free software: you are free to change and redistribute it.')
    print('There is NO WARRANTY, to the extent permitted by law.')
    print('Author: Steve Baskauf')
    print('Revision date:', created)
    sys.exit()

if '--help' in arg_vals or '-H' in arg_vals: # provide help information according to GNU standards
    # needs to be expanded to include brief info on invoking the program
    print('For help, see the documentation page at https://github.com/HeardLibrary/linked-data/blob/master/vanderbot/acquire_wikidata.md')
    print('Report bugs to: steve.baskauf@vanderbilt.edu')
    sys.exit()

# Code from https://realpython.com/python-command-line-arguments/#a-few-methods-for-parsing-python-command-line-arguments
opts = [opt for opt in arg_vals if opt.startswith('-')]
args = [arg for arg in arg_vals if not arg.startswith('-')]

if '--config' in opts: #  set path to configuration file
    config_path = args[opts.index('--config')]
if '-C' in opts: 
    config_path = args[opts.index('-C')]

if '--lang' in opts: #  set default language for labels in columns whose output is suppressed
    default_language = args[opts.index('--lang')]
if '-L' in opts: 
    default_language = args[opts.index('-L')]

# ----------------
# Utility functions
# ----------------

# Best to send a user-agent header because some Wikimedia servers don't like unidentified clients
def generate_header_dictionary(accept_media_type):
    user_agent_header = 'VanderBot/1.7.1 (https://github.com/HeardLibrary/linked-data/tree/master/vanderbot; mailto:steve.baskauf@vanderbilt.edu)'
    requestHeaderDictionary = {
        'Accept' : accept_media_type,
        'Content-Type': 'application/sparql-query',
        'User-Agent': user_agent_header
    }
    return requestHeaderDictionary

requestheader = generate_header_dictionary(accept_media_type)

# Read plain text from file
def read_plain_text(filename):
    with open(filename, 'rt', encoding='utf-8') as file_object:
        text = file_object.read()
        return text

# read from a CSV file into a list of dictionaries
def read_dict(filename):
    with open(filename, 'r', newline='', encoding='utf-8') as file_object:
        dict_object = csv.DictReader(file_object)
        array = []
        for row in dict_object:
            array.append(row)
    return array

# write a list of dictionaries to a CSV file
def write_dicts_to_csv(table, filename, fieldnames):
    with open(filename, 'w', newline='', encoding='utf-8') as csv_file_object:
        writer = csv.DictWriter(csv_file_object, fieldnames=fieldnames)
        writer.writeheader()
        for row in table:
            writer.writerow(row)

# extracts the qNumber from a Wikidata IRI
def extract_qnumber(iri):
    # pattern is http://www.wikidata.org/entity/Q6386232
    pieces = iri.split('/')
    return pieces[-1]

# extracts the UUID and qId from a statement IRI
def extract_statement_uuid(iri):
    # pattern is http://www.wikidata.org/entity/statement/Q7552806-8B88E0CA-BCC8-49D5-9AC2-F1755464F1A2
    pieces = iri.split('/')
    statement_id = pieces[5]
    pieces = statement_id.split('-')
    return pieces[1] + '-' + pieces[2] + '-' + pieces[3] + '-' + pieces[4] + '-' + pieces[5], pieces[0]

def convert_skolem_to_turtle_bnode(string):
    """Parse hash-based Skolem IRI and return a string Turtle-style bnode with same hash.
    
    Any other string is returned unaltered.
    """
    original, success, hash_ = string.partition('http://www.wikidata.org/.well-known/genid/')
    if success:
        return True, '_:' + hash_
    else:
        return False, original

# function to use in sort
def sort_funct(row):
    return row['qid']

# ----------------
# Specialty functions
# ----------------

# function to add variables related to a property to the select clause and graph pattern of the SPARQL query
def sparql_append_property(prop, select_prefix, graph_pattern_prefix):
    variable_name = prop['variable']
    prop_id = prop['pid']
    
    # Create the variables for the select clause of the query
    select_prefix += ' ?' + variable_name + '_uuid'
    if prop['value_type'] == 'date':
        select_prefix += ' ?' + variable_name + '_nodeId ?' + variable_name + ' ?' + variable_name + '_val ?' + variable_name + '_prec'
    elif prop['value_type'] == 'quantity':
        select_prefix += ' ?' + variable_name + '_nodeId ?' + variable_name + ' ?' + variable_name + '_val ?' + variable_name + '_unit'
    elif prop['value_type'] == 'globecoordinate':
        select_prefix += ' ?' + variable_name + '_nodeId ?' + variable_name + ' ?' + variable_name + '_val ?' + variable_name + '_long ?' + variable_name + '_prec'
    else:
        select_prefix += ' ?' + variable_name

    if len(prop['ref']) > 0:
        select_prefix += ' ?' + variable_name + '_ref1_hash'
        for reference in prop['ref']:
            if reference['value_type'] == 'date':
                select_prefix += ' ?' + variable_name + '_ref1_' + reference['variable'] + '_nodeId ?' + variable_name + '_ref1_' + reference['variable'] + '_val ?' + variable_name + '_ref1_' + reference['variable'] + '_prec'
            else:
                select_prefix += ' ?' + variable_name + '_ref1_' + reference['variable']


    for qualifier in prop['qual']:
        if qualifier['value_type'] == 'date':
            select_prefix += ' ?' + variable_name + '_' + qualifier['variable'] + '_nodeId ?' + variable_name + '_' + qualifier['variable'] + '_val ?' + variable_name + '_' + qualifier['variable'] + '_prec'
        else:
            select_prefix += ' ?' + variable_name + '_' + qualifier['variable']

    # Create the graph pattern for the query
    graph_pattern_prefix += '''optional{
?qid p:''' + prop['pid'] + ' ?' + variable_name + '''_uuid.
?''' + variable_name + '_uuid ps:' + prop['pid'] + ' ?' + variable_name + '.\n''' # This is needed even for node-valued claims in order to test for blank nodes.

    # These need to be optional in the event that there is a blank node. In that case these triples would not exist.
    if prop['value_type'] == 'date':
        graph_pattern_prefix += '''optional{
?''' + variable_name + '_uuid psv:' + prop['pid'] + ' ?' + variable_name + '''_nodeId.
?''' + variable_name + '_nodeId wikibase:timeValue ?' + variable_name + '''_val.
?''' + variable_name + '_nodeId wikibase:timePrecision ?' + variable_name + '''_prec.
}\n'''
        
    elif prop['value_type'] == 'quantity':
        graph_pattern_prefix += '''optional{
?''' + variable_name + '_uuid psv:' + prop['pid'] + ' ?' + variable_name + '''_nodeId.
?''' + variable_name + '_nodeId wikibase:quantityAmount ?' + variable_name + '''_val.
?''' + variable_name + '_nodeId wikibase:quantityUnit ?' + variable_name + '''_unit.
}\n'''
        
    elif prop['value_type'] == 'globecoordinate':
        graph_pattern_prefix += '''optional{
?''' + variable_name + '_uuid psv:' + prop['pid'] + ' ?' + variable_name + '''_nodeId.
?''' + variable_name + '_nodeId wikibase:geoLatitude ?' + variable_name + '''_val.
?''' + variable_name + '_nodeId wikibase:geoLongitude ?' + variable_name + '''_long.
?''' + variable_name + '_nodeId wikibase:geoPrecision ?' + variable_name + '''_prec.
}\n'''
        
    elif prop['value_type'] == 'monolingualtext':
        graph_pattern_prefix += 'filter(lang(?' + variable_name + ')="' + prop['language'] + '")\n'

    # construct reference triple patterns
    for reference in prop['ref']:
        graph_pattern_prefix += '''
optional{
?''' + variable_name + '''_uuid prov:wasDerivedFrom ?''' + variable_name + '''_ref1_hash.
'''
        if reference['value_type'] == 'date':
            graph_pattern_prefix += '''
?''' + variable_name + '_ref1_hash prv:' + reference['pid'] + ' ?' + variable_name + '_ref1_' + reference['variable'] + '''_nodeId.
?''' + variable_name + '_ref1_' + reference['variable'] + '_nodeId wikibase:timeValue ?' + variable_name + '_ref1_' + reference['variable'] + '''_val.
?''' + variable_name + '_ref1_' + reference['variable'] + '_nodeId wikibase:timePrecision ?' + variable_name + '_ref1_' + reference['variable'] + '''_prec.
'''
        elif reference['value_type'] == 'monolingualtext':
            graph_pattern_prefix += '''
?''' + variable_name + '_ref1_hash pr:' + reference['pid'] + ' ?' + variable_name + '_ref1_' + reference['variable'] + '''.
filter(lang(?''' + variable_name + '_' + reference['variable'] + ')="' + reference['language'] + '''")
'''
        else:
            graph_pattern_prefix += '''
?''' + variable_name + '_ref1_hash pr:' + reference['pid'] + ' ?' + variable_name + '_ref1_' + reference['variable'] +'''.
'''
        # close the optional clause
        graph_pattern_prefix += '''}
'''

    # construct qualifiers triple patterns
    for qualifier in prop['qual']:
        if qualifier['value_type'] == 'date':
            graph_pattern_prefix += '''
optional{
?''' + variable_name + '''_uuid pqv:''' + qualifier['pid'] + ' ?' + variable_name + '_' + qualifier['variable'] + '''_nodeId.
?''' + variable_name + '_' + qualifier['variable'] + '_nodeId wikibase:timeValue ?' + variable_name + '_' + qualifier['variable'] + '''_val.
?''' + variable_name + '_' + qualifier['variable'] + '_nodeId wikibase:timePrecision ?' + variable_name + '_' + qualifier['variable'] + '''_prec.
}'''
        elif qualifier['value_type'] == 'monolingualtext':
            graph_pattern_prefix += '''
optional{
?''' + variable_name + '_uuid pq:' + qualifier['pid'] + ' ?' + variable_name + '_' + qualifier['variable'] + '''.
filter(lang(?''' + variable_name + '_' + qualifier['variable'] + ')="' + qualifier['language'] + '''")
}
'''
        else:
            graph_pattern_prefix += '''
optional{
?''' + variable_name + '''_uuid pq:'''+ qualifier['pid'] + ''' ?''' + variable_name + '_' + qualifier['variable'] +'''.
}
'''

    # close graph pattern
    graph_pattern_prefix += '}\n'
    return select_prefix, graph_pattern_prefix

# function to add columns to column list for CSV header
def csv_header_append(prop, header_list):
    variable_name = prop['variable']

    header_list.append(variable_name + '_uuid')
    if prop['value_type'] == 'date':
        header_list.append(variable_name + '_nodeId')
        header_list.append(variable_name + '_val')
        header_list.append(variable_name + '_prec')
    elif prop['value_type'] == 'quantity':
        header_list.append(variable_name + '_nodeId')
        header_list.append(variable_name + '_val')
        header_list.append(variable_name + '_unit')
    elif prop['value_type'] == 'globecoordinate':
        header_list.append(variable_name + '_nodeId')
        header_list.append(variable_name + '_val')
        header_list.append(variable_name + '_long')
        header_list.append(variable_name + '_prec')
    else:
        header_list.append(variable_name)

    for qualifier in prop['qual']:
        if qualifier['value_type'] == 'date':
            header_list.append(variable_name + '_' + qualifier['variable'] + '_nodeId')
            header_list.append(variable_name + '_' + qualifier['variable'] + '_val')
            header_list.append(variable_name + '_' + qualifier['variable'] + '_prec')
        else:
            header_list.append(variable_name + '_' + qualifier['variable'])

    if len(prop['ref']) > 0:
        header_list.append(variable_name + '_ref1_hash')
        for reference in prop['ref']:
            if reference['value_type'] == 'date':
                header_list.append(variable_name + '_ref1_' + reference['variable'] + '_nodeId')
                header_list.append(variable_name + '_ref1_' + reference['variable'] + '_val')
                header_list.append(variable_name + '_ref1_' + reference['variable'] + '_prec')
            else:
                header_list.append(variable_name + '_ref1_' + reference['variable'])

    return header_list

def remove_multiples(matching_rows, col_name, old_id):
    matched_rows = []
    for check_row in matching_rows:
        if old_id == check_row[col_name]:
            matched_rows.append(check_row)
    return matched_rows

def check_for_duplicates(list, new_item):
    for item in list:
        if new_item == item:
            return list
    return list.append(new_item)

# ----------------
# Main function
# ----------------

def process_file(manage_descriptions, label_description_language_list, output_file_name, prop_list):
    
    # Determine if previous file and load if exists
    # In order to determine which redundant statements and references to keep, try to load a previous version of the file.

    if os.path.exists(data_path + output_file_name):
        old_file_data = read_dict(data_path + output_file_name)
    else:
        old_file_data = []

    # ----------------
    # Create the SPARQL query to get the property statements for the items on the Q IDs list
    # ----------------

    select_variable_list = ''
    graph_pattern = ''
    for prop in prop_list:
        select_variable_list, graph_pattern = sparql_append_property(prop, select_variable_list, graph_pattern)
    query = '''
    select distinct ?qid '''

    # note: dashes not allowed in SPARQL variable names, so replace with underscores
    for label_description_language in label_description_language_list:
        query +='?label_' + label_description_language.replace('-', '_') + ' ?description_' + label_description_language.replace('-', '_') + ' '
    query += select_variable_list + ' where {'

    query += '''
      VALUES ?qid
    {
    ''' + item_qids + '''
    }
    '''
    # made label and description optional since some don't have in English
    for label_description_language in label_description_language_list:
        query += '''
    optional {
    ?qid rdfs:label ?label_''' + label_description_language.replace('-', '_') + '''.
    filter(lang(?label_''' + label_description_language.replace('-', '_') + ')="' + label_description_language + '''")
    }
    optional {
    ?qid schema:description ?description_''' + label_description_language.replace('-', '_') + '''.
    filter(lang(?description_''' + label_description_language.replace('-', '_') + ')="' + label_description_language + '''")
    }
    '''

    query += graph_pattern + '''
    }
    order by ?qid'''

    #print(query)

    # ----------------
    # send request to Wikidata Query Service
    # ----------------

    print('querying SPARQL endpoint to acquire item metadata')
    response = requests.post(endpoint, data=query.encode('utf-8'), headers=requestheader)
    # If there is an error message, the conversion to JSON will fail and the error message will be printed. There will then be an error because "data" isn't defined
    try:
        data = response.json()
    except:
        print(response.text)

    # extract the values from the response JSON
    results = data['results']['bindings']

    print('done retrieving data')
    #print(json.dumps(results, indent=2))

    # ----------------
    # extract results
    # ----------------

    metadata_list = []
    for result in results:
        row_dict = {}
        row_dict['qid'] = extract_qnumber(result['qid']['value'])
        for label_description_language in label_description_language_list:
            try:
                row_dict['label_' + label_description_language.replace('-', '_')] = result['label_' + label_description_language.replace('-', '_')]['value']
            except:
                row_dict['label_' + label_description_language.replace('-', '_')] = ''
            if manage_descriptions:
                try:
                    row_dict['description_' + label_description_language.replace('-', '_')] = result['description_' + label_description_language.replace('-', '_')]['value']
                except:
                    row_dict['description_' + label_description_language.replace('-', '_')] = ''           
        for property in prop_list:
            try:
                row_dict[property['variable'] + '_uuid'], trash = extract_statement_uuid(result[property['variable'] + '_uuid']['value'])
            except:
                row_dict[property['variable'] + '_uuid'] = ''

            # Need to check for blank nodes first
            converted = False
            try:
                converted, ps_value = convert_skolem_to_turtle_bnode(result[property['variable']]['value'])

                # If there was a blank node, the value node cells need to set to empty strings except for the _val cell, to which the blank node identifier should be transferred.
                if converted:
                    if property['value_type'] == 'date':
                        row_dict[property['variable'] + '_nodeId'] = ''
                        row_dict[property['variable'] + '_val'] = ps_value
                        row_dict[property['variable'] + '_prec'] = ''
                    elif property['value_type'] == 'quantity':
                        row_dict[property['variable'] + '_nodeId'] = ''
                        row_dict[property['variable'] + '_val'] = ps_value
                        row_dict[property['variable'] + '_unit'] = ''
                    elif property['value_type'] == 'globecoordinate':
                        row_dict[property['variable'] + '_nodeId'] = ''
                        row_dict[property['variable'] + '_val'] = ps_value
                        row_dict[property['variable'] + '_long'] = ''
                        row_dict[property['variable'] + '_prec'] = ''
                    else:
                        row_dict[property['variable']] = ps_value
            # In cases where the property doesn't have a value, the dict won't have that key. So do nothing -- null values will be handled in the next section.
            except:
                pass

            # Value is not a blank node, so process normally
            if not converted:
                try:
                    if property['value_type'] == 'item':
                        row_dict[property['variable']] = extract_qnumber(result[property['variable']]['value'])
                    elif property['value_type'] == 'date':
                        row_dict[property['variable'] + '_nodeId'] = extract_qnumber(result[property['variable'] + '_nodeId']['value'])
                        row_dict[property['variable'] + '_val'] = result[property['variable'] + '_val']['value']
                        row_dict[property['variable'] + '_prec'] = result[property['variable'] + '_prec']['value']
                    elif property['value_type'] == 'quantity':
                        row_dict[property['variable'] + '_nodeId'] = extract_qnumber(result[property['variable'] + '_nodeId']['value'])
                        row_dict[property['variable'] + '_val'] = result[property['variable'] + '_val']['value']
                        row_dict[property['variable'] + '_unit'] = extract_qnumber(result[property['variable'] + '_unit']['value'])
                    elif property['value_type'] == 'globecoordinate':
                        row_dict[property['variable'] + '_nodeId'] = extract_qnumber(result[property['variable'] + '_nodeId']['value'])
                        row_dict[property['variable'] + '_val'] = result[property['variable'] + '_val']['value']
                        row_dict[property['variable'] + '_long'] = result[property['variable'] + '_long']['value']
                        row_dict[property['variable'] + '_prec'] = result[property['variable'] + '_prec']['value']
                    else:
                        row_dict[property['variable']] = result[property['variable']]['value']
            
                except: # assign empty string if there is no value returned from query
                    if property['value_type'] == 'date':
                        row_dict[property['variable'] + '_nodeId'] = ''
                        row_dict[property['variable'] + '_val'] = ''
                        row_dict[property['variable'] + '_prec'] = ''
                    elif property['value_type'] == 'quantity':
                        row_dict[property['variable'] + '_nodeId'] = ''
                        row_dict[property['variable'] + '_val'] = ''
                        row_dict[property['variable'] + '_unit'] = ''
                    elif property['value_type'] == 'globecoordinate':
                        row_dict[property['variable'] + '_nodeId'] = ''
                        row_dict[property['variable'] + '_val'] = ''
                        row_dict[property['variable'] + '_long'] = ''
                        row_dict[property['variable'] + '_prec'] = ''
                    else:
                        row_dict[property['variable']] = ''
            
            if len(property['ref']) > 0:
                try:
                    row_dict[property['variable'] + '_ref1_hash'] = extract_qnumber(result[property['variable'] + '_ref1_hash']['value'])
                except:
                    row_dict[property['variable'] + '_ref1_hash'] = ''
                for reference in property['ref']:
                    try:
                        if reference['value_type'] == 'date':
                            # Note: the form of the node ID is http://www.wikidata.org/value/0a8f688406e3fc53d0119eafcd2c0396
                            # so the extract_qnumber() function can be used on it.
                            row_dict[property['variable'] + '_ref1_' + reference['variable'] + '_nodeId'] = extract_qnumber(result[property['variable'] + '_ref1_' + reference['variable'] + '_nodeId']['value'])
                            row_dict[property['variable'] + '_ref1_' + reference['variable'] + '_val'] = result[property['variable'] + '_ref1_' + reference['variable'] + '_val']['value']
                            row_dict[property['variable'] + '_ref1_' + reference['variable'] + '_prec'] = result[property['variable'] + '_ref1_' + reference['variable'] + '_prec']['value']
                        elif reference['value_type'] == 'item':
                            row_dict[property['variable'] + '_ref1_' + reference['variable']] = extract_qnumber(result[property['variable'] + '_ref1_' + reference['variable']]['value'])
                        else:
                            row_dict[property['variable'] + '_ref1_' + reference['variable']] = result[property['variable'] + '_ref1_' + reference['variable']]['value']
                    except:
                        if reference['value_type'] == 'date':
                            row_dict[property['variable'] + '_ref1_' + reference['variable'] + '_nodeId'] = ''
                            row_dict[property['variable'] + '_ref1_' + reference['variable'] + '_val'] = ''
                            row_dict[property['variable'] + '_ref1_' + reference['variable'] + '_prec'] = ''
                        else:
                            row_dict[property['variable'] + '_ref1_' + reference['variable']] = ''

            for qualifier in property['qual']:
                try:
                    if qualifier['value_type'] == 'date':
                        row_dict[property['variable'] + '_' + qualifier['variable'] + '_nodeId'] = extract_qnumber(result[property['variable'] + '_' + qualifier['variable'] + '_nodeId']['value'])
                        row_dict[property['variable'] + '_' + qualifier['variable'] + '_val'] = result[property['variable'] + '_' + qualifier['variable'] + '_val']['value']
                        row_dict[property['variable'] + '_' + qualifier['variable'] + '_prec'] = result[property['variable'] + '_' + qualifier['variable'] + '_prec']['value']
                    elif qualifier['value_type'] == 'item':
                        row_dict[property['variable'] + '_' + qualifier['variable']] = extract_qnumber(result[property['variable'] + '_' + qualifier['variable']]['value'])
                    else:
                        row_dict[property['variable'] + '_' + qualifier['variable']] = result[property['variable'] + '_' + qualifier['variable']]['value']
                except:
                    if qualifier['value_type'] == 'date':
                        row_dict[property['variable'] + '_' + qualifier['variable'] + '_nodeId'] = ''
                        row_dict[property['variable'] + '_' + qualifier['variable'] + '_val'] = ''
                        row_dict[property['variable'] + '_' + qualifier['variable'] + '_prec'] = ''
                    else:
                        row_dict[property['variable'] + '_' + qualifier['variable']] = ''

        metadata_list.append(row_dict)

    #print(json.dumps(metadata_list, indent=2))

    # ----------------
    # prepare acquired data for saving
    # ----------------

    # create the list of column headers
    fieldnames = ['qid']
    # The schema generator puts all of the labels first, then the descriptions
    for label_description_language in label_description_language_list:
        fieldnames.append('label_' + label_description_language.replace('-', '_'))          
    if manage_descriptions:
        for label_description_language in label_description_language_list:
            fieldnames.append('description_' + label_description_language.replace('-', '_'))          
    for prop in prop_list:
        fieldnames = csv_header_append(prop, fieldnames)
    # print(fieldnames)

    # ----------------
    # Remove redundant item lines
    # ----------------
    
    file_save_allowed = True

    # Determine whether old and new file headers are the same
    try:
        old_fieldnames = list(old_file_data[0].keys())
        if old_fieldnames != fieldnames:
            print(old_fieldnames)
            print(fieldnames)
            print("fieldnames are not the same")
            file_save_allowed = False
    except:
        print('no pre-existing file')

    # Remove duplicate rows that aren't found in a previous version of the table. It doesn't do anything if there 
    # isn't an earlier table. 

    # If there are duplicates items in the previous version, they will both be carried forward in the new version
    # unless the metadata that causes them to be different is removed or changed so that they are now the same.
    # In that case, they will be removed by the check_for_duplicates() function.

    output_data = []
    # old_file_data will be an empty list if it doesn't exist and no matching will be attempted
    for old_row in old_file_data:
        matching_rows = []
        # find all rows from the query that match the QID of the row in the original table
        for row in metadata_list:
            if old_row['qid'] == row['qid']:
                matching_rows.append(row)
        original_matching_rows = list(matching_rows) # make a copy of the matching data
        if len(matching_rows) == 0:
            print('Warning! No result from the query matches old item:', old_row['qid'])

        # Note: if only one row matches, there is no reason to believe that any value or reference is the same as 
        # before since no checks are done here.
        elif len(matching_rows) == 1:
            check_for_duplicates(output_data, matching_rows[0])

        # There are three reasons why there could be duplicate rows:
        # - there could be two references for the same statement.
        # - there could be two values for the same property.
        # - the reference or qualifier properties could have more than one value
        elif len(matching_rows) > 1: # skip if there aren't duplicate rows
            # There can be any number of duplicate rows since the SPARQL query catches every combination
            # of duplicate reference and statement values. But this should systematically reduce them to 
            # one if there were only one statement in the original file.

            # Remove rows whose references don't match those in the original file.
            for prop in prop_list:
                if len(prop['ref']) != 0:
                    ref_col_name = prop['variable'] + '_ref1_hash'
                    old_ref_hash = old_row[ref_col_name]
                    if len(matching_rows) > 1:
                        matching_rows = remove_multiples(matching_rows, ref_col_name, old_ref_hash)

            # It's possible that two rows will have different values for a property but the same reference
            # So look for the statement UUID that matches the UUID in the original file and eliminate others.
            for prop in prop_list:
                statement_uuid_col_name = prop['variable'] + '_uuid'
                old_statement_uuid = old_row[statement_uuid_col_name]
                if len(matching_rows) > 1:
                    matching_rows = remove_multiples(matching_rows, statement_uuid_col_name, old_statement_uuid)

            # It's possible that the previous value for this item doesn't have the same reference or values 
            # as any of the query results.
            if len(matching_rows) == 0:
                print('Multiple query results for', old_row['qid'], 'but none match previous statement values and references.')
                print('Check values manually.\n')
                output_data += original_matching_rows
            elif len(matching_rows) ==1:
                check_for_duplicates(output_data, matching_rows[0])
            else:
                # The last case is rare, but occurs. In that case, the rows are the same because either the
                # reference or qualifier properties have multiple properties.
                for prop in prop_list:
                    for ref in prop['ref']:
                        if ref['value_type'] == 'date' or ref['value_type'] == 'quantity' or ref['value_type'] == 'globecoordinate':
                            ref_col_name = prop['variable'] + '_ref1_' + ref['variable'] + '_val'
                        else:
                            ref_col_name = prop['variable'] + '_ref1_' + ref['variable']
                        old_ref_value = old_row[ref_col_name]
                        matching_rows = remove_multiples(matching_rows, ref_col_name, old_ref_value)
                    for qual in prop['qual']:
                        if qual['value_type'] == 'date' or qual['value_type'] == 'quantity' or qual['value_type'] == 'globecoordinate':
                            qual_col_name = prop['variable'] + '_' + qual['variable'] + '_val'
                        else:
                            qual_col_name = prop['variable'] + '_' + qual['variable']
                        old_qual_value = old_row[qual_col_name]
                        matching_rows = remove_multiples(matching_rows, qual_col_name, old_qual_value)

                if len(matching_rows) == 0:
                    print('Multiple query results for', old_row['qid'], 'but none match previous qual/ref values.')
                    print('Check values manually.\n')
                    output_data += original_matching_rows
                elif len(matching_rows) ==1:
                    check_for_duplicates(output_data, matching_rows[0])
                else:
                    print('Multiple query results for', old_row['qid'], 'have the same qual/ref values.')
                    print('How did this happen? It should not. Check results manually.')
                    output_data += matching_rows

    # Add any new items that were added to the item list file or that resulted from the item query.
    for row in metadata_list:
        found = False
        for old_row in old_file_data:
            if old_row['qid'] == row['qid']:
                found = True
                break # stop looking for more matches
        if not found:
            output_data.append(row)
    output_data.sort(key = sort_funct)
    #print(json.dumps(output_data, indent = 2))

    # write the data to a CSV file
    if file_save_allowed:
        print('writing data to file', output_file_name)
        write_dicts_to_csv(output_data, data_path + output_file_name, fieldnames)
    else:
        print('data not written to file', output_file_name)

# ----------------
# Beginning of main script
# ----------------

#file_text = read_plain_text(config_path)
#config = json.loads(file_text)
with open('config.yaml', 'r') as file_object:
    config = yaml.safe_load(config_path)

data_path = config['data_path']
item_source_csv = config['item_source_csv'] 
item_graph_pattern_file = config['item_pattern_file']
outfiles = config['outfiles']

# ----------------
# Load list of items from file (or generate by query) and construct Q ID list for query
# ----------------

if item_source_csv == '':
    # Load item data from csv
    print('loading graph pattern from file')
    filename = data_path + item_graph_pattern_file
    graph_pattern = read_plain_text(filename)
    print('done loading')
    item_query = '''select distinct ?qid where {
''' + graph_pattern + '''
}'''
    # print(graph_pattern)

    # send request to Wikidata Query Service
    print('querying SPARQL endpoint to acquire item QIDs')
    response = requests.post(endpoint, data=item_query.encode('utf-8'), headers=requestheader)
    #print(response.text)
    data = response.json()
    print('results returned')

    # extract the values from the response JSON
    items = data['results']['bindings']
    #print(items)
    
    # Create VALUES list for items
    item_qids = ''
    for item in items:
        item_qids += 'wd:' + extract_qnumber(item['qid']['value']) + '\n'
else:
    # Load item data from csv
    print('loading item data from file')
    filename = data_path + item_source_csv
    items = read_dict(filename)
    print('done loading')

    # Create VALUES list for items
    item_qids = ''
    for item in items:
        item_qids += 'wd:' + item['qid'] + '\n'
# remove trailing newline
item_qids = item_qids[:len(item_qids)-1]
print()

#print(item_qids)
for outfile in outfiles:
    if outfile['manage_descriptions']:
        process_file(True, outfile['label_description_language_list'], outfile['output_file_name'], outfile['prop_list'])
    else:
        process_file(False, [default_language], outfile['output_file_name'], outfile['prop_list'])
    print()
print('done')
