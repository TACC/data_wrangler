#!/usr/bin/env python
#Similar to export_records, returns records added, updated or deleted from beginTime to endTime

from config import config
import requests

fields = {
    'token': config['api_token'],
    'content': 'log',
    'format': 'csv',
    'logtype': 'record',
    'user': '',
    'record': '',
    'beginTime': '2020-06-23 14:45',
    'endTime': '',
    'returnFormat': 'csv'
}

r = requests.post(config['api_url'],data=fields)
print('HTTP Status: ' + str(r.status_code))
print(r.text)