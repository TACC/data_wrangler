#!/usr/bin/env python
#report_id is number assigned to the REDCap custom report. Utilize a CSV with all report_ids to export from the project (ctrn_report_ids.csv)

from config import config
import requests

fields = {
    'token': config['api_token'],
    'content': 'report',
    'format': 'csv',
    'report_id': '4792',
    'csvDelimiter': '',
    'rawOrLabel': 'raw',
    'rawOrLabelHeaders': 'raw',
    'exportCheckboxLabel': 'false',
    'returnFormat': 'csv'
}

r = requests.post(config['api_url'],data=fields)
print('HTTP Status: ' + str(r.status_code))
print(r.text)


