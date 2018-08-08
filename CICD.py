import json
import requests
import configparser 
import sys
import pprint 
import logging
import time
import polling
import shutil
import sendgrid
import os
from sendgrid.helpers.mail import *
import lxml.etree

CONFIGFILE='config.ini'
BRANCH='trunk' # this should be a config parameter

#logging.basicConfig(level=logging.DEBUG)
logging.basicConfig(level=logging.INFO)

# read the configuration file 
logging.info('Reading the configuraton file: ' + CONFIGFILE)
try:
    config=configparser.ConfigParser()
    config.read(CONFIGFILE)
except:
    print('Error reading configuration file.  Does ' + CONFIGFILE + 'exist?')
    sys.exit()

# extract configuration information from the configuration file [MENDIXAPI] section
logging.info('Retrieving configuration values from configuration file: ' + CONFIGFILE)
try: 
    username=config.get('MENDIXAPI','Mendix-Username')
    apikey=config.get('MENDIXAPI','Mendix-ApiKey')
except:
    print('Error retrieving configuration values from configuration file')
    sys.exit()

# extract configuration information from the configuration file [CONFIG] section
try:
    endpoint=config.get('CONFIG','endpoint')
    AppId=config.get('CONFIG','AppId')
except:
    print('Error retrieving configuration values from the configuration file')
    sys.exit()

# set headers 
headers={'Mendix-Username': username,
         'Mendix-ApiKey' : apikey}

# GET a list of all apps associated with this user and apikey
logging.info('GET request to retrieve all apps associated with user and apikey')

resource='/api/1/apps/'

url=endpoint+resource

try:
    r=requests.get(url, headers=headers)
except:
    print('Failed making GET request to ' + r.url);
    sys.exit()

# GET information associated to a single app using its AppId
logging.info('GET information associated to AppId: ' + AppId)
resource='/api/1/apps/{0}'.format(AppId)
url=endpoint+resource
try:
    r=requests.get(url, headers=headers)
except:
    print('Failed making GET request to ' + r.url)
    sys.exit()

# GET revisions
logging.info('GET revisions history for AppId: ' + AppId)
resource='/api/1/apps/{0}/branches/{1}/revisions/'.format(AppId,BRANCH)
url=endpoint+resource
try:
	r=requests.get(url, headers=headers)
except:
	print('Failed making GET request to ' + r.url)
	sys.exit()

#logging.debug('Revision History: ' + str(r.json()))

latestRevisionNumber=r.json()[0]['Number']

# GET Packages
logging.info('GET packages for AppId: ' + AppId)
resource='/api/1/apps/{0}/packages/'.format(AppId)
url=endpoint+resource
try:
        r=requests.get(url, headers=headers)
except:
        print('Failed making GET request to ' + r.url)
        sys.exit()

#logging.debug('Available Packages' + str(r.json()))


# create a deployment package from the latest revision
logging.info('creating deployment package from the latest revision')
resource='/api/1/apps/{0}/packages/'.format(AppId)
url=endpoint+resource
data = {}
data['Revision'] = latestRevisionNumber
data['Version'] = '3.2.'+str(int(round(time.time() * 1000))) 
data['Description'] = 'Created for auto-deployment'
json_data = json.dumps(data)

try:
    r=requests.post(url, headers=headers, data=json_data)
except:
    print('Failed making POST request to ' + r.url)
    sys.exit()

logging.debug('Package Response: ' + str(r.json()))
packageId=r.json()['PackageId']


# check status of the package creation process
logging.info('checking on status of package ' + packageId + ' (poll)')
resource='/api/1/apps/{0}/packages/{1}'.format(AppId,packageId)
url=endpoint+resource
try:
    r=requests.get(url, headers=headers)
except:
    sys.exit()

# poll until the package is created 

def is_package_built(response):
    """check that the package has been built"""
    return response.json()['Status'] == 'Succeeded'

polling.poll(
    lambda: requests.get(url, headers=headers),
    check_success=is_package_built,
    step=10,
    timeout=200)

logging.debug('Packaging Succeeded')

# download the package (this is not necessary for a CICD pipeline that leverages the transport API)
logging.info('downloading package: ' + packageId )
resource='/api/1/apps/{0}/packages/{1}/download'.format(AppId,packageId)
url=endpoint+resource
local_filename = 'package.file'
r = requests.get(url, headers=headers, stream=True)
with open(local_filename, 'wb') as f:
    shutil.copyfileobj(r.raw, f)

# transport package to acceptance environment
logging.info('transporting package to acceptance')
resource='/api/1/apps/{0}/environments/{1}/transport'.format(AppId,'Acceptance')
url=endpoint+resource
data = {}
data['PackageId'] = packageId
json_data = json.dumps(data)
try:
    r=requests.post(url, headers=headers, data=json_data)
except:
    sys.exit()

