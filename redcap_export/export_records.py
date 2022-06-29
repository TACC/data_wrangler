#!/usr/bin/env python

# Export all records that have been added or changed since dateRangeBegin; format may be 'csv' or 'json'. If json, lines 14-17 and 22 should be commented out.  

from config import config
import requests

fields = {
    'token': config['api_token'],
    'content': 'record',
    'action': 'export',
    'format': 'csv',
    'type': 'flat',
    'csvDelimiter': '',
    'rawOrLabel': 'raw',
    'rawOrLabelHeaders': 'raw',
    'exportCheckboxLabel': 'false',
    'exportSurveyFields': 'true',
    'exportDataAccessGroups': 'true',
    'returnFormat': 'csv',
    'dateRangeBegin': '2022-06-08 00:00:00',
    'exportBlankForGrayFormStatus': 'true'
}
r = requests.post(config['api_url'],data=fields)
print('HTTP Status: ' + str(r.status_code))
print(r.text)
