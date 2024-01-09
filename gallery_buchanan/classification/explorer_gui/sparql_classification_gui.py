# sparql_classification_gui, an app to explore artworks via SPARQL queries.  sparql_classification_gui.py
SCRIPT_VERSION = '0.0.1'
VERSION_MODIFIED = '2024-01-08'

# (c) 2024 Vanderbilt University. This program is released under a GNU General Public License v3.0 http://www.gnu.org/licenses/gpl-3.0
# Author: Steve Baskauf
# For more information, see 

# The Sparqler class code is (c) 2022-2023 Steven J. Baskauf
# and released under a GNU General Public License v3.0 http://www.gnu.org/licenses/gpl-3.0
# For more information, see https://github.com/HeardLibrary/digital-scholarship/blob/master/code/wikidata/sparqler.py

# -----------------------------------------
# Version 0.0.1 change notes: 
# - Initial version
# -----------------------------------------


# ------------
# import modules
# ------------

from tkinter import *
import tkinter.scrolledtext as tkst
import sys
import requests
import datetime
import time
import json
import csv
from typing import List, Dict, Tuple, Any, Optional

# ------------
# Global variables
# ------------

# These defaults can be changed by command line arguments
DEFAULT_ENDPOINT = 'https://sparql.vanderbilt.edu/sparql' # arg: --endpoint or -E 
DEFAULT_METHOD = 'get' # arg: --method or -M
CSV_OUTPUT_PATH = 'sparql_results.csv' # arg: --results or -R
PREFIXES_DOC_PATH = 'prefixes.txt' # arg: --prefixes or -P
USER_AGENT = 'sparql_classification_gui/' + SCRIPT_VERSION + ' ()'

starting_classification_label = 'tray'
starting_current_scheme = 'wikidata'

# Starting values of variables common to all functions

# Designate the orientation of the scheme buttons for each current scheme.
SCHEME_ORIENTATIONS = {
    'wikidata': {'left': 'nomenclature', 'right': 'aat', 'current': 'wikidata', 'broader': 'wikidata'},
    'aat': {'left': 'wikidata', 'right': 'nomenclature', 'current': 'aat', 'broader': 'aat'},
    'nomenclature': {'left': 'aat', 'right': 'wikidata', 'current': 'nomenclature', 'broader': 'nomenclature'}
}

# Initial values for match types
MATCH_TYPE = {'left': 'exactMatch',
                'right': 'exactMatch'
    }

CURRENT_SCHEME_ORIENTATION = SCHEME_ORIENTATIONS[starting_current_scheme]
CLASSIFICATION = {'nomenclature': 'https://nomenclature.info/nom/11781', 
                  'aat': 'http://vocab.getty.edu/aat/300043071',
                  'wikidata': 'http://www.wikidata.org/entity/Q613972',
                  'broader': 'http://www.wikidata.org/entity/Q987767'}
LABEL = {'nomenclature': 'Tray', 
                  'aat': 'trays',
                  'wikidata': 'tray',
                  'broader': 'container'}

# Attempt to make the subclass buttons global so they can be destroyed and recreated.
EXISTING_SUBCLASS_BUTTONS = []

# ------------
# Support command line arguments
# ------------

arg_vals = sys.argv[1:]
# see https://www.gnu.org/prep/standards/html_node/_002d_002dversion.html
if '--version' in arg_vals or '-V' in arg_vals: # provide version information according to GNU standards 
    # Remove version argument to avoid disrupting pairing of other arguments
    # Not really necessary here, since the script terminates, but use in the future for other no-value arguments
    if '--version' in arg_vals:
        arg_vals.remove('--version')
    if '-V' in arg_vals:
        arg_vals.remove('-V')
    print('CommonsTool', SCRIPT_VERSION)
    print('Copyright ©', VERSION_MODIFIED[:4], 'Vanderbilt University')
    print('License GNU GPL version 3.0 <http://www.gnu.org/licenses/gpl-3.0>')
    print('This is free software: you are free to change and redistribute it.')
    print('There is NO WARRANTY, to the extent permitted by law.')
    print('Author: Steve Baskauf')
    print('Revision date:', VERSION_MODIFIED)
    print()
    sys.exit()

if '--help' in arg_vals or '-H' in arg_vals: # provide help information according to GNU standards
    # needs to be expanded to include brief info on invoking the program
    print('''Command line arguments:
--endpoint or -E to specify a SPARQL endpoint URL, default: ''' + DEFAULT_ENDPOINT + '''
--method or -M to specify the HTTP method (get or post) to send the query, default: ''' + DEFAULT_METHOD + '''
--results or -R to specify the path (including filename) to save the CSV results, default: ''' + CSV_OUTPUT_PATH + '''
--agent or -A to specify your own user agent string to be sent with the query, default: ''' + USER_AGENT + '''

''')
    print('Report bugs to: steve.baskauf@vanderbilt.edu')
    print()
    sys.exit()

# Code from https://realpython.com/python-command-line-arguments/#a-few-methods-for-parsing-python-command-line-arguments
opts = [opt for opt in arg_vals if opt.startswith('-')]
args = [arg for arg in arg_vals if not arg.startswith('-')]

if '--endpoint' in opts: # specifies a Wikibase SPARQL endpoint different from the Wikidata Query Service
    DEFAULT_ENDPOINT = args[opts.index('--endpoint')]
