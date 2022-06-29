#!/usr/bin/env python
#Exports list of REDCap events for populating protocol/event_type tables.

from config import config
import requests

fields = {
    'token': config['api_token'],
    'content': 'event',
    'format': 'csv',
    'arms': ''
}

r = requests.post(config['api_url'],data=fields)
print('HTTP Status: ' + str(r.status_code))
print(r.text)