# stop the acceptance environment
logging.info('stopping the acceptance environment')
resource='/api/1/apps/{0}/environments/{1}/{2}'.format(AppId,'Acceptance','stop')
url=endpoint+resource
try:
    r=requests.post(url, headers=headers)
except:
    sys.exit()

# poll until environment is stopped

resource='/api/1/apps/{0}/environments/{1}'.format(AppId,'Acceptance')
url=endpoint+resource

logging.info('waiting for acceptance environment to stop (poll)')

def is_environment_stopped(response):
    """check that the environment is stopped"""
    return response.json()['Status'] == 'Stopped'

polling.poll(
    lambda: requests.get(url, headers=headers),
    check_success=is_environment_stopped,
    step=5,
    timeout=200)

# start the acceptance environment
logging.info('starting the acceptance environment')
resource='/api/1/apps/{0}/environments/{1}/{2}'.format(AppId,'Acceptance','start')
url=endpoint+resource
try:
    r=requests.post(url, headers=headers)
except:
    sys.exit()

# poll until environment is started

resource='/api/1/apps/{0}/environments/{1}'.format(AppId,'Acceptance')
url=endpoint+resource
logging.info('waiting for acceptance environment to start (poll)')

def is_environment_running(response):
    """check that the environment is running"""
    return response.json()['Status'] == 'Running'

polling.poll(
    lambda: requests.get(url, headers=headers),
    check_success=is_environment_running,
    step=5,
    timeout=200)

# start running tests

# ATS testing
logging.info('start ATS testing')
ats_headers = {'content-type': 'application/soap+xml'}
x='<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:men="http://www.mendix.com/"><soapenv:Header><men:authentication><username>{0}</username><password>{1}</password></men:authentication></soapenv:Header><soapenv:Body><men:RunJob><TestRun><AppAPIToken>{2}</AppAPIToken><AppID>{3}</AppID><JobTemplateID>{4}</JobTemplateID></TestRun></men:RunJob></soapenv:Body></soapenv:Envelope>'.format('', '', '', '', '')
r=requests.post('https://ats100.mendixcloud.com/ws/RunJob', headers=headers, data=x)
xml_tree = lxml.etree.fromstring(r.text)
ats_JobID = xml_tree.find('.//*/JobID').text
logging.info('started ATS test suite. returned JobID: ' + ats_JobID)
logging.info('ATS results can be viewed at: https://ats100.mendixcloud.com/index.html')

# poll ats

# check return status of ats




# microflow testing
logging.info('start microflow testing')

url='https://mendix345-accp.mendixcloud.com/rest/testrunner/v1/runall'
r=requests.get(url)


if r.json()['Test Status']=='Passed':
    logging.info('microflow testing passed')
    logging.info('microflow testing results ca be viewed at: https://mendix345-accp.mendixcloud.com/')
    # transporting package to production environment
    logging.info('transporting package to production')
    resource='/api/1/apps/{0}/environments/{1}/transport'.format(AppId,'Production')
    url=endpoint+resource
    data = {}
    data['PackageId'] = packageId
    json_data = json.dumps(data)
    try:
    	r=requests.post(url, headers=headers, data=json_data)
    except:
    	sys.exit()

    # stop the production environment
    logging.info('stopping the production environment')
    resource='/api/1/apps/{0}/environments/{1}/{2}'.format(AppId,'Production','stop')
    url=endpoint+resource
    try:
        r=requests.post(url, headers=headers)
    except:
        sys.exit()

    # poll until environment is stopped

    resource='/api/1/apps/{0}/environments/{1}'.format(AppId,'Production')
    url=endpoint+resource

    def is_environment_stopped(response):
        """check that the environment is stopped"""
        return response.json()['Status'] == 'Stopped'

    polling.poll(
        lambda: requests.get(url, headers=headers),
        check_success=is_environment_stopped,
        step=5,
        timeout=200)

    # start the production environment
    logging.info('starting the production environment')
    resource='/api/1/apps/{0}/environments/{1}/{2}'.format(AppId,'Production','start')
    url=endpoint+resource
    try:
        r=requests.post(url, headers=headers)
    except:
        sys.exit()

    # poll until environment is started

    resource='/api/1/apps/{0}/environments/{1}'.format(AppId,'Production')
    url=endpoint+resource

    def is_environment_running(response):
        """check that the environment is running"""
        return response.json()['Status'] == 'Running'

    polling.poll(
        lambda: requests.get(url, headers=headers),
        check_success=is_environment_running,
        step=5,
        timeout=200)


    logging.info('production is running')

else:
    
    logging.info('microflow testing failed')
    logging.info('emailing committer: vincent.beltrani@mendix.com')
   # sg = sendgrid.SendGridAPIClient(apikey='')
   # from_email = Email("TestRunner@LogTest.app")
   # to_email = Email("vincent.beltrani@mendix.com")
   # subject = "You broke the build!"
   # content = Content("text/plain", "your message here")
   # mail = Mail(from_email, subject, to_email, content)
   # response = sg.client.mail.send.post(request_body=mail.get())