if '-E' in opts: # specifies a Wikibase SPARQL endpoint different from the Wikidata Query Service
    DEFAULT_ENDPOINT = args[opts.index('-E')]

if '--results' in opts: # specifies path (including filename) where CSV will be saved
    CSV_OUTPUT_PATH = args[opts.index('--results')]
if '-R' in opts: # specifies path (including filename) where CSV will be saved
    CSV_OUTPUT_PATH = args[opts.index('-R')]

if '--method' in opts: # specifies the HTTP method to be used with the query
    DEFAULT_METHOD = args[opts.index('--method')]
if '-M' in opts: # specifies the HTTP method to be used with the query
    DEFAULT_METHOD = args[opts.index('-M')]

if '--prefixes' in opts: # specifies path (including filename) of text file containing prefixes
    PREFIXES_DOC_PATH = args[opts.index('--prefixes')]
if '-P' in opts: # specifies path (including filename) of text file containing prefixes
    PREFIXES_DOC_PATH = args[opts.index('-P')]

if '--agent' in opts: # to provide your own user agent string to be sent with the query
    USER_AGENT = args[opts.index('--agent')]
if '-A' in opts: # to provide your own user agent string to be sent with the query
    USER_AGENT = args[opts.index('-A')]

# Open the prefixes file and read it in as a string
try:
    with open(PREFIXES_DOC_PATH, 'r') as prefixes_doc:
        PREFIXES = prefixes_doc.read()
except:
    PREFIXES = ''

