#!/usr/bin/env python
# report_id is a number assigned to the REDCap custom report. Use a list or CSV of report_ids to export from each project (ctrn_report_ids.csv).
#Save the returned data to a file within the CTRN VM rc_export directory /rc_export/[report_name]_DATA_[export_date]_[hhmm].csv
#An example filename for a REDCap report download is "TexasChildhoodTrauma-SchererTesicsp_DATA_2022-06-09_1442.csv" 

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


