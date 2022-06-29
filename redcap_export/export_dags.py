#!/usr/bin/env python
#Exports the REDCap data admin groups for populating organization and access group tables; format can be csv or json. 

from config import config
import requests

fields = {
    'token': config['api_token'],
    'content': 'dag',
    'format': 'csv'
}

r = requests.post(config['api_url'],data=fields)
print('HTTP Status: ' + str(r.status_code))
print(r.text)