# ------------
# Functions
# ------------
def change_scheme_button(new_scheme: str) -> None:
    """Handle the click of the "Switch to ..." buttons"""
    # Indicate that EXISTING_SUBCLASS_BUTTONS is a global variable
    global EXISTING_SUBCLASS_BUTTONS

    # Determine whether the existing broader classification is empty or not. If empty, the broader
    # button will be hidden and needs to be redisplayed.
    if CLASSIFICATION['broader'] == '':
        need_to_display_broader_button = True
    else:
        need_to_display_broader_button = False

    # The current scheme orientation will be set to the new_scheme for the button that was clicked.
    CURRENT_SCHEME_ORIENTATION = SCHEME_ORIENTATIONS[new_scheme]

    # Reset the labels for the buttons and text box, and commands for the buttons
    left_button.config(text='Switch to ' + CURRENT_SCHEME_ORIENTATION['left'] + '\nterm: ' + LABEL[CURRENT_SCHEME_ORIENTATION['left']], command = lambda: change_scheme_button(CURRENT_SCHEME_ORIENTATION['left']))
    right_button.config(text='Switch to ' + CURRENT_SCHEME_ORIENTATION['right'] + '\nterm: ' + LABEL[CURRENT_SCHEME_ORIENTATION['right']], command = lambda: change_scheme_button(CURRENT_SCHEME_ORIENTATION['right']))
    current_classification_text.set(CURRENT_SCHEME_ORIENTATION['current'] + '\nterm: ' + LABEL[CURRENT_SCHEME_ORIENTATION['current']])

    # Query to find the new broader category for the current classification.
    broader_label, broader_iri = retrieve_broader_classification(CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']])
    CLASSIFICATION['broader'] = broader_iri
    LABEL['broader'] = broader_label
    if broader_label == '': # Handle the case where there is no broader classification.
        broader_button.grid_forget()
    else:
        broader_button.config(text='Broader ' + CURRENT_SCHEME_ORIENTATION['current'] + '\nterm: ' + broader_label, command = lambda: parent_concept_button(new_scheme))
        if need_to_display_broader_button:
            broader_button.grid(column=2, row=1)

    # Determine the subclasses of the new current concept and create any buttons for them.
    subclass_list = retrieve_narrower_concepts(CURRENT_SCHEME_ORIENTATION['current'], CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']])
        
    # Destroy the existing subclass buttons
    for button in EXISTING_SUBCLASS_BUTTONS:
        #button.grid_forget() # removes button from grid but doesn't destroy it
        button.destroy() # removes button from grid and destroys it
    EXISTING_SUBCLASS_BUTTONS = [] # Not sure if this is necessary.

    # Create new subclass buttons
    EXISTING_SUBCLASS_BUTTONS = generate_subclass_buttons(subclass_list)

    # Find the artworks that are included in the current classification
    retrieve_included_artworks(CURRENT_SCHEME_ORIENTATION['current'], CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']])

def parent_concept_button(scheme_name: str) -> None:
    """Handle the click of the "Broader ..." button by making the parent concept the current classification."""
    # Indicate that EXISTING_SUBCLASS_BUTTONS is a global variable
    global EXISTING_SUBCLASS_BUTTONS

    # Determine whether the existing broader classification is empty or not. If empty, the broader
    # button will be hidden and needs to be redisplayed.
    if CLASSIFICATION['broader'] == '':
        need_to_display_broader_button = True
    else:
        need_to_display_broader_button = False

    # Set the current classification IRI and label to the broader classification
    CLASSIFICATION[scheme_name] = CLASSIFICATION['broader']
    LABEL[scheme_name] = LABEL['broader']
    # I thought it should not be necessary to set this since it's a global variable and already set. But apparently it is getting a value from some previous state.
    CURRENT_SCHEME_ORIENTATION = SCHEME_ORIENTATIONS[scheme_name]

    # Reset the label for the current classification text box.
    current_classification_text.set(CURRENT_SCHEME_ORIENTATION['current'] + '\nterm: ' + LABEL[CURRENT_SCHEME_ORIENTATION['current']])

    # Make the left and right buttons invisible and clear the data for them.
    #left_button.grid_forget()
    #CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['left']] = ''
    #LABEL[CURRENT_SCHEME_ORIENTATION['left']] = ''
    #MATCH_TYPE['left'] = ''

    #right_button.grid_forget()
    #CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['right']] = ''
    #LABEL[CURRENT_SCHEME_ORIENTATION['right']] = ''
    #MATCH_TYPE['right'] = ''

    # If there are equivalent concepts, find them and change the left and right buttons. 
    # If an equivalent concept is not found, make the button invisible.
    find_equivalent_concepts_and_set_buttons(CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']], CURRENT_SCHEME_ORIENTATION)

    # Determine the subclasses of the new current concept and create any buttons for them.
    subclass_list = retrieve_narrower_concepts(CURRENT_SCHEME_ORIENTATION['current'], CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']])
        
    # Destroy the existing subclass buttons
    for button in EXISTING_SUBCLASS_BUTTONS:
        #button.grid_forget() # removes button from grid but doesn't destroy it
        button.destroy() # removes button from grid and destroys it
    EXISTING_SUBCLASS_BUTTONS = [] # Not sure if this is necessary.

    # Create new subclass buttons
    EXISTING_SUBCLASS_BUTTONS = generate_subclass_buttons(subclass_list)

    # Query to find the new broader category for the current classification.
    broader_label, broader_iri = retrieve_broader_classification(CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']])
    CLASSIFICATION['broader'] = broader_iri
    LABEL['broader'] = broader_label

    if broader_label == '': # Handle the case where there is no broader classification.
        broader_button.grid_forget()
    else:
        # Create the new broader button after it has the updated subclass buttons.
        broader_button.config(text='Broader ' + CURRENT_SCHEME_ORIENTATION['current'] + '\nterm: ' + broader_label, command = lambda: parent_concept_button(scheme_name))
        if need_to_display_broader_button:
            broader_button.grid(column=2, row=1)

    # Find the artworks that are included in the higher classification
    retrieve_included_artworks(CURRENT_SCHEME_ORIENTATION['current'], CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']])

def retrieve_included_artworks(current_scheme: str, superclass: str) -> None:
    """Retrieve the artworks that are included in the specified superclass."""
    #print(current_scheme, superclass)

    query_string = '''PREFIX wd:      <http://www.wikidata.org/entity/>
PREFIX wdt:     <http://www.wikidata.org/prop/direct/>
PREFIX gvp:     <http://vocab.getty.edu/ontology#>
PREFIX skos:    <http://www.w3.org/2004/02/skos/core#>

SELECT DISTINCT ?artwork ?artworkLabel ?wdClass ?wdClassLabel
WHERE
{
BIND (<''' + superclass + '''> as ?superclass)
'''

    # Insert the specific part of the query string for the current scheme superclass relationship.
    # Do this instead of UNION because AAT has both gvp:broaderPreferred and skos:broader (which 
    # we don't want to use).
    if current_scheme == 'wikidata':
        query_string += '''?wdClass wdt:P279* ?superclass. # Wikidata
'''
    elif current_scheme == 'aat':
        query_string += '''?class gvp:broaderPreferred* ?superclass. # AAT
        {?wdClass skos:exactMatch ?class.} 
    UNION 
        {?wdClass skos:broadMatch ?class.}
    UNION
        {?wdClass skos:closeMatch ?class.}
'''
    elif current_scheme == 'nomenclature':
        query_string += '''?class skos:broader* ?superclass. # Nomenclature
        {?wdClass skos:exactMatch ?class.} 
    UNION 
        {?wdClass skos:broadMatch ?class.}
    UNION
        {?wdClass skos:closeMatch ?class.}
'''

    # Add the rest of the query string
    query_string += '''?wdClass rdfs:label ?wdClassLabel.
?artwork wdt:P31 ?wdClass.
?artwork rdfs:label ?artworkLabel.
filter(lang(?artworkLabel) = "en")
}
order by ?wdClassLabel ?artworkLabel
'''
    #print(query_string)

    # Send the query to the endpoint
    data = Sparqler().query(query_string) # default to DEFAULT_ENDPOINT
    #print(json.dumps(data, indent=2))
    output_string = ''
    for result in data:
        artwork_iri = result['artwork']['value']
        artwork_label = result['artworkLabel']['value']
        class_iri = result['wdClass']['value']
        class_label = result['wdClassLabel']['value']

        output_string += '(' + class_label + ')' + artwork_iri + ' ' + artwork_label + '\n'
    update_artworks(output_string)

def retrieve_narrower_concepts(current_scheme: str, parent_class: str) -> List[Dict[str, str]]:
    """Retrieve the narrower concepts for a concept.
    Returned values are (label, IRI)."""
    # Query string to find the narrower concepts for AAT, nom, or Wikidata
    query_string = '''PREFIX wd:      <http://www.wikidata.org/entity/>
PREFIX wdt:     <http://www.wikidata.org/prop/direct/>
PREFIX gvp:     <http://vocab.getty.edu/ontology#>
PREFIX skos:    <http://www.w3.org/2004/02/skos/core#>
PREFIX skosxl:  <http://www.w3.org/2008/05/skos-xl#>

SELECT DISTINCT ?superclass ?superclassLabel
WHERE
{
BIND (<''' + parent_class + '''> as ?parentClass)
'''

    # Insert the specific part of the query string for the current scheme superclass relationship.
    # Do this instead of UNION because AAT has both gvp:broaderPreferred and skos:broader (which 
    # we don't want to use).
    if current_scheme == 'wikidata':
        query_string += '''?superclass wdt:P279 ?parentClass. # Parent class is one level above the test superclass
?wdClass wdt:P279* ?superclass. # The test superclass is required to be linked to at least one artwork through any level.
?superclass rdfs:label ?superclassLabel.
'''
    elif current_scheme == 'aat':
        query_string += '''?superclass gvp:broaderPreferred ?parentClass.
?superclass skosxl:prefLabel ?l.
?l skosxl:literalForm ?superclassLabel.
?class gvp:broaderPreferred* ?superclass.
    {?wdClass skos:exactMatch ?class.} 
UNION 
    {?wdClass skos:broadMatch ?class.}
UNION
    {?wdClass skos:closeMatch ?class.}
'''
    elif current_scheme == 'nomenclature':
        query_string += '''?superclass skos:broader ?parentClass.
?superclass skos:prefLabel ?superclassLabel.
?class skos:broader* ?superclass.
    {?wdClass skos:exactMatch ?class.} 
UNION 
    {?wdClass skos:broadMatch ?class.}
UNION
    {?wdClass skos:closeMatch ?class.}
'''

    # Add the rest of the query string
    query_string += '''?artwork wdt:P31 ?wdClass. # The wikidata class must be linked to at least one artwork.
filter(lang(?superclassLabel) = "en")
}
order by ?superclassLabel
'''
    #print(query_string)

    # Send the query to the endpoint
    data = Sparqler().query(query_string) # default to DEFAULT_ENDPOINT
    #print(json.dumps(data, indent=2))

    # Get the superclass IRIs and labels and put them in a list of dictionaries.
    superclasses = []
    for result in data:
        superclass_iri = result['superclass']['value']
        superclass_label = result['superclassLabel']['value']
        superclasses.append({'iri': superclass_iri, 'label': superclass_label})
    return superclasses

def retrieve_broader_classification(search_string: str) -> Tuple[str, str]:
    """Retrieve the broader classification for a concept.
    Returned values are (label, IRI)."""
    # Query string to find the broader classification for AAT, nom, or Wikidata
    query_string = '''PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wdt:     <http://www.wikidata.org/prop/direct/>
PREFIX skos:    <http://www.w3.org/2004/02/skos/core#>
PREFIX skosxl:  <http://www.w3.org/2008/05/skos-xl#>
PREFIX gvp:     <http://vocab.getty.edu/ontology#>
SELECT DISTINCT ?parent ?parentLabel
WHERE {

{<''' + search_string + '''> wdt:P279 ?parent.
?parent rdfs:label ?parentLabel.}
UNION
{<''' + search_string + '''> gvp:broaderPreferred ?parent.
?parent skosxl:prefLabel ?l.
?l skosxl:literalForm ?parentLabel.}
UNION
{<''' + search_string + '''> skos:broader ?parent.
?parent skos:prefLabel ?parentLabel.}

filter(lang(?parentLabel)="en")
}
'''
    #print(query_string)
    #update_artworks(search_string)

    # Send the query to the endpoint
    data = Sparqler().query(query_string) # default to DEFAULT_ENDPOINT
    #print(json.dumps(data, indent=2))
    #print()
    
    if len(data) == 0: # Handle the case where there is no broader classification.
        return ('', '')
    # Note: Only Wikidata can return multiple results. The others return only one result.
    # So for the Wikidata result, only the first one will be used.
    label = data[0]['parentLabel']['value']
    iri = data[0]['parent']['value']

    return(label, iri)

def move_to_subclass(subclass_iri: str) -> None:
    """Handle the click of one of the subclass buttons"""
    # Indicate that EXISTING_SUBCLASS_BUTTONS is a global variable
    global EXISTING_SUBCLASS_BUTTONS

    #print('subclass IRI of button:', subclass_iri)

    # Determine the scheme_name from the subclass_iri
    if 'nomenclature' in subclass_iri:
        scheme_name = 'nomenclature'
    elif 'aat' in subclass_iri:
        scheme_name = 'aat'
    elif 'wikidata' in subclass_iri:
        scheme_name = 'wikidata'
    else:
        print('Error: subclass IRI does not contain a scheme name')
        sys.exit()

    # I thought it should not be necessary to set this since it's a global variable and already set. But apparently it is getting a value from some previous state.
    CURRENT_SCHEME_ORIENTATION = SCHEME_ORIENTATIONS[scheme_name]

    # Determine whether the existing broader classification is empty or not. If empty, the broader
    # button will be hidden and needs to be redisplayed.
    if CLASSIFICATION['broader'] == '':
        need_to_display_broader_button = True
    else:
        need_to_display_broader_button = False

    # Move the CLASSIFICATION and LABEL values for the former current classification to the broader classification.
    CLASSIFICATION['broader'] = CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']]
    LABEL['broader'] = LABEL[CURRENT_SCHEME_ORIENTATION['current']]

    # Change the values of the broader button to the new broader classification.
    broader_button.config(text='Broader ' + CLASSIFICATION['broader'] + '\nterm: ' + LABEL['broader'], command = lambda: parent_concept_button(scheme_name))
    if need_to_display_broader_button:
        broader_button.grid(column=2, row=1)

    # Move the values of CLASSIFICATION for the chosen subclass to the current classification.
    CLASSIFICATION[scheme_name] = subclass_iri

    # Get the label for the chosen subclass via a SPARQL query based on its subclass_iri.
    # rdfs:label for Wikidata, skos:prefLabel for nom, skosxl:prefLabel for AAT.
    # Don't specify a graph, since the labels come from various graphs.
    query_string = '''SELECT DISTINCT ?label
WHERE {
    {<''' + subclass_iri + '''> <http://www.w3.org/2004/02/skos/core#prefLabel> ?label} 
UNION
    {<''' + subclass_iri + '''> <http://www.w3.org/2000/01/rdf-schema#label> ?label}
UNION
    {<''' + subclass_iri + '''> <http://www.w3.org/2008/05/skos-xl#prefLabel> ?labelObject.
    ?labelObject <http://www.w3.org/2008/05/skos-xl#literalForm> ?label.}
FILTER (lang(?label) = "en")
}
'''
    #print(query_string)
    #print()
    label_data = Sparqler().query(query_string) # default to DEFAULT_ENDPOINT
    #print(json.dumps(label_data, indent=2))

    # Get the label from the query results
    LABEL[scheme_name] = label_data[0]['label']['value']

    # Now change the label of the current classification text box.
    current_classification_text.set(CURRENT_SCHEME_ORIENTATION['current'] + '\nterm: ' + LABEL[CURRENT_SCHEME_ORIENTATION['current']])

    # Determine the subclass list for the new main classification and create any buttons for them.
    subclass_list = retrieve_narrower_concepts(CURRENT_SCHEME_ORIENTATION['current'], CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']])        

    # Destroy the existing subclass buttons
    for button in EXISTING_SUBCLASS_BUTTONS:
        #button.grid_remove()
        button.destroy() # removes button from grid and destroys it
    EXISTING_SUBCLASS_BUTTONS = [] # Not sure if this is necessary.

    # Create new subclass buttons
    EXISTING_SUBCLASS_BUTTONS = generate_subclass_buttons(subclass_list)

    # If there are equivalent concepts, find them and change the left and right buttons. 
    # If an equivalent concept is not found, make the button invisible.
    find_equivalent_concepts_and_set_buttons(subclass_iri, CURRENT_SCHEME_ORIENTATION)

    # Update the artworks that are included in the current classification
    retrieve_included_artworks(CURRENT_SCHEME_ORIENTATION['current'], CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']])

def find_equivalent_concepts_and_set_buttons(classification_iri: str, scheme_orientation: Dict[str, str]) -> None:
    """Perform a SPARQL query to look for equivalent concepts and set the left and right buttons."""
    # Create a query string to try to get the equivalent concepts for the current scheme.
    query_string = '''SELECT DISTINCT ?o ?p ?label
FROM <https://art-classification-crosswalks>
WHERE {
<''' + classification_iri + '''> ?p ?o.
}
'''
    #print(query_string)

    # Send the query to the endpoint
    data = Sparqler().query(query_string) # default to DEFAULT_ENDPOINT
    #print(json.dumps(data, indent=2))
    #print()

    # Based on the data from the query, set the match type, concept IRI and label of the concept in the specified button position.
    for side in ['left', 'right']:
        set_equivalent_button_concept_data(scheme_orientation, data, side)

def set_equivalent_button_concept_data(scheme_orientation: Dict[str, str], data: List, button_position: str) -> None:
    """Retrieve and set the match type, concept IRI and label of the concept in the specified button position.
    """
    # Indicate that EXISTING_SUBCLASS_BUTTONS is a global variable
    global EXISTING_SUBCLASS_BUTTONS

    if CLASSIFICATION[scheme_orientation[button_position]] == '':
        need_to_display_button = True
    else:
        need_to_display_button = False

    # Keep track of whether a match was found for the side.
    found_match_for_side = False

    for equivalent in data:
        concept_iri = equivalent['o']['value'] # Get the IRI of the equivalent concept
        if scheme_orientation[button_position] in concept_iri: # Check if the scheme name is in the domain name for the given scheme
            found_match_for_side = True
            MATCH_TYPE[button_position] = equivalent['p']['value'].split('#')[1] # Match type is the local name
            #print('match type:', MATCH_TYPE[button_position])
            CLASSIFICATION[scheme_orientation[button_position]] = concept_iri
            #print('concept IRI:', concept_iri)

            # Query to get the label for the concept. rdfs:label for Wikidata, skos:prefLabel for nom, skosxl:prefLabel for AAT.
            # Don't specify a graph, since the labels come from various graphs.
            query_string = '''SELECT DISTINCT ?label
        WHERE {
            {<''' + concept_iri + '''> <http://www.w3.org/2004/02/skos/core#prefLabel> ?label} 
        UNION
            {<''' + concept_iri + '''> <http://www.w3.org/2000/01/rdf-schema#label> ?label}
        UNION
            {<''' + concept_iri + '''> <http://www.w3.org/2008/05/skos-xl#prefLabel> ?labelObject.
            ?labelObject <http://www.w3.org/2008/05/skos-xl#literalForm> ?label.}
        FILTER (lang(?label) = "en")
        }
        '''
            #print(query_string)
            #print()
            label_data = Sparqler().query(query_string) # default to DEFAULT_ENDPOINT
            #print(json.dumps(label_data, indent=2))

            # Get the label from the query results
            LABEL[scheme_orientation[button_position]] = label_data[0]['label']['value']
            #print('label:', LABEL[button_position])
            #print()

            # Set the button label to the label of the concept, then make the button visible.
            if button_position == 'left':
                left_button.config(text='Switch to ' + scheme_orientation['left'] + '\nterm: ' + LABEL[scheme_orientation['left']], command = lambda: change_scheme_button(scheme_orientation['left']))
                if need_to_display_button:
                    left_button.grid(column=1, row=2, sticky=W)
            elif button_position == 'right':
                right_button.config(text='Switch to ' + scheme_orientation['right'] + '\nterm: ' + LABEL[scheme_orientation['right']], command = lambda: change_scheme_button(scheme_orientation['right']))
                if need_to_display_button:
                    right_button.grid(column=3, row=2, sticky=W)

    if not found_match_for_side:
        # If no match was found, clear the button data.
        MATCH_TYPE[button_position] = ''
        CLASSIFICATION[scheme_orientation[button_position]] = ''
        LABEL[scheme_orientation[button_position]] = ''
        if button_position == 'left':
            left_button.grid_forget()
        elif button_position == 'right':
            right_button.grid_forget()

# ------------
# Classes
# ------------

class Sparqler:
    """Build SPARQL queries of various sorts

    Parameters
    -----------
    method: str
        Possible values are "post" (default) or "get". Use "get" if read-only query endpoint.
        Must be "post" for update endpoint.
    endpoint: URL
        Defaults to Wikidata Query Service if not provided.
    useragent : str
        Required if using the Wikidata Query Service, otherwise optional.
        Use the form: appname/v.v (URL; mailto:email@domain.com)
        See https://meta.wikimedia.org/wiki/User-Agent_policy
    session: requests.Session
        If provided, the session will be used for all queries. Note: required for the Commons Query Service.
        If not provided, a generic requests method (get or post) will be used.
        NOTE: Currently only implemented for the .query() method since I don't have any way to test the mehtods that write.
    sleep: float
        Number of seconds to wait between queries. Defaults to 0.1
        
    Required modules:
    -------------
    requests, datetime, time
    """
    def __init__(self, method=DEFAULT_METHOD, endpoint=DEFAULT_ENDPOINT, useragent=None, session=None, sleep=0.1):
        # attributes for all methods
        self.http_method = method
        self.endpoint = endpoint
        if useragent is None:
            if self.endpoint == 'https://query.wikidata.org/sparql':
                print('You must provide a value for the useragent argument when using the Wikidata Query Service.')
                print()
                raise KeyboardInterrupt # Use keyboard interrupt instead of sys.exit() because it works in Jupyter notebooks
        self.session = session
        self.sleep = sleep

        self.requestheader = {}
        if useragent:
            self.requestheader['User-Agent'] = useragent
        
        if self.http_method == 'post':
            self.requestheader['Content-Type'] = 'application/x-www-form-urlencoded'

    def query(self, query_string, form='select', verbose=False, **kwargs):
        """Sends a SPARQL query to the endpoint.
        
        Parameters
        ----------
        form : str
            The SPARQL query form.
            Possible values are: "select" (default), "ask", "construct", and "describe".
        mediatype: str
            The response media type (MIME type) of the query results.
            Some possible values for "select" and "ask" are: "application/sparql-results+json" (default) and "application/sparql-results+xml".
            Some possible values for "construct" and "describe" are: "text/turtle" (default) and "application/rdf+xml".
            See https://docs.aws.amazon.com/neptune/latest/userguide/sparql-media-type-support.html#sparql-serialization-formats-neptune-output
            for response serializations supported by Neptune.
        verbose: bool
            Prints status when True. Defaults to False.
        default: list of str
            The graphs to be merged to form the default graph. List items must be URIs in string form.
            If omitted, no graphs will be specified and default graph composition will be controlled by FROM clauses
            in the query itself. 
            See https://www.w3.org/TR/sparql11-query/#namedGraphs and https://www.w3.org/TR/sparql11-protocol/#dataset
            for details.
        named: list of str
            Graphs that may be specified by IRI in a query. List items must be URIs in string form.
            If omitted, named graphs will be specified by FROM NAMED clauses in the query itself.
            
        Returns
        -------
        If the form is "select" and mediatype is "application/json", a list of dictionaries containing the data.
        If the form is "ask" and mediatype is "application/json", a boolean is returned.
        If the mediatype is "application/json" and an error occurs, None is returned.
        For other forms and mediatypes, the raw output is returned.

        Notes
        -----
        To get UTF-8 text in the SPARQL queries to work properly, send URL-encoded text rather than raw text.
        That is done automatically by the requests module for GET. I guess it also does it for POST when the
        data are sent as a dict with the urlencoded header. 
        See SPARQL 1.1 protocol notes at https://www.w3.org/TR/sparql11-protocol/#query-operation        
        """
        query_form = form
        if 'mediatype' in kwargs:
            media_type = kwargs['mediatype']
        else:
            if query_form == 'construct' or query_form == 'describe':
            #if query_form == 'construct':
                media_type = 'text/turtle'
            else:
                media_type = 'application/sparql-results+json' # default for SELECT and ASK query forms
        self.requestheader['Accept'] = media_type
            
        # Build the payload dictionary (query and graph data) to be sent to the endpoint
        payload = {'query' : query_string}
        if 'default' in kwargs:
            payload['default-graph-uri'] = kwargs['default']
        
        if 'named' in kwargs:
            payload['named-graph-uri'] = kwargs['named']

        if verbose:
            print('querying SPARQL endpoint')

        start_time = datetime.datetime.now()
        if self.http_method == 'post':
            if self.session is None:
                response = requests.post(self.endpoint, data=payload, headers=self.requestheader)
            else:
                response = self.session.post(self.endpoint, data=payload, headers=self.requestheader)
        else:
            if self.session is None:
                response = requests.get(self.endpoint, params=payload, headers=self.requestheader)
            else:
                response = self.session.get(self.endpoint, params=payload, headers=self.requestheader)
        elapsed_time = (datetime.datetime.now() - start_time).total_seconds()
        self.response = response.text
        time.sleep(self.sleep) # Throttle as a courtesy to avoid hitting the endpoint too fast.

        if verbose:
            print('done retrieving data in', int(elapsed_time), 's')

        if query_form == 'construct' or query_form == 'describe':
            return response.text
        else:
            if media_type != 'application/sparql-results+json':
                return response.text
            else:
                try:
                    data = response.json()
                except:
                    return None # Returns no value if an error. 

                if query_form == 'select':
                    # Extract the values from the response JSON
                    results = data['results']['bindings']
                else:
                    results = data['boolean'] # True or False result from ASK query 
                return results           

    def update(self, request_string, mediatype='application/json', verbose=False, **kwargs):
        """Sends a SPARQL update to the endpoint.
        
        Parameters
        ----------
        mediatype : str
            The response media type (MIME type) from the endpoint after the update.
            Default is "application/json"; probably no need to use anything different.
        verbose: bool
            Prints status when True. Defaults to False.
        default: list of str
            The graphs to be merged to form the default graph. List items must be URIs in string form.
            If omitted, no graphs will be specified and default graph composition will be controlled by USING
            clauses in the query itself. 
            See https://www.w3.org/TR/sparql11-update/#deleteInsert
            and https://www.w3.org/TR/sparql11-protocol/#update-operation for details.
        named: list of str
            Graphs that may be specified by IRI in the graph pattern. List items must be URIs in string form.
            If omitted, named graphs will be specified by USING NAMED clauses in the query itself.
        """
        media_type = mediatype
        self.requestheader['Accept'] = media_type
        
        # Build the payload dictionary (update request and graph data) to be sent to the endpoint
        payload = {'update' : request_string}
        if 'default' in kwargs:
            payload['using-graph-uri'] = kwargs['default']
        
        if 'named' in kwargs:
            payload['using-named-graph-uri'] = kwargs['named']

        if verbose:
            print('beginning update')
            
        start_time = datetime.datetime.now()
        response = requests.post(self.endpoint, data=payload, headers=self.requestheader)
        elapsed_time = (datetime.datetime.now() - start_time).total_seconds()
        self.response = response.text
        time.sleep(self.sleep) # Throttle as a courtesy to avoid hitting the endpoint too fast.

        if verbose:
            print('done updating data in', int(elapsed_time), 's')

        if media_type != 'application/json':
            return response.text
        else:
            try:
                data = response.json()
            except:
                return None # Returns no value if an error converting to JSON (e.g. plain text) 
            return data           

    def load(self, file_location, graph_uri, s3='', verbose=False, **kwargs):
        """Loads an RDF document into a specified graph.
        
        Parameters
        ----------
        s3 : str
            Name of an AWS S3 bucket containing the file. Omit load a generic URL.
        verbose: bool
            Prints status when True. Defaults to False.
        
        Notes
        -----
        The triplestore may or may not rely on receiving a correct Content-Type header with the file to
        determine the type of serialization. Blazegraph requires it, AWS Neptune does not and apparently
        interprets serialization based on the file extension.
        """
        if s3:
            request_string = 'LOAD <https://' + s3 + '.s3.amazonaws.com/' + file_location + '> INTO GRAPH <' + graph_uri + '>'
        else:
            request_string = 'LOAD <' + file_location + '> INTO GRAPH <' + graph_uri + '>'
        
        if verbose:
            print('Loading file:', file_location, ' into graph: ', graph_uri)
        data = self.update(request_string, verbose=verbose)
        return data

    def drop(self, graph_uri, verbose=False, **kwargs):
        """Drop a specified graph.
        
        Parameters
        ----------
        verbose: bool
            Prints status when True. Defaults to False.
        """
        request_string = 'DROP GRAPH <' + graph_uri + '>'

        if verbose:
            print('Deleting graph:', graph_uri)
        data = self.update(request_string, verbose=verbose)
        return data
    

# ------------
# Set up GUI
# ------------

root = Tk()

# this sets up the characteristics of the window
root.title("SPARQL Explorer GUI")

# Create a frame object for the main window
mainframe = Frame(root)
mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
mainframe.columnconfigure(0, weight=1)
mainframe.rowconfigure(0, weight=1)

# Create a label object for instructions
#instruction_text = StringVar()
#Label(mainframe, textvariable=instruction_text).grid(column=3, row=10, sticky=(W, E))
#instruction_text.set('Enter SELECT query below and click the "Send Query" button')

# Create a text box object for the SPARQL query, 100 characters wide and 25 lines high
#query_text_box = Text(mainframe, width=100, height=1)
#query_text_box.grid(column=3, row=11, sticky=(W, E))

# Insert the generic query text
#query_text_box.insert(END, PREFIXES + 'http://www.wikidata.org/entity/Q613972')

current_classification_text = StringVar()
Label(mainframe, textvariable=current_classification_text).grid(column=2, row=2, sticky=(W, E))
current_classification_text.set(CURRENT_SCHEME_ORIENTATION['current'] + '\nterm: ' + LABEL[CURRENT_SCHEME_ORIENTATION['current']])

results_text = StringVar()
Label(mainframe, textvariable=results_text).grid(column=3, row=3, sticky=(W, E))
results_text.set('Click a subclass button below')

# Create a scrolling text box to display the subclasses

#subclass_list_box = tkst.ScrolledText(master = mainframe, width  = 100, height = 25)
# The padx/pady space will form a frame.
#subclass_list_box.grid(column=2, row=3, padx=8, pady=8)
#subclass_list_box.insert(END, '')

#def update_subclasses_box(result):
    #print(result)
#    subclass_list_box.delete('1.0', END)
#    subclass_list_box.insert(INSERT, result + '\n')
    #subclass_list_box.see(END) #causes scroll up as text is added
#    root.update_idletasks() # causes update to log window, see https://stackoverflow.com/questions/6588141/update-a-tkinter-text-widget-as-its-written-rather-than-after-the-class-is-fini

# Get the subclasses for the current classification, then display them.

subclass_list = retrieve_narrower_concepts(CURRENT_SCHEME_ORIENTATION['current'], CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']])
#subclass_string = ''
#for subclass in subclass_list:
#    subclass_string += subclass['label'] + ' ' + subclass['iri'] + '\n'
#update_subclasses_box(subclass_string)

def generate_subclass_buttons(subclass_list: List[Dict[str, str]]) -> List[Button]:
    """Generate buttons for the subclasses of the current classification."""
    subclass_buttons = []
    for index, subclass in enumerate(subclass_list):
        # Need to pass the subclass IRI by value, not by reference, so it will be the value at the time the button is created.
        button = Button(mainframe, text = subclass['label'] + '\nterm: ' + subclass['iri'], width = 30, command = lambda subclass_iri=subclass['iri']: move_to_subclass(subclass_iri) )
        #button = Button(mainframe, text = subclass['label'] + '\nterm: ' + subclass['iri'], width = 30, command = lambda: move_to_subclass(subclass['iri']) )
        button.grid(column=3, row=index+4)
        subclass_buttons.append(button)
    return subclass_buttons

EXISTING_SUBCLASS_BUTTONS = generate_subclass_buttons(subclass_list) # Pass in an emtpy list for the subclass buttons at first.

# Generate buttons after the subclass buttons are created.
broader_button = Button(mainframe, text = 'Broader ' + CURRENT_SCHEME_ORIENTATION['current'] + '\nterm: ' + LABEL['broader'], width = 30, command = lambda: parent_concept_button(CURRENT_SCHEME_ORIENTATION['current']) )
broader_button.grid(column=2, row=1)

left_button = Button(mainframe, text = 'Switch to ' + CURRENT_SCHEME_ORIENTATION['left'] + '\nterm: ' + LABEL[CURRENT_SCHEME_ORIENTATION['left']], width = 30, command = lambda: change_scheme_button(CURRENT_SCHEME_ORIENTATION['left']) )
left_button.grid(column=1, row=2, sticky=W)

right_button = Button(mainframe, text = 'Switch to ' + CURRENT_SCHEME_ORIENTATION['right'] + '\nterm: ' + LABEL[CURRENT_SCHEME_ORIENTATION['right']], width = 30, command = lambda: change_scheme_button(CURRENT_SCHEME_ORIENTATION['right']) )
right_button.grid(column=3, row=2, sticky=W)

results_text = StringVar()
Label(mainframe, textvariable=results_text).grid(column=1, row=3, sticky=(W, E))
results_text.set('Items in collection (at right)')

# Scrolling text box hacked from https://www.daniweb.com/programming/software-development/code/492625/exploring-tkinter-s-scrolledtext-widget-python
artworks_list = tkst.ScrolledText(master = mainframe, width  = 100, height = 25)
# the padx/pady space will form a frame
artworks_list.grid(column=2, row=3, padx=8, pady=8)
artworks_list.insert(END, '')

def update_artworks(result):
    #print(result)
    artworks_list.delete('1.0', END)
    artworks_list.insert(INSERT, result + '\n')
    #artworks_list.see(END) #causes scroll up as text is added
    root.update_idletasks() # causes update to log window, see https://stackoverflow.com/questions/6588141/update-a-tkinter-text-widget-as-its-written-rather-than-after-the-class-is-fini

retrieve_included_artworks(CURRENT_SCHEME_ORIENTATION['current'], CLASSIFICATION[CURRENT_SCHEME_ORIENTATION['current']])

def main():	
    root.mainloop()
	
if __name__=="__main__":
	main()
