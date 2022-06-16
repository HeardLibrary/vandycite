# Note: to use the GitHub API, you need to deploy PyGitHub: https://github.com/PyGithub/PyGithub
# Follow the instructions at https://docs.aws.amazon.com/lambda/latest/dg/python-package.html#python-package-create-package-with-dependency
# It is necessary to create the package on an EC2 instance that's running the same version of Linux as the Lambda.
# Check https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html to find the Linux version for the Python3 used in the lambda (Amazon Linux 2 for x86_64)
# Created baskauf_python_lambda_package_builder2 EC2 t2micro instance. Used PEM baskauf_python_lambda_package_builder.pem
# Allow access to key by issuing command: chmod 400 /Users/baskausj/baskauf_python_lambda_package_builder.pem
# Connection notes at https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/AccessingInstancesLinux.html
# Connect using: ssh -i baskauf_python_lambda_package_builder.pem ec2-user@ec2-3-83-117-207.compute-1.amazonaws.com
# Python3 (and pip3) is already installed along with the OS.
# Used command pip3 install --target ./package PyGithub
# After finishing creating the .zip, use SCP to get it from the EC2 to local drive (in a terminal window that's not SSH'ed to the EC2):
# scp -i baskauf_python_lambda_package_builder.pem ec2-user@ec2-3-83-117-207.compute-1.amazonaws.com:my-sourcecode-function/my-deployment-package.zip /Users/baskausj/my-deployment-package.zip
# Then add the lambda_function.py to the zip file using: zip -g my-deployment-package.zip lambda_function.py


import boto3
import json
import csv
import io
import urllib3
from time import sleep
import datetime
import pickle
from github import Github

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

def read_string_from_github_file(path_to_directory, filename, organization_name='heardlibrary', repo_name='dashboard'):
    """Read a raw string from a file in GitHub."""
    path = path_to_directory + filename
    url = 'https://raw.githubusercontent.com/' + organization_name + '/' + repo_name + '/master/' + path
    response = get_request(url)
    return response

def read_dicts_from_github_csv(path_to_directory, filename, organization_name='heardlibrary', repo_name='dashboard'):
    """Read from a CSV file in GitHub into a list of dictionaries (representing a table)."""
    path = path_to_directory + filename
    url = 'https://raw.githubusercontent.com/' + organization_name + '/' + repo_name + '/master/' + path
    response = get_request(url)
    file_text = response.split('\n')
    file_rows = csv.DictReader(file_text)
    table = []
    for row in file_rows:
        table.append(row)
    return table

def read_lists_from_github_csv(path_to_directory, filename, organization_name='heardlibrary', repo_name='dashboard'):
    """Read from a CSV file in GitHub into a list of lists (representing a table)."""
    path = path_to_directory + filename
    url = 'https://raw.githubusercontent.com/' + organization_name + '/' + repo_name + '/master/' + path
    response = get_request(url)
    file_text = response.split('\n')
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
# functions for interacting with GitHub
# -----------------

def load_credential(filename):
    """Loads the GitHub token from a pickle (binary) file and converts it to text."""
    bytes_like_object = load_file(filename, format='bytes') # format kwarg prevents the loader from converting to UTF-8
    cred = pickle.loads(bytes_like_object) # This is the pickle method to un-pickle a bytes-like object.
    return cred
    
def login_get_repo(cred_filename, repo_name, github_username='', organization_name=''):
    """Log in and return a repo object.
    
    Set a value for the github_username keyword to do a username login instead of using an access token. Note:
    username logins are not possible when 2FA is enabled.
    
    Set a value for the organization_name to use an organizational account rather than an individual account. 
    The token creator must have push access to the organization's repo.
    """
    if github_username:
        pwd = load_credential(cred_filename)
        g = Github(github_username, pwd)
    else:
        token = load_credential(cred_filename)
        g = Github(login_or_token = token)
    
    if organization_name:
        # this option creates an instance of a repo in an organization
        # to which the token creator has push access
        organization = g.get_organization(organization_name)
        repo = organization.get_repo(repo_name)
    else:
        # this option accesses a user's repo instead of an organizational one
        # In this case, the value of organization_name is not used.
        user = g.get_user()
        repo = user.get_repo(repo_name)
    return repo

# -----------------
# main script
# -----------------

def lambda_handler(event, context):
    '''
    request_header_dict = generate_header_dictionary()
    # Extract the data about the file triggering the S3 event
    #in_file_name = event['Records'][0]['s3']['object']['key']
    in_file_name = 'url.txt'
    #in_bucket_name = event['Records'][0]['s3']['bucket']['name']
    in_bucket_name = 'baskauf-lambda-input'
    
    file_string = load_file('url.txt')

    print(file_string)
    
    json_string = get_request(file_string, headers=request_header_dict)
    data = json.loads(json_string)
    '''
    
    username = 'Baskaufs'
    project = 'wikidata'
    namespace = '0'
    project_url = 'www.wikidata.org'
    #data = get_xtools_edit_counts(username, project, namespace)
    #data = get_xtools_page_creation_counts(username, project_url)
    #data = get_single_value(query)
    #data = get_unit_counts(query)
    path_to_directory = 'vandycite/'
    filename = 'vandycite_users.csv'
    #data = read_string_from_github_file(path_to_directory, filename)
    #table = read_dicts_from_github_csv(path_to_directory, filename)
    #table = read_lists_from_github_csv(path_to_directory, filename)
    #data = write_dicts_to_string(table, ['username'])
    #data = write_lists_to_string(table)
    github_cred_filename = '010e0da8-8793-439d-845c-66d937b040a1.'
    #data = load_file(github_cred_filename)
    #data = load_credential(github_cred_filename)
    github_organization = 'heardlibrary'
    repo_name = 'dashboard'
    data = login_get_repo(github_cred_filename, repo_name, organization_name=github_organization)
    
    print(data)
    return {}
