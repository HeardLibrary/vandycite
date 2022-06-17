import boto3
import json
import csv
import io
import urllib3
from time import sleep
import datetime
import pickle

# -----------------
# utility functions
# -----------------

def generate_utc_date():
    """Parses the xsd:date from the UTC xsd:dateTime"""
    whole_time_string_z = datetime.datetime.utcnow().isoformat() # form: 2019-12-05T15:35:04.959311
    date_z = whole_time_string_z.split('T')[0] # form 2019-12-05
    return date_z

def extract_localname(iri):
    """Parse the local name from an IRI"""
    pieces = iri.split('/')
    return pieces[len(pieces)-1] # return the last piece

def generate_header_dictionary():
    """Generate HTTP request header dictionary for Accept=JSON and a custom User-Agent string"""
    accept_media_type = 'application/json'
    user_agent_header = 'StatsRetrieverLambda/0.1 (mailto:steve.baskauf@vanderbilt.edu)'
    request_header_dictionary = {
        'Accept' : accept_media_type,
        'User-Agent': user_agent_header
    }
    return request_header_dictionary

def load_file(filename, path='', bucket='baskauf-lambda-input', format='string'):
    """Loads text from a file in an S3 bucket and returns a UTF-8 string that is the file contents."""
    s3in = boto3.resource('s3') # s3 object
    in_bucket = s3in.Bucket(bucket) # bucket object
    s3_path = path + filename
    in_file = in_bucket.Object(s3_path) # file object
    file_bytes = in_file.get()['Body'].read() # this inputs all the text in the file as bytes
    if format == 'string':
        return file_bytes.decode('utf-8') # turns the bytes into a UTF-8 string
    else:
        return file_bytes

def load_credential(filename):
    """Loads the GitHub token from a pickle (binary) file and converts it to text."""
    bytes_like_object = load_file(filename, format='bytes') # format kwarg prevents the loader from converting to UTF-8
    cred = pickle.loads(bytes_like_object) # This is the pickle method to un-pickle a bytes-like object.
    return cred
    
def save_string_to_file_in_bucket(text_string, filename, content_type='text/csv', path='', bucket='disc-dashboard-data'):
    s3_path = path + filename
    s3_resource = boto3.resource('s3')
    s3_resource.Object(bucket, s3_path).put(Body=text_string, ContentType=content_type)

def get_request(url, headers=None, params=None):
    """Performs an HTTP GET from a URL and returns the response body as UTF-8 text, or None if not status 200."""
    if headers is None:
        http = urllib3.PoolManager()
    else:
        http = urllib3.PoolManager(headers=headers)
    if params is None:
        response = http.request('GET', url)
    else:
        response = http.request('GET', url, fields=params)
    if response.status == 200:
        response_body = response.data.decode('utf-8')
    else:
        response_body = None
    return response_body
    
def read_string_to_dicts(text_string):
    """Converts a single CSV text string into a list of dicts"""
    file_text = text_string.split('\n')
    file_rows = csv.DictReader(file_text)
    table = []
    for row in file_rows:
        table.append(row)
    return table

def read_string_to_lists(text_string):
    """Converts a single CSV text string into a list of lists"""
    file_text = text_string.split('\n')
    # remove any trailing newlines
    if file_text[len(file_text)-1] == '':
        file_text = file_text[0:len(file_text)-1]
    file_rows = csv.reader(file_text)
    table = []
    for row in file_rows:
        table.append(row)
    return table

def write_dicts_to_string(table, fieldnames):
    """Write a list of dictionaries to a single string representing a CSV file"""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in table:
        writer.writerow(row)
    return output.getvalue()

def write_lists_to_string(table):
    """Write a list of lists to a single string representing a CSV file"""
    output = io.StringIO()
    writer = csv.writer(output)
    for row in table:
        writer.writerow(row)
    return output.getvalue()

# -----------------
# functions for interacting with APIs
# -----------------

def get_single_value(query, sparql_sleep=0.1):
    """Sends a query to a SPARQL endpoint and extracts "single_value" from the query results."""
    endpoint_url = 'https://query.wikidata.org/sparql'
    response = get_request(endpoint_url, headers=generate_header_dictionary(), params={'query' : query})
    if response is None:
        value = None
    else:
        try:
            data = json.loads(response)
            value = data['results']['bindings'][0]['single_value']['value']
        except:
            value = None
    # delay to avoid hitting the SPARQL endpoint to rapidly
    sleep(sparql_sleep)
    return value

