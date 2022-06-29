#!/usr/bin/env python
#Export format can be set to csv or json.

from config import config
import requests

fields = {
    'token': config['api_token'],
    'content': 'metadata',
    'format': 'csv',
    'returnFormat': 'csv'
}

r = requests.post(config['api_url'],data=fields)
print('HTTP Status: ' + str(r.status_code))
print(r.text)

