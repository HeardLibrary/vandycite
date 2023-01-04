from langdetect import detect_langs
from fuzzywuzzy import fuzz # fuzzy logic matching
from datetime import datetime
import requests
from time import sleep
import re # regex
import logging
import pandas as pd
from typing import List, Dict, Tuple
#import requests_cache

#requests_cache.install_cache('wqs_cache', backend='sqlite', expire_after=300, allowable_methods=['GET', 'POST'])

# ------------------------
# Utility functions
# ------------------------

# The following function is needed by the calculate_pages function
def roman_to_decimal(numeral: str) -> int:
    """Convert Roman numerals to integers.
    
    Note:
    -----
    Code from https://www.geeksforgeeks.org/python-program-for-converting-roman-numerals-to-decimal-lying-between-1-to-3999/"""

    def roman_integer_value(char: str) -> int:
        """Return value of Roman numeral symbol.

        Note:
        -----
        Code from https://www.geeksforgeeks.org/python-program-for-converting-roman-numerals-to-decimal-lying-between-1-to-3999/"""    
        if (char == 'I'):
            return 1
        if (char == 'V'):
            return 5
        if (char == 'X'):
            return 10
        if (char == 'L'):
            return 50
        if (char == 'C'):
            return 100
        if (char == 'D'):
            return 500
        if (char == 'M'):
            return 1000
        return -1

    str = numeral.upper()
    res = 0
    i = 0

    while (i < len(str)):

        # Getting value of symbol s[i]
        s1 = roman_integer_value(str[i])
        
        # Return a negative number if error.
        if s1 < 0:
            return -1

        if (i + 1 < len(str)):

            # Getting value of symbol s[i + 1]
            s2 = roman_integer_value(str[i + 1])
            
            # Return a negative number if error.
            if s2 < 0:
                return -1

            # Comparing both values
            if (s1 >= s2):

                # Value of current symbol is greater
                # or equal to the next symbol
                res = res + s1
                i = i + 1
            else:

                # Value of current symbol is greater
                # or equal to the next symbol
                res = res + s2 - s1
                i = i + 2
        else:
            res = res + s1
            i = i + 1

    return res

def include_reference_url(url: str, full_works: pd.DataFrame) -> str:
    """Returned strings are suitable to use for references (same criteria as full work available)."""
    url_pattern = "^https?:\\/\\/(?:www\\.)?[-a-zA-Z0-9@:%._\\+~#=]{1,256}\\.[a-zA-Z0-9()]{1,6}\\b(?:[-a-zA-Z0-9()@:%_\\+.~#?&\\/=]*)$"
    url_inclusion_strings = [
    'doi',
    'jstor',
    #'oxfordjournals.org/content',
    'article',
    'academia.edu',
    'content',
    'proquest.com/docview',
    'handle'
    ]
    
    url_exclusion_strings = [
    'login',
    'proxy',
    #'search.proquest.com',
    'worldcat',
    'wp-content',
    'site.ebrary.com',
    'cro3.org/',
    'worldbookonline.com/pl/infofinder'
    ]

    url = url.lower() # convert to all lowercase
    
    # Exclude invalid URLs
    if re.match(url_pattern, url) is None:
        return ''

    # If the URL matches one of the pre-screened URLs, use it
    matched_series = full_works.loc[full_works['Url']==url, 'Url']
    # matched_series will be a Series composed of all values in the Url column that match. There should be 1 or 0.
    if len(matched_series) == 1:
        return url
    
    # Exclude any URLs containing strings that indicate a login is required
    for screening_string in url_exclusion_strings:
        if screening_string in url:
            return ''
        
    # Must contain one of the strings that indicate metadata and possible acces
    for screening_string in url_inclusion_strings:
        if screening_string in url:
            return url
        
    return ''