def get_unit_counts(query, sparql_sleep=0.1):
    """Sends a query to the WDQS SPARQL endpoint that searches for counts related to all subsidiary units of Vanderbilt. 
    Returns a list of dictionaries with the Q ID and count for each unit.
    """
    table = []
    endpoint_url = 'https://query.wikidata.org/sparql'
    response = get_request(endpoint_url, headers=generate_header_dictionary(), params={'query' : query})
    if response is None:
        table = None
    else:
        try:
            data = json.loads(response)
            statements = data['results']['bindings']
            for statement in statements:
                unit_iri = statement['unit']['value']
                unit_qnumber = extract_localname(unit_iri)
                count = statement['count']['value']
                table.append({'unit': unit_qnumber, 'count': count})
        except:
            table = None
    # delay to avoid hitting the SPARQL endpoint to rapidly
    sleep(sparql_sleep)
    return table

def get_xtools_edit_counts(username, project, namespace, api_sleep=0.1):
    """Sends a query to the XTools Edit Counter and returns a single value."""
    query_url = 'https://xtools.wmflabs.org/api/user/simple_editcount/' + project + '/' + username + '/' + namespace
    response = get_request(query_url, headers=generate_header_dictionary())
    if response is None:
        value = None
    else:
        try:
            data = json.loads(response)
            value = data['live_edit_count']
        except:
            value = None
    # delay to avoid hitting the API to rapidly
    sleep(api_sleep)
    return value

def get_xtools_page_creation_counts(username, project_url, api_sleep=0.1):
    """sends a query to the XTools User Pages counter and returns a single value."""
    query_url = 'https://xtools.wmflabs.org/api/user/pages_count/' + project_url + '/' + username
    response = get_request(query_url, headers=generate_header_dictionary())
    if response is None:
        value = None
    else:
        try:
            data = json.loads(response)
            if 'count' in data['counts']:
                value = data['counts']['count']
            else:
                value = 0
        except:
            value = None
    # delay to avoid hitting the API to rapidly
    sleep(api_sleep)
    return value

# -----------------
# top-level functions for acquiring the main datasets
# -----------------

def get_vandycite_contribution_counts():
    """Retrieves the total contributions for all participants in the VandyCite project and writes to CSV file.
    If it fails due to timeout or some other error, the input file remains unchanged.
    """
    
    # Get existing table of edit data
    text_string = load_file('vandycite_edit_data.csv', bucket='disc-dashboard-data', path='vandycite/')
    table = read_string_to_dicts(text_string)
    
    # Get username list
    vandycite_user_list = []
    text_string = load_file('vandycite_users.csv', bucket='disc-dashboard-data', path='vandycite/')
    user_dicts = read_string_to_dicts(text_string)
    for dict in user_dicts:
        vandycite_user_list.append(dict['username'])

    # Retrieve data from XTools Edit Counter API
    project = 'wikidata'
    namespace = '0' # 0 is the main namespace

    fieldnames = ['date'] + vandycite_user_list + ['total']
    today = generate_utc_date()
    row_dict = {'date': today}

    total = 0
    success = True
    for username in vandycite_user_list:
        #print(username)
        count = get_xtools_edit_counts(username, project, namespace)
        if count is None: # If not HTTP 200 or response not JSON abort this update
            success = False
            break # Get out of the loop with a failure state
        else:
            row_dict[username] = count
            total += int(count)
    row_dict['total'] = str(total)
    
    if success: # Only add the row if all data were collected successfully. Otherwise, the table is unchanged.
        table.append(row_dict)
        file_text_string = write_dicts_to_string(table, fieldnames)
        save_string_to_file_in_bucket(file_text_string, 'vandycite_edit_data.csv', path='vandycite/')
        return True
    else:
        return False

def get_vandycite_page_creation_counts():
    """Retrieves the total number of new pages created for all VandyCite participants and writes to a VSV.
    If it fails, the input file remains unchanged.
    """
    # Get existing table of new pages data
    text_string = load_file('vandycite_page_creation_data.csv', bucket='disc-dashboard-data', path='vandycite/')
    table = read_string_to_dicts(text_string)
    
    # Get username list
    vandycite_user_list = []
    text_string = load_file('vandycite_users.csv', bucket='disc-dashboard-data', path='vandycite/')
    user_dicts = read_string_to_dicts(text_string)
    for dict in user_dicts:
        vandycite_user_list.append(dict['username'])

    # Retrieve data from XTools User Pages API
    project_url = 'www.wikidata.org'

    fieldnames = ['date'] + vandycite_user_list + ['total']
    today = generate_utc_date()
    row_dict = {'date': today}

    total = 0
    success = True
    for username in vandycite_user_list:
        #print(username)
        count = get_xtools_page_creation_counts(username, project_url)
        if count is None: # If not HTTP 200 or response not JSON abort this update
            success = False
            break # Get out of the loop with a failure state
        else:
            row_dict[username] = count
            total += int(count)
    row_dict['total'] = str(total)
    
    if success: # Only add the row if all data were collected successfully. Otherwise, the table is unchanged.
        table.append(row_dict)
        file_text_string = write_dicts_to_string(table, fieldnames)
        save_string_to_file_in_bucket(file_text_string, 'vandycite_page_creation_data.csv', path='vandycite/')
        return True
    else:
        return False

