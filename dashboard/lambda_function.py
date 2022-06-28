# StatsRetrieverLambda, a Python script for collecting Wikimedia data
version = '0.1'
created = '2022-06-28'

# (c) 2022 Vanderbilt University. This program is released under a GNU General Public License v3.0 http://www.gnu.org/licenses/gpl-3.0
# Author: Steve Baskauf

# IMPORTANT NOTE: If you hack this script to download your own data, you MUST change the user_agent_header
# to your own email address.

import boto3
import json
import csv
import io
import os
import urllib3
import urllib.parse
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

def yesterday_utc():
    today = datetime.datetime.utcnow().toordinal() # get today as number of days from Jan 1, 1 CE
    yesterday = datetime.datetime.fromordinal(today - 1) # turn ordinal day back into dateTime object
    yesterday_iso = yesterday.strftime('%Y-%m-%d')
    yesterday_wikimedia = yesterday.strftime('%Y%m%d')
    return yesterday_iso, yesterday_wikimedia
    
def extract_localname(iri):
    """Parse the local name from an IRI"""
    pieces = iri.split('/')
    return pieces[len(pieces)-1] # return the last piece

def filename_to_commons_page_article(filename):
    """Performs encoding and character substitutions to convert a filename to the file string in a Commons URL"""
    filename = filename.replace(' ', '_')
    encoded_filename = urllib.parse.quote(filename)
    url = 'File:' + encoded_filename
    url = url.replace('%28', '(').replace('%29', ')').replace('%2C', ',')
    return url

def generate_header_dictionary():
    """Generate HTTP request header dictionary for Accept=JSON and a custom User-Agent string"""
    accept_media_type = 'application/json'
    user_agent_header = 'StatsRetrieverLambda/' + version + ' (mailto:steve.baskauf@vanderbilt.edu)'
    request_header_dictionary = {
        'Accept' : accept_media_type,
        'User-Agent': user_agent_header
    }
    return request_header_dictionary

def load_file(filename, path='', bucket='disc-dashboard-data', format='string'):
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

def get_request_status(url, headers=None, params=None):
    """Performs an HTTP GET from a URL and returns the response body as UTF-8 text, or None if not status 200."""
    if headers is None:
        http = urllib3.PoolManager()
    else:
        http = urllib3.PoolManager(headers=headers)
    if params is None:
        response = http.request('GET', url)
    else:
        response = http.request('GET', url, fields=params)
    response_body = response.data.decode('utf-8')
    return response_body, response.status
 
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
    
def send_email(message_string):
    """Sends message_string as an email to subscribers of the sns api-update-fail topic.
    To set up, create the topic, set the arn as the snsArn environmental variable,
    and make sure that the SNS permissions have been added to the lambda's role.
    """
    sns = boto3.client('sns')
    snsArn = os.environ['sns_arn']
    response = sns.publish(
        TargetArn=snsArn,
        Message=json.dumps({
            'default': json.dumps(message_string)
        }),
        MessageStructure='json'
    )

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

