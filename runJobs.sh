#!/bin/sh

# Set your CI/CD variables
USERNAME=ATSAPIUser
PASSWORD=ATSAPIUser
APPAPITOKEN=103e32b3-2857-49fe-96e3-6aef5104262d
APPID=cdf0ca7a-c44b-4cef-82ec-c10be367588b
JOBTEMPLATEID=74c98fa5-9671-496a-83c7-2774c100d482
URL2=https://ats100.mendixcloud.com/


echo "ATS Testing will start..."
echo ""
#Call ATS API

JOBID=$(curl -s -H 'Content-Type: text/xml' -d '<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\" xmlns:men=\"http://www.mendix.com/\"><soapenv:Header><men:authentication><username>$USERNAME</username><password>$PASSWORD</password></men:authentication></soapenv:Header><soapenv:Body><men:RunJob><TestRun><AppAPIToken>$APPAPITOKEN</AppAPIToken><AppID>$APPID</AppID><JobTemplateID>$JOBTEMPLATEID</JobTemplateID></TestRun></men:RunJob></soapenv:Body></soapenv:Envelope>' ${URL2}/ws/RunJob -X POST |xmllint --xpath "string(//JobID)" -)