def get_vu_counts():
    """Runs all of the WDQS SPARQL queries that retrieve a single value for the whole university.
    If it fails due to timeout or some other error, the file remains unchanged.
    """
    all_vu_query_list = [
        {'name': 'vu_total',
        'query': '''
        select (count(distinct ?person) as ?single_value)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?person wdt:P1416 ?unit.
          }
        '''},
        {'name': 'vu_men',
        'query': '''
        select (count(distinct ?man) as ?single_value)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?man wdt:P1416 ?unit.
          ?man wdt:P21 wd:Q6581097.
          }
        '''},
        {'name': 'vu_women',
        'query': '''
        select (count(distinct ?woman) as ?single_value)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?woman wdt:P1416 ?unit.
          ?woman wdt:P21 wd:Q6581072.
          }
        '''},
        {'name': 'vu_orcid',
        'query': '''
        select (count(distinct ?person) as ?single_value)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?person wdt:P1416 ?unit.
          ?person wdt:P496 ?orcid.
          }
        '''},
        {'name': 'vu_works',
        'query': '''
        select (count(distinct ?work) as ?single_value)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?person wdt:P1416 ?unit.
          ?work wdt:P50 ?person.
          }
        '''},
        {'name': 'vu_men_works',
        'query': '''
        select (count(distinct ?work) as ?single_value)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?man wdt:P1416 ?unit.
          ?man wdt:P21 wd:Q6581097.
          ?work wdt:P50 ?man.
          }
        '''},
        {'name': 'vu_women_works',
        'query': '''
        select (count(distinct ?work) as ?single_value)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?woman wdt:P1416 ?unit.
          ?woman wdt:P21 wd:Q6581072.
          ?work wdt:P50 ?woman.
          }
        '''},
    ]
    #print(json.dumps(all_vu_query_list, indent=2))
    
    # Load existing data
    text_string = load_file('vandycite_item_data.csv', bucket='disc-dashboard-data', path='vandycite/')
    table = read_string_to_dicts(text_string)

    fieldnames = ['date']
    today = generate_utc_date()
    row_dict = {'date': today}

    # Retrieve data from Wikidata Query Service
    success = True
    for query_dict in all_vu_query_list:
        query_name = query_dict['name']
        print(query_name)
        fieldnames.append(query_name)
        count = get_single_value(query_dict['query'])
        if count is None: # If not HTTP 200 or response not JSON abort this update
            success = False
            break # Get out of the loop with a failure state
        else:
            row_dict[query_name] = count

    if success: # Only add the row if all data were collected successfully. Otherwise, the table is unchanged.
        table.append(row_dict)
        file_text_string = write_dicts_to_string(table, fieldnames)
        save_string_to_file_in_bucket(file_text_string, 'vandycite_item_data.csv', path='vandycite/')
        return True
    else:
        return False

def get_unit_affiliation_queries():
    units_query_list = [
        {'name': 'units_total',
        'query': '''
        select ?unit (count(distinct ?person) as ?count)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?person wdt:P1416 ?unit.
          }
        group by ?unit
        '''},
        {'name': 'units_women',
        'query': '''
        select ?unit (count(distinct ?woman) as ?count)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?woman wdt:P1416 ?unit.
          ?woman wdt:P21 wd:Q6581072.
          }
        group by ?unit
        '''},
        {'name': 'units_men',
        'query': '''
        select ?unit (count(distinct ?man) as ?count)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?man wdt:P1416 ?unit.
          ?man wdt:P21 wd:Q6581097.
          }
        group by ?unit
        '''},
        {'name': 'units_orcid',
        'query': '''
        select ?unit (count(distinct ?person) as ?count)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?person wdt:P1416 ?unit.
          ?person wdt:P496 ?orcid.
          }
        group by ?unit
        '''},
        {'name': 'units_works',
        'query': '''
        select ?unit (count(distinct ?work) as ?count)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?person wdt:P1416 ?unit.
          ?work wdt:P50 ?person.
          }
        group by ?unit
        '''},
        {'name': 'units_works_men',
        'query': '''
        select ?unit (count(distinct ?work) as ?count)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?man wdt:P1416 ?unit.
          ?man wdt:P21 wd:Q6581097.
          ?work wdt:P50 ?man.
          }
        group by ?unit
        '''},
        {'name': 'units_works_women',
        'query': '''
        select ?unit (count(distinct ?work) as ?count)  where {
          ?unit wdt:P749+ wd:Q29052.
          ?woman wdt:P1416 ?unit.
          ?woman wdt:P21 wd:Q6581072.
          ?work wdt:P50 ?woman.
          }
        group by ?unit
        '''}
    ]
    return units_query_list

# -----------------
# main script
# -----------------

def lambda_handler(event, context):
    #data = get_single_value(query)
    #data = get_unit_counts(query)
    result = get_vandycite_contribution_counts()
    
    print(result)
    return {}