def get_pageview_counts(article, date, project='commons.wikimedia.org', api_sleep=0.015):
    """Send a request to the Wikimedia REST API to get pageviews for an article.
    article is the page name after 'wiki/' in the URL (e.g. "File:imagex.jpg", or "Q2")
    date is in the format yyyymmdd
    The rate limit is 100 calls/s, so api_sleep should not be decreased below 0.015
    
    NOTES:
    Pageviews API information https://wikitech.wikimedia.org/wiki/Analytics/AQS/Pageviews
    Wikimedia REST API information https://wikimedia.org/api/rest_v1/
    """
    query_url = 'https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/' + project + '/all-access/user/' + article + '/daily/' + date + '/' + date
    print(query_url)
    response, code = get_request_status(query_url, headers=generate_header_dictionary())
    if code == 200:
        try:
            data = json.loads(response)
            if 'items' in data:
                #print('Found record successfully.')
                value = str(data['items'][0]['views'])
        except:
            # Error messages not in JSON format
            print('API response not JSON')
            value = None
    elif code == 404:
        try:
            data = json.loads(response)
            if 'detail' in data:
                # Handle case where there were no views on that day or article didn't exist
                message = 'The date(s) you used are valid, but we either do not have data for those date(s), or the project you asked for is not loaded yet.'
                if message in data['detail']:
                    value = str(0)
                else:
                    print('404 response "detail" did not have the valid date/no data response')
                    value = None
            else:
                print('404 response did not include a "detail" field')
                value = None
        except:
            print('404 response was not JSON')
            value = None
    else:
        print('response neither 200 nor 404')
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
    text_string = load_file('vandycite_edit_data.csv', path='vandycite/')
    table = read_string_to_dicts(text_string)
    
    # Get username list
    vandycite_user_list = []
    text_string = load_file('vandycite_users.csv', path='vandycite/')
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
    
    if success: # Only add the row and write if all data were collected successfully. Otherwise, the table is unchanged.
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
    text_string = load_file('vandycite_page_creation_data.csv', path='vandycite/')
    table = read_string_to_dicts(text_string)
    
    # Get username list
    vandycite_user_list = []
    text_string = load_file('vandycite_users.csv', path='vandycite/')
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
    text_string = load_file('vandycite_item_data.csv', path='vandycite/')
    table = read_string_to_dicts(text_string)

    fieldnames = ['date']
    today = generate_utc_date()
    row_dict = {'date': today}

    # Retrieve data from Wikidata Query Service
    success = True
    for query_dict in all_vu_query_list:
        query_name = query_dict['name']
        #print(query_name)
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
    """Creates a list of dictionaries containing SPARQL queries to retrieve Wikidata data by academic unit"""
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

def get_vu_counts_by_unit(last_run, last_script_run):
    """Loops through a series of queries that retrieves counts data from Wikidata about Vanderbilt academic units"""
    units_query_list = get_unit_affiliation_queries()
    for query_dict in units_query_list:
        #print(query_dict['name'])
        filename = query_dict['name'] + '.csv'
        
        if generate_utc_date() > last_run[filename].split('T')[0]:
            text_string = load_file(filename, path='vandycite/')
            # NOTE: This differs from other functions in that it creates a list of lists rather than a list of dicts.
            table = read_string_to_lists(text_string)
            
            date = generate_utc_date()
    
            # Retrieve data from Wikidata Query Service
            dictionary = get_unit_counts(query_dict['query'])
            if dictionary is None:
                success = False
            else:
                row_list = [date]
                # Go through each column header and try to match it to the SPARQL query results
                for header in table[0][1:len(table[0])]: # skip the first item (date)
                    found = False
                    for count in dictionary:
                        if count['unit'] == header:
                            found = True
                            row_list.append(count['count'])
                    if not found:
                        row_list.append('0')
                table.append(row_list) # Add the new data row to the end of the table.
                file_text_string = write_lists_to_string(table)
                save_string_to_file_in_bucket(file_text_string, filename, path='vandycite/')
                success = True
            if success:
                last_run[filename] = datetime.datetime.utcnow().isoformat()
                file_text_string = json.dumps(last_run)
                save_string_to_file_in_bucket(file_text_string, 'last_run.json')
                print(filename, datetime.datetime.utcnow().isoformat())
            else: # If the file update was unsuccessful, do nothing on the first try of the day.
                if last_script_run == generate_utc_date(): # If fail and the script was already run today...
                    send_email(filename + ' failed')
    return last_run

def get_commons_pageview_counts():
    """Retrieve the Commons page views for all Gallery works in the source file
    If it fails due to timeout or some other error, the table remains unchanged
    Returns a raw CSV string
    """
    # Load previous pageview data
    text_string = load_file('commons_pageview_data.csv', path='gallery/')
    table = read_string_to_dicts(text_string)

    # Get Commons image data
    text_string = load_file('commons_images.csv', path='gallery/')
    user_dicts = read_string_to_dicts(text_string)

    # Create column headers list
    mid_list = [] # M IDs are the Commons equivalents of Q IDs used by the Structured data Wikibase
    for dict_record in user_dicts:
        mid_list.append(dict_record['commons_id'])
        
    # Retrieve data from the Wikimedia REST API
    yesterday_iso, yesterday_wikimedia = yesterday_utc()
    #yesterday_iso = '2021-12-11' # uncomment to override date to be checked
    #yesterday_wikimedia = '20211211' # uncomment to override date to be checked

    fieldnames = ['date', 'total'] + mid_list
    row_dict = {'date': yesterday_iso}

    total = 0
    success = True
    for dict_record in user_dicts:
        image_filename = dict_record['image_name']
        #print(image_filename)
        count = get_pageview_counts(filename_to_commons_page_article(image_filename), yesterday_wikimedia)
        if count is None:
            success = False
            break # Get out of loop with failure state
        else:
            row_dict[dict_record['commons_id']] = count
            total += int(count)
    row_dict['total'] = str(total)

    if success:
        table.append(row_dict)
        file_text_string = write_dicts_to_string(table, fieldnames)
        save_string_to_file_in_bucket(file_text_string, 'commons_pageview_data.csv', path='gallery/')
        return True
    else:
        return False