def fix_all_caps(name_pieces: List[str]) -> List[str]:
    """Correct the capitalization for a list of name parts that are in all caps."""

    def title_if_no_lowercase(string: str) -> str:
        """Change to titlecase only if there are no lowercase letters in the string."""
        lower = 'abcdefghijklmnopqrstuvwxyz'
        is_lower = False
        for letter in string:
            if letter in lower:
                is_lower = True
        if is_lower:
            return string
        else:
            return string.title()

    clean_pieces = []
    for piece in name_pieces:
        # Special handing for names starting with apostrophe-based prefixes
        apostrophe_list = ["van't", "'t", "O'", "D'", "d'", "N'"]
        apostrophe_prefix = ''
        for possible_apostrophe_prefix in apostrophe_list:
            if possible_apostrophe_prefix in piece:
                # Remove prefix
                piece = piece.replace(possible_apostrophe_prefix, '')
                apostrophe_prefix = possible_apostrophe_prefix
        
        # Special handling for name parts that are lowercase
        lower_case_list = ['von', 'de', 'van', 'la', 'der']
        if piece.lower() in lower_case_list:
            piece = piece.lower()
        else:
            # Special handling for hyphenated names; doesn't work for an edge case with more than 2 hyphens
            if '-' in piece:
                halves = piece.split('-')
                piece = title_if_no_lowercase(halves[0]) + '-' + title_if_no_lowercase(halves[1])
            else:
                piece = title_if_no_lowercase(piece)
        
        # put any apostrophe prefix back on the front
        if apostrophe_prefix:
            piece = apostrophe_prefix + piece
        
        clean_pieces.append(piece)
    return clean_pieces
  
# ------------------------
# SPARQL query class
# ------------------------

# This is a condensed version of the more full-featured script at 
# https://github.com/HeardLibrary/digital-scholarship/blob/master/code/wikidata/sparqler.py
# It includes only the method for the query form.

