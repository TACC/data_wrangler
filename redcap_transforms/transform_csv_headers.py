"""
Replaces headers from a csv with another set of specified headers. 

TO DO: Pass filename as an arg. 
TO DO: Create the header list from the rcap_field_variable_map.csv  
"""
import csv

header = ["column_1", "column_2", "column_3"]

with open('text.csv', 'r') as fp:
    reader = csv.DictReader(fp, fieldnames=header)

    # use newline='' to avoid adding new CR at end of line
    with open('output.csv', 'w', newline='') as fh: 
        writer = csv.DictWriter(fh, fieldnames=reader.fieldnames)
        writer.writeheader()
        header_mapping = next(reader)
        writer.writerows(reader)