# -----------------
# main script
# -----------------

def lambda_handler(event, context):
    print('start update:', datetime.datetime.utcnow().isoformat())
    
    # Load the date of the last time the lambda ran
    last_script_run = load_file('last_run.txt')
    
    # Load the data about the last time each datafile was successfully updated.
    text_string = load_file('last_run.json')
    last_run = json.loads(text_string)
    
    # Collect the data if the current date is later than the date the last time the file was updated.
    if generate_utc_date() > last_run['commons_pageview_data.csv'].split('T')[0]:
        result = get_commons_pageview_counts()
        if result: # Save the file update time if successful
            last_run['commons_pageview_data.csv'] = datetime.datetime.utcnow().isoformat()
            file_text_string = json.dumps(last_run)
            save_string_to_file_in_bucket(file_text_string, 'last_run.json')
            print('commons_pageview_data.csv', datetime.datetime.utcnow().isoformat())
        else: # If the file update was unsuccessful, do nothing on the first try of the day.
            if last_script_run == generate_utc_date(): # If fail and the script was already run today...
                send_email('commons_pageview_data.csv failed')
    
    if generate_utc_date() > last_run['vandycite_edit_data.csv'].split('T')[0]:
        result = get_vandycite_contribution_counts()
        if result: # Save the file update time if successful
            last_run['vandycite_edit_data.csv'] = datetime.datetime.utcnow().isoformat()
            file_text_string = json.dumps(last_run)
            save_string_to_file_in_bucket(file_text_string, 'last_run.json')
            print('vandycite_edit_data.csv', datetime.datetime.utcnow().isoformat())
        else: # If the file update was unsuccessful, do nothing on the first try of the day.
            if last_script_run == generate_utc_date(): # If fail and the script was already run today...
                send_email('vandycite_edit_data.csv failed')
    
    if generate_utc_date() > last_run['vandycite_page_creation_data.csv'].split('T')[0]:
        result = get_vandycite_page_creation_counts()
        if result:
            last_run['vandycite_page_creation_data.csv'] = datetime.datetime.utcnow().isoformat()
            file_text_string = json.dumps(last_run)
            save_string_to_file_in_bucket(file_text_string, 'last_run.json')
            print('vandycite_page_creation_data.csv', datetime.datetime.utcnow().isoformat())
        else: # If the file update was unsuccessful, do nothing on the first try of the day.
            if last_script_run == generate_utc_date(): # If fail and the script was already run today...
                send_email('vandycite_page_creation_data.csv failed')
        
    if generate_utc_date() > last_run['vandycite_item_data.csv'].split('T')[0]:
        result = get_vu_counts()
        if result:
            last_run['vandycite_item_data.csv'] = datetime.datetime.utcnow().isoformat()
            file_text_string = json.dumps(last_run)
            save_string_to_file_in_bucket(file_text_string, 'last_run.json')
            print('vandycite_item_data.csv', datetime.datetime.utcnow().isoformat())
        else: # If the file update was unsuccessful, do nothing on the first try of the day.
            if last_script_run == generate_utc_date(): # If fail and the script was already run today...
                send_email('vandycite_item_data.csv failed')
    
    last_run = get_vu_counts_by_unit(last_run, last_script_run)
    
    # Save the current date as the last time the lambda ran.
    save_string_to_file_in_bucket(generate_utc_date(), 'last_run.txt')
    
    return last_run