class Sparqler:

    def __init__(self, method='post', endpoint='https://query.wikidata.org/sparql', useragent=None, sleep=0.1):
        """Build SPARQL queries of various sorts

        Parameters
        -----------
        useragent : str
            Required if using the Wikidata Query Service, otherwise optional.
            Use the form: appname/v.v (URL; mailto:email@domain.com)
            See https://meta.wikimedia.org/wiki/User-Agent_policy
        endpoint: URL
            Defaults to Wikidata Query Service if not provided.
        method: str
            Possible values are "post" (default) or "get". Use "get" if read-only query endpoint.
            Must be "post" for update endpoint.
        sleep: float
            Number of seconds to wait between queries. Defaults to 0.1
            
        Required modules:
        -------------
        requests, datetime, time
        """
        # attributes for all methods
        self.http_method = method
        self.endpoint = endpoint
        if useragent is None:
            if self.endpoint == 'https://query.wikidata.org/sparql':
                print('You must provide a value for the useragent argument when using the Wikidata Query Service.')
                print()
                raise KeyboardInterrupt # Use keyboard interrupt instead of sys.exit() because it works in Jupyter notebooks
        self.sleep = sleep

        self.requestheader = {}
        if useragent:
            self.requestheader['User-Agent'] = useragent
        
        if self.http_method == 'post':
            self.requestheader['Content-Type'] = 'application/x-www-form-urlencoded'

    def query(self, query_string, form='select', verbose=False, **kwargs):
        """Send a SPARQL query to the endpoint.
        
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

        start_time = datetime.now()
        if self.http_method == 'post':
            response = requests.post(self.endpoint, data=payload, headers=self.requestheader)
        else:
            response = requests.get(self.endpoint, params=payload, headers=self.requestheader)
        #print('from cache:', response.from_cache) # uncomment if you want to see if cached data are used
        elapsed_time = (datetime.now() - start_time).total_seconds()
        self.response = response.text
        sleep(self.sleep) # Throttle as a courtesy to avoid hitting the endpoint too fast.

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

# ------------------------
# mapping functions
# ------------------------

def identity(value: str, settings: Dict[str, any]) -> str:
    """Return the value argument with any leading and trailing whitespace removed."""
    return value.strip()

def set_instance_of(string: str, settings: Dict[str, any]) -> str:
    """Match the type string with possible types for the data source and return the type Q ID."""
    if string == '':
        return ''

    for work_type in settings['work_types']:
        if string == work_type['type_string']:
            return work_type['qid']

    print('Cannot set instance_of, did not find datatype for type:', string)
    #error_log_string += 'Did not find datatype for type:' + string + '\n'
    logging.warning('Cannot set instance_of, did not find datatype for type:' + string)
    return ''

def detect_language(string: str, settings: Dict[str, any]) -> str:
    """Detect the language of the label and return the Wikidata Q ID for it."""
    if string == '':
        return ''
    try:
        lang_list = detect_langs(string)
        lang_string = str(lang_list[0])
        confidence = float(lang_string[3:])
        lang = lang_string[:2]
    except: #exceptions occur when no info to decide, e.g. numbers
        lang = 'zxx'
        confidence = float(0)
    if confidence < settings['language_precision_cutoff']:
        print('Warning: language confidence for', lang, 'below', settings['language_precision_cutoff'], ':', confidence)
        #error_log_string += 'Warning: language confidence for ' + lang + ' below ' + str(settings['language_precision_cutoff']) + ': ' + str(confidence) + '\n'
        logging.warning('Warning: language confidence for ' + lang + ' below ' + str(settings['language_precision_cutoff']) + ': ' + str(confidence))
    if lang in settings['language_qid']:
        return settings['language_qid'][lang]
    else:
        print('Warning: detected language', lang, 'not in list of known languages.')
        #error_log_string += 'Warning: detected language ' + lang + ' not in list of known languages.\n'
        logging.warning('Warning: detected language ' + lang + ' not in list of known languages.')
        return ''

def title_en(string: str, settings: Dict[str, any]) -> str:
    """Detect the language of the label and return the language code for it."""
    if string == '':
        return ''
    try:
        lang_list = detect_langs(string)
        lang_string = str(lang_list[0])
        confidence = float(lang_string[3:])
        lang = lang_string[:2]
    except: #exceptions occur when no info to decide, e.g. numbers
        lang = 'zxx'
        confidence = float(0)
    if lang == 'en':
        return string
    else:
        return ''

def calculate_pages(range: str, settings: Dict[str, any]) -> str:
    """Calculate the number of pages from the page range.
    
    Note
    ----
    Supports properly formatted Roman numerals and doesn't care about whitespace."""
    if range == '':
        return ''
    numbers = range.split('-')
    
    # If there is only a single number or an empty cell, return the empty string.
    if len(numbers) < 2:
        return ''
    # Edge case where it isn't a well-formed range and has multiple hyphens
    if len(numbers) > 2:
        return ''
    
    # Step through the two numbers to try to convert them from Roman numerals if not integers.
    for index, number in enumerate(numbers):
        number = number.strip()
        if not number.isnumeric():
            numbers[index] = roman_to_decimal(number)
            
            # Will return -1 error if it contains characters not valid for Roman numerals 
            if numbers[index] < 0:
                return ''
    
    number_pages = int(numbers[1]) - int(numbers[0]) + 1 # Need to add one since first page in range counts
    if number_pages < 1:
        return ''
    return str(number_pages)

def clean_doi(value: str, settings: Dict[str, any]) -> str:
    """Turn DOI into uppercase and remove leading and trailing whitespace."""
    cleaned_value = value.upper().strip()
    return cleaned_value

def extract_pmid_from_extra(extra_field, settings: Dict[str, any]) -> str:
    """Extract the PubMed ID from the Extra field in the Zotero export."""
    identifier = ''
    tokens = extra_field.split(' ')
    for token_index in range(len(tokens)):
        if tokens[token_index] == 'PMID:': # match the tag for PMID
            # The identifer is the next token after the tag
            identifier = tokens[token_index + 1]
            break
    return identifier

def disambiguate_published_in(value: str, settings: Dict[str, any]) -> str:
    """Use the value in the ISSN column to try to find the containing work.
    
    Note:
    -----
    For journal articles, this performs a legitimate WQS search for the journal title using the ISSN.
    For book chapters, the ISSN column may contain the Q ID of the containing book, inserted there during
    a pre-processing step (a hack, but typically books would not have an ISSN and this column would be empty)."""
    if value == '':
        return value
    
    # The value is a Q ID and was determined during a pre-processing step (i.e. for book chapters)
    if value[0] == 'Q':
        return value

    # Look up the ISSN in Wikidata
    # Build query string
    query_string = '''select distinct ?container ?containerLabel where {
      ?container wdt:P236 "''' + value + '''".
      optional {
      ?container rdfs:label ?containerLabel.
      filter(lang(?containerLabel)="en")
      }
    }'''
    #print(query_string)

    user_agent = 'PubLoader/' + settings['script_version'] + ' (mailto:' + settings['operator_email_address'] + ')'
    wdqs = Sparqler(useragent=user_agent)
    query_results = wdqs.query(query_string)
    sleep(settings['sparql_sleep'])
    
    if len(query_results) == 0:
        return ''

    if len(query_results) > 1:
        print('Warning! More than one container in Wikidata matched the ISSN ')
        #error_log_string += 'Warning! More than one container in Wikidata matched the ISSN\n'
        logging.warning('Warning! More than one container in Wikidata matched the ISSN')
        print(query_results, '\n')
        #error_log_string += str(query_results) + '\n'
        logging.warning(str(query_results))

    # Extract Q ID from SPARQL query results. If there is more than one result, the last one will be used for the Q ID
    for result in query_results:
        container_qid = result['container']['value'].split('/')[-1] # extract the local name from the IRI

    return container_qid

def isbn10(string: str, settings: Dict[str, any]) -> str:
    """Check whether the ISBN value has 10 characters or not."""
    test = string.replace('-', '')
    if len(test) == 10:
        return string
    return ''

def isbn13(string: str, settings: Dict[str, any]) -> str:
    """Check whether the ISBN value has 13 characters or not."""
    test = string.replace('-', '')
    if len(test) == 13:
        return string
    return ''

def disambiguate_publisher(name_string: str, settings: Dict[str, any], publishers: pd.DataFrame) -> str:
    """Look up the publisher Q ID from a list derived from a SPARQL query https://w.wiki/4pbi"""
    # Set publisher Q ID to empty string if there's no publisher string
    if name_string == '':
        return ''
    
    best_match_score = 0
    best_match = ''
    best_match_label = ''
    for qid, publisher in publishers.iterrows():
        w_ratio = fuzz.WRatio(name_string, publisher['label'])
        if w_ratio > best_match_score:
            best_match = qid
            best_match_label = publisher['label']
            best_match_score = w_ratio
            
    # empiracally determined range for possible matches is > 86 and < 98
    if best_match_score <= 86:
        print('w_ratio:', best_match_score, 'Warning: No match for stated publisher: "' + name_string + '"\n')
        logging.warning('w_ratio: ' + str(best_match_score) + ' Warning: no match for stated publisher: "' + name_string + '"')
        return ''

    elif best_match_score < 98:
        print('w_ratio:', best_match_score, 'Warning: poor match of: "' + best_match_label + '"', best_match, 'to stated publisher: "' + name_string + '"\n')
        logging.warning('w_ratio: ' + str(best_match_score) + ' Warning: poor match of: "' + best_match_label + '" ' + best_match + ' to stated publisher: "' + name_string + '"')
        
    return best_match

def disambiguate_place_of_publication(value: str, settings, publisher_locations: pd.DataFrame) -> str:
    """Look up place of publication Q ID from a list derived from query https://w.wiki/63Ap
    If there is a single match, the Q ID is returned.
    If there are no matches, the string is returned unprocessed.
    If there are multiple matches, a dict with possible values is returned."""
    if value == '':
        return ''
    
    if 'New York' in value:
        return 'Q60'
    
    if 'New Brunswick' in value:
        return 'Q138338'
    
    if 'California' in value:
        value = value.replace('California', 'CA')
    
    if 'Calif' in value:
        value = value.replace('Calif', 'CA')
        
    if 'Massachusetts' in value:
        value = value.replace('Massachusetts', 'MA')
        
    if 'Cambridge' in value:
        if 'Cambridge, M' in value:
            return 'Q49111'
        else:
            return 'Q350'
    
    location_list = []
    for qid, location in publisher_locations.iterrows():
        if location['label'] in value:
            location_list.append({'qid': qid, 'label': location['label']})
    if len(location_list) == 0:
        #error_log_string += value + ' not found in place list.\n'
        logging.warning(value + ' not found in place list.')
        return value
    
    elif len(location_list) == 1:
        return location_list[0]['qid']
    else:
        #error_log_string += 'Multiple matches found in place list.' + str(location_list) + '\n'
        logging.warning('Multiple matches found in place list.' + str(location_list))
        return location_list

def today(settings: Dict[str, any]) -> str:
    """Generate the current UTC xsd:date"""
    whole_time_string_z = datetime.utcnow().isoformat() # form: 2019-12-05T15:35:04.959311
    date_z = whole_time_string_z.split('T')[0] # form 2019-12-05
    return date_z

def set_reference(input_url: str, settings: Dict[str, any], full_works: pd.DataFrame) -> str:
    """Screen any URL that is present in the field for suitability as the reference URL value."""
    url = include_reference_url(input_url, full_works) # Screen for suitable URLs
    if url != '':
        return url
    else:
        return ''

def set_stated_in(input_url: str, settings: Dict[str, any], full_works: pd.DataFrame) -> str:
    """If no URL is present, set a fixed value to be used as the stated_in value."""
    url = include_reference_url(input_url, full_works) # Screen for suitable URLs
    if url == '':
        return 'Q114403967' # Vanderbilt Divinity publications database
    else:
        return ''

def extract_names_from_list(names_string: str, settings: Dict[str, any]) -> str:
    """Extract multiple authors from a character-separated list in a single string."""
    if names_string == '':
        return []
    
    names_list = names_string.split(settings['names_separator'])
    
    output_list = []
    # If names are last name first
    if settings['name_part_separator']:
        for name in names_list:
            pieces = name.split(settings['name_part_separator'])
            # Keep removing empty strings until there aren't any more
            while '' in pieces:
                pieces.remove('')
            if len(pieces) == 1: # an error, name wasn't reversed
                print('Name error:', names_string)
                #mapping_functions.error_log_string += 'Name error: ' + names_string + '\n'
                logging.warning('Name error: ' + names_string)
                surname_pieces = []
                given_pieces = []
                suffix = ''
            elif len(pieces) == 2: # no Jr.
                surname_pieces, suffix = extract_name_pieces(pieces[0].strip())
                given_pieces, dummy = extract_name_pieces(pieces[1].strip())
            elif len(pieces) == 3: # has Jr.
                # Note Jr. is handled inconsistently, sometimes placed after entire name, sometimes after surname
                if 'Jr' in pieces[2]:
                    surname_pieces, suffix = extract_name_pieces(pieces[0].strip() + ', ' + pieces[2].strip())
                    given_pieces, dummy = extract_name_pieces(pieces[1].strip())
                else:
                    surname_pieces, suffix = extract_name_pieces(pieces[0].strip() + ', ' + pieces[1].strip())
                    given_pieces, dummy = extract_name_pieces(pieces[2].strip())                    
            else:
                print('Name error:', names_string)
                #mapping_functions.error_log_string += 'Name error: ' + names_string + '\n'
                logging.warning('Name error: ' + names_string)
                surname_pieces = []
                given_pieces = []
                suffix = ''
                
            surname = ' '.join(surname_pieces)
            given = ' '.join(given_pieces)
            output_list.append({'orcid': '', 'givenName': given, 'familyName': surname, 'suffix': suffix, 'affiliation': []})
    else:
        pass # need to write code for case where they aren't reversed
        
    return output_list


# ------------------------
# mapping functions for agents
# ------------------------
    
def extract_names_from_list(names_string: str, settings: Dict[str, any]) -> List[Dict[str, str]]:
    """Extract multiple authors from a character-separated list in a single string."""

    def extract_name_pieces(name: str) -> Tuple[List[str], str]:
        """Extract parts of names. Recognize typical male suffixes. Fix ALL CAPS if present."""
        # treat commas as if they were spaces
        name = name.replace(',', ' ')
        # get rid of periods, sometimes periods are close up with no spaces
        name = name.replace('.', ' ')

        pieces = name.split(' ')
        while '' in pieces:
            pieces.remove('')
        
        # Remove ", Jr.", "III", etc. from end of name
        if pieces[len(pieces)-1] == 'Jr':
            pieces = pieces[0:len(pieces)-1]
            suffix = ', Jr.'
        elif pieces[len(pieces)-1] == 'II':
            pieces = pieces[0:len(pieces)-1]
            suffix = ' II'
        elif pieces[len(pieces)-1] == 'III':
            pieces = pieces[0:len(pieces)-1]
            suffix = ' III'
        elif pieces[len(pieces)-1] == 'IV':
            pieces = pieces[0:len(pieces)-1]
            suffix = ' IV'
        elif pieces[len(pieces)-1] == 'V':
            pieces = pieces[0:len(pieces)-1]
            suffix = ' V'
        elif len(pieces) > 3 and pieces[len(pieces)-2] == 'the' and pieces[len(pieces)-1] == 'elder':
            pieces = pieces[0:len(pieces)-2]
            suffix = ' the elder'
        else:
            suffix = ''
            
        # Fix stupid situation where name is written in ALL CAPS
        pieces = fix_all_caps(pieces)
        return pieces, suffix

    if names_string == '':
        return []
    
    names_list = names_string.split(settings['names_separator'])
    
    output_list = []
    # If names are last name first
    if settings['name_part_separator']:
        for name in names_list:
            pieces = name.split(settings['name_part_separator'])
            # Keep removing empty strings until there aren't any more
            while '' in pieces:
                pieces.remove('')
            if len(pieces) == 1: # an error, name wasn't reversed
                print('Name error:', names_string)
                #mapping_functions.error_log_string += 'Name error: ' + names_string + '\n'
                logging.warning('Name error: ' + names_string)
                surname_pieces = []
                given_pieces = []
                suffix = ''
            elif len(pieces) == 2: # no Jr.
                surname_pieces, suffix = extract_name_pieces(pieces[0].strip())
                given_pieces, dummy = extract_name_pieces(pieces[1].strip())
            elif len(pieces) == 3: # has Jr.
                # Note Jr. is handled inconsistently, sometimes placed after entire name, sometimes after surname
                if 'Jr' in pieces[2]:
                    surname_pieces, suffix = extract_name_pieces(pieces[0].strip() + ', ' + pieces[2].strip())
                    given_pieces, dummy = extract_name_pieces(pieces[1].strip())
                else:
                    surname_pieces, suffix = extract_name_pieces(pieces[0].strip() + ', ' + pieces[1].strip())
                    given_pieces, dummy = extract_name_pieces(pieces[2].strip())                    
            else:
                print('Name error:', names_string)
                #mapping_functions.error_log_string += 'Name error: ' + names_string + '\n'
                logging.warning('Name error: ' + names_string)
                surname_pieces = []
                given_pieces = []
                suffix = ''
                
            surname = ' '.join(surname_pieces)
            given = ' '.join(given_pieces)
            output_list.append({'orcid': '', 'givenName': given, 'familyName': surname, 'suffix': suffix, 'affiliation': []})
    else:
        pass # need to write code for case where they aren't reversed
        
    
    return output_list

