"""
    Redcapy_exportcsv.py interacts with Redcap v12.0 API export methods.  Tested with Python 3.x.
    Based on Redcapy.py utilities developed by Bill Santos for UCSF and employed by him for managing REDCap projects through 2022 and REDCap v9.x.
    Includes backoff and throttling parameters to address REDCap load and timeout issues.
    Extended to include methods for exporting reports and other REDCap files formated as CSVs. 
    
    Note that the methods using self._core_api_code may return False to other instance methods in the event of a connection failure, in lieu of an expected response.
"""

import attr
import csv
import json
import re
import requests
import time

#from bs4 import BeautifulSoup (Chiefly used for testing/validating formats for importing into REDCap.) 
from collections import namedtuple
from functools import wraps
from validator_collection import checkers


@attr.s
class Redcapy_exportcsv:
    # Instance vars
    api_token = attr.ib(validator=attr.validators.instance_of(str))
    _redcap_token = ""  # later copies api_token value as private var
    redcap_url = attr.ib(validator=attr.validators.instance_of(str))
    last_status_code = ""
    last_response = ""
    retry_keys = ["limit", "wait_secs", "backoff", "logger"]  # Used by retry decorator

    @api_token.validator
    def check_and_mask_token(self, attribute, value):
        if not self.api_token:
            raise ValueError("Must provide token to initialize Redcapy instance")
        else:
            begin_show_chars = 3
            end_show_chars = 2

            # Swap tokens such that api_token is masked when revealed with __repr__ and using
            # instead private attribute _redcap_token as the actual token
            self._redcap_token = self.api_token
            self.api_token = (
                self._redcap_token[:begin_show_chars]
                + "***...***"
                + self._redcap_token[-end_show_chars:]
            )

    @redcap_url.validator
    def check_url(self, attribute, value):
        if not checkers.is_url(self.redcap_url):
            msg = 'Invalid URL format detected for "{}" when initializing Redcapy instance'.format(
                self.redcap_url
            )
            raise ValueError(msg)

    def __call__(self, *args, **kwargs):
        return self

    class _Decorators:
        @classmethod
        def retry(cls, exceptions, limit=4, wait_secs=3, backoff=2, logger=None):
            """
                Retry calling the decorated function using an exponential backoff.

                Ref: Adapted from https://www.calazan.com/retry-decorator-for-python-3/
                    and https://medium.com/@vadimpushtaev/decorator-inside-python-class-1e74d23107f6
                    and https://stackoverflow.com/a/19447502

                :param exceptions: The exception to check. may be a tuple of exceptions to check.
                :param limit: Number of times to try (not retry) before giving up.
                :param wait_secs: Initial delay between retries in seconds.
                :param backoff: Backoff multiplier (e.g. value of 2 will double the delay each retry).
                :param logger: Logger to use. If None, print.
            """

            # Outer function retry is a wrapper for the inner decorator
            def deco_retry(f):
                @wraps(f)
                def f_retry_wrapper(other_self, **kwargs):
                    # mtries, mdelay = tries, delay
                    post_data = kwargs.get("post_data", {})
                    import_file = kwargs.get("import_file", False)
                    delete_file = kwargs.get("delete_file", False)
                    opt_post_data_kvpairs = kwargs.get("opt_post_data_kvpairs", None)

                    mtries = kwargs.get("limit", limit)
                    mdelay = kwargs.get("wait_secs", wait_secs)
                    # mbackoff = kwargs.get('backoff', backoff)

                    while mtries > 1:
                        try:
                            print("Attempting API connection...")
                            rv = f(
                                other_self,
                                post_data=post_data,
                                import_file=import_file,
                                delete_file=delete_file,
                                opt_post_data_kvpairs=opt_post_data_kvpairs,
                                limit=mtries,
                                wait_secs=mdelay,
                            )

                            if isinstance(rv, bool) and not rv:
                                raise Exception

                            return rv
                        except (exceptions, Exception):
                            mtries -= 1

                            msg = "Up to {} attempt(s) remaining. Retrying in {} seconds...".format(
                                mtries, mdelay
                            )
                            print(msg)

                            if logger:
                                logger.warning(msg)

                            time.sleep(mdelay)
                            mdelay *= backoff

                    return f(
                        other_self,
                        post_data=post_data,
                        import_file=import_file,
                        delete_file=delete_file,
                        opt_post_data_kvpairs=opt_post_data_kvpairs,
                        limit=mtries,
                        wait_secs=mdelay,
                    )

                return f_retry_wrapper

            return deco_retry
            print("Completed API connection attempt")

    @_Decorators.retry(Exception)
    def _core_api_code(
        self,
        post_data,
        import_file=False,
        delete_file=False,
        opt_post_data_kvpairs=None,
        **kwargs
    ):
        """
            Common code elements to access Redcap API

            :param post_data:  String that had been formatted as a json object using json.dumps()
            :param opt_post_data_kvpairs:  Key value pairs to override POST data defaults.  Other
                    internal methods provide key checks for post fields; however, no such checks
                    are included if this override is used here.
            :param import_file:  bool.  Set to True when the import_file method is being used (import_file
                    and delete_file cannot both be True)
            :param delete_file:  bool.  Set to True when the delete_file method is being used

            :return: One of several types, depending on the call. Check Redcap documentation for any given method.
                    Returns CSV or JSON containing either the expected output or an error message for most calls.
                    Returns False when error encountered
                    Returns True after successfully deleting a file
                    Returns str after exporting a survey URL

            WARNING: Original code returned JSON responses from server. CSV, XML and other export formats were not supported.
            This code is currently being updated to support REDCap CSV exports and a broader set of REDCap export methods.  
        """
        self.last_status_code = ""
        self.last_response = ""

        if opt_post_data_kvpairs is None:
            opt_post_data_kvpairs = {}

        assert isinstance(
            post_data, dict
        ), "{} passed to core_api_code method \
            expected a dict but received a {} object".format(
            post_data, type(post_data)
        )

        if opt_post_data_kvpairs is not None:
            for key, value in opt_post_data_kvpairs.items():
                post_data[key] = value
      
        try:
            self.last_status_code = r.status_code
            self.last_response = r

            if r.status_code != 200:
                msg = "Critical: Redcap server returned a {} status code. ".format(
                    r.status_code
                )
                print(msg)
                return False
              
            else:
            return True

    def _api_error_handler(self, error_message):
        # TODO
        print(
            "From __api_error_handler__ (this output may be expected in a unit test):",
            error_message,
        )

    @staticmethod
    def _find_url(str_to_parse):
        """
            Ref: https://www.geeksforgeeks.org/python-check-url-string/
        :param str_to_parse: str
        :return: str, URL of the first URL found in the supplied str argument
        """

        url_list = re.findall(
            "http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]| [! *(),] | (?: %[0-9a-fA-F][0-9a-fA-F]))+",
            str_to_parse,
        )
        return url_list[0] if len(url_list) > 0 else ""

    def _check_args(self, limit, wait_secs):
        """
        Check and replace invalid args passed to instance methods with new defaults
        :param limit: int >= 1
        :param wait_secs: int >= 0
        :return: collections.namedtuple of limit and wait_secs
        """

        if (not isinstance(limit, int)) or (isinstance(limit, int) and limit < 1):
            limit = 1
        if (not isinstance(wait_secs, int)) or (
            isinstance(wait_secs, int) and wait_secs < 0
        ):
            wait_secs = 1

        ARGS = namedtuple("ARGS", "limit wait_secs")
        rv = ARGS(limit=limit, wait_secs=wait_secs)

        return rv

    def export_events(self, limit=3, wait_secs=3, **kwargs):
        """
            Export events from Redcap

            :param limit: int, >= 1, max number of recursive attempts
            :param wait_secs: int, >= 0, number of secs to wait between API calls

            WARNING: Not all optional arguments have been tested.  Defaults are set in post_data.

            Note that the format for returned data is the format field, not the returnFormat field.

            Example of returned content (JSON):
                [{"event_name":"Baseline","arm_num":"2","day_offset":"0","offset_min":"0",
                "offset_max":"0", "unique_event_name":"baseline_arm_2","custom_event_label":null}]

        :param kwargs:
            token: {your token}
            content: event
            format: json/csv
            arms: a comma separated string of arm numbers that you wish to pull events for (Default = all arms)
            returnFormat: json/csv

        :return: object in specified format (json or csv) containing either the expected output or an error message from __core_api_code__ method
        """

        checked_args = self._check_args(limit=limit, wait_secs=wait_secs)
        limit = checked_args.limit
        wait_secs = checked_args.wait_secs

        post_data = {
            "token": self._redcap_token,
            "content": "event",
            "format": "csv",
            "returnFormat": "csv",
        }

        if kwargs is not None:
            for key, value in kwargs.items():
                if (
                    key
                    in ["token", "content", "format", "arms", "returnFormat"]
                    + self.retry_keys
                ):
                    post_data[key] = kwargs[key]
                else:
                    print("{} is not a valid key".format(key))

        return self._core_api_code(
            post_data=post_data, limit=limit, wait_secs=wait_secs
        )

    def export_data_dictionary(self, limit=3, wait_secs=3, **kwargs):
        """
            Export the data definitions.

            Any changes to the POST data will be passed entirely to core_api_code method to
                replace the default POST options.
            Note that the format for returned data is the format field, not the returnFormat field.

            :param limit: int, >= 1, max number of recursive attempts
            :param wait_secs: int, >= 0, number of secs to wait between API calls
            :param kwargs: Available options (check post_data for defaults)
                token: {your token}
                content: metadata
                format: json/csv

                OPTIONAL
                --------
                fields: string (Comma separated if multiple)
                forms: string (Comma separated if multiple)
                returnFormat: json/csv

            :return: object in specified format (json or csv) containing either the expected output or an error message from
                    __core_api_code__ method
        """

        checked_args = self._check_args(limit=limit, wait_secs=wait_secs)
        limit = checked_args.limit
        wait_secs = checked_args.wait_secs

        post_data = {
            "token": self._redcap_token,
            "content": "metadata",
            "format": "csv",
            "returnFormat": "csv",
        }

        if kwargs is not None:
            for key, value in kwargs.items():
                if (
                    key
                    in ["token", "content", "format", "fields", "forms", "returnFormat"]
                    + self.retry_keys
                ):
                    post_data[key] = kwargs[key]
                else:
                    print("{} is not a valid key".format(key))

        return self._core_api_code(
            post_data=post_data, limit=limit, wait_secs=wait_secs
        )

    def export_records(self, limit=5, wait_secs=3, **kwargs):
        """
            Export records (study data) from Redcap.

            WARNING: Not all optional arguments have been tested.  Defaults are set in post_data.

            Any changes to the POST data will be passed entirely to core_api_code method to
                replace the default POST options.
            Note that the format for returned data is the format field, not the returnFormat field.

            Example usage: Export all records that have been added or changed since last export (dateRangeBegin) 
                from redcap.redcapy import Redcapy
                redcap_token = os.environ['your project token string']
                redcap_url = os.environ['redcap server url']
                rc = Redcapy(api_token=redcap_token, redcap_url=redcap_url)
                data_export = rc.export_records(rawOrLabel='raw',
                                    fields='consent_date, randomization_id, record_id')

            :param limit: int, >= 1, max number of recursive attempts
            :param wait_secs: int, >= 0, number of secs to wait between API calls
            :param kwargs: Available options
                token: {your token}
                content: record
                action: export
                format: json/csv/xml
                type: flat/eav
                csvDelimiter: '' or other delimiter
                rawOrLabel: raw/label
                rawOrLabelHeaders: raw/label
                exportCheckboxLabel: false/true
                exportSurveyFields: false/true
                exportDataAccessGroups: false/true
                returnFormat: json/csv/xml
                dateRangeBegin: yyyy-mm-dd hh:mm:ss
                dateRangeEnd: defaults to current datetime
                exportBlankForGrayFormStatus: false/true
                fields: string (Comma separated as a single string, not list, if multiple)
                forms: string (Comma separated as a single string, not list, if multiple)
                events: string (Comma separated as a single string, not list, if multiple)

            :return object in specified format (json or csv) containing either the expected output or an error message from
                    __core_api_code__ method, or False if self._core_api_code fails
        """

        checked_args = self._check_args(limit=limit, wait_secs=wait_secs)
        limit = checked_args.limit
        wait_secs = checked_args.wait_secs

        # TODO Add handling of record filter, in the form of record[0], record[1], etc.
        # TODO Add way to set dateRangeBegin to time of the last export (or current minus one week)
        post_data = {
            "token": self._redcap_token,
            "content": "record",
            "format": "csv",
            "type": "flat",
            "csvDelimiter": '',
            "rawOrLabel": "raw",
            "rawOrLabelHeaders": "raw",
            "exportCheckboxLabel": "false",
            "exportSurveyFields": "true",
            "exportDataAccessGroups": "true",
            "returnFormat": "csv",
            "dateRangeBegin":"",
            "exportBlankForGrayFormStatus": "true"
        }

        if kwargs is not None:
            for key, value in kwargs.items():
                if (
                    key
                    in [
                        "fields",
                        "forms",
                        "events",
                        "records",
                        "token",
                        "content",
                        "format",
                        "type",
                        "rawOrLabel",
                        "rawOrLabelHeaders",
                        "exportCheckboxLabel",
                        "exportSurveyFields",
                        "exportDataAccessGroups",
                        "returnFormat",
                        "dateRangeBegin",
                        "dateRangeEnd",
                        "exportBlankForGrayFormStatus"
                    ]
                    + self.retry_keys
                ):
                    post_data[key] = kwargs[key]
                else:
                    print("{} is not a valid key".format(key))

        return self._core_api_code(
            post_data=post_data, limit=limit, wait_secs=wait_secs
        )

 def export_field_names(self, limit=3, wait_secs=3, **kwargs):
        """
            Export_field_names provides the list of field names (including checkbox variables) which can be compared more easily than the metadata
            files to determine if any changes to the data schema have been made. This table can also serve as the basis for mapping variable names between
            REDCap and target database tables.
            Any changes to the POST data will be passed entirely to core_api_code method to
                replace the default POST options.
            Note that the format for returned data is the format field, not the returnFormat field.
            :param limit: int, >= 1, max number of recursive attempts
            :param wait_secs: int, >= 0, number of secs to wait between API calls
            :param kwargs: Available options (check post_data for defaults)
                token: {your token}
                content: exportFieldNames
                format: json/csv
                OPTIONAL
                --------
                returnFormat: json/csv
            :return: object in specified format (json or csv) containing either the expected output or an error message from
                    __core_api_code__ method
        """

        checked_args = self._check_args(limit=limit, wait_secs=wait_secs)
        limit = checked_args.limit
        wait_secs = checked_args.wait_secs

        post_data = {
            "token": self._redcap_token,
            "content": "exportFieldNames",
            "format": "csv",
            "returnFormat": "csv",
        }

        if kwargs is not None:
            for key, value in kwargs.items():
                if (
                    key
                    in ["token", "content", "format", "returnFormat"]
                    + self.retry_keys
                ):
                    post_data[key] = kwargs[key]
                else:
                    print("{} is not a valid key".format(key))

        return self._core_api_code(
            post_data=post_data, limit=limit, wait_secs=wait_secs
        )   

 def export_reports(self, limit=3, wait_secs=3, **kwargs):
        """
            Export_reports allows flexibility to build and preview reports within REDCap using advanced filters, and then export the resulting data.
            One caveat is that while the report data updates dynamically, fields that are added to an instrument after defining the report
            will not be included. New fields will be displayed as unchecked within the REDCap report definition. Make changes to the 
            report by selecting the fieldnames and saving the report changes. These changes must also be made within the schema for the target table.   
            
            Any changes to the POST data will be passed entirely to core_api_code method to replace the default POST options.
            Note that the format for returned data is the format field, not the returnFormat field.
            :param limit: int, >= 1, max number of recursive attempts
            :param wait_secs: int, >= 0, number of secs to wait between API calls
            :param kwargs: Available options (check post_data for defaults)
                token: {your token}
                content: exportFieldNames
                format: json/csv
                report_id: [a # associated with each report, displayed in top right of the REDCap report definition page]
                csvDelimiter:'' (default for CSV or another delimiter may be substituted)
                rawOrLabel: raw/label
                rawOrLabelHeaders: raw/label
                exportCheckboxLabel: true/false
                OPTIONAL
                --------
                returnFormat: json/csv
            :return: object in specified format (json or csv) containing either the expected output or an error message from
                    __core_api_code__ method
                    
            TODO: replace static report_id with list of reports to be exported.
        """

        checked_args = self._check_args(limit=limit, wait_secs=wait_secs)
        limit = checked_args.limit
        wait_secs = checked_args.wait_secs

        post_data = {
            "token": self._redcap_token,
            "content": "report",
            "format": "csv",
            "report_id":"4792",
            'csvDelimiter': '',
            'rawOrLabel': 'raw',
            'rawOrLabelHeaders': 'raw',
            'exportCheckboxLabel': 'false',
            "returnFormat": "csv",
        }

        if kwargs is not None:
            for key, value in kwargs.items():
                if (
                    key
                    in ["token", "content", "format", "returnFormat"]
                    + self.retry_keys
                ):
                    post_data[key] = kwargs[key]
                else:
                    print("{} is not a valid key".format(key))

        return self._core_api_code(
            post_data=post_data, limit=limit, wait_secs=wait_secs
        )   
    
    
    
    
    
    
    
    
    
if __name__ == "__main__":
    
    """
        Sample usage below using command line args for Redcap tokens.
    """
    import os
    import sys
    from pprint import pprint

    def export_from_redcap(rc_instance, **kwargs):
        response = rc_instance.export_records(**kwargs)

        if response and "error" not in response:
            return response
        else:
            export_msg = "Failed to export records from Redcap for {}. Server returned: {}".format(
                response
            )
            print(export_msg)

    if sys.argv[1] and sys.argv[2]:
        try:
            redcap_url = os.environ[sys.argv[1]]
            redcap_token = os.environ[sys.argv[2]]

            # Redcap instance
            rc = Redcapy(api_token=redcap_token, redcap_url=redcap_url)

            rc_export_raw = export_from_redcap(rc_instance=rc, rawOrLabel="raw")
            pprint(rc_export_raw[0])
        except Exception as e:
            print("Unable to export records from Redcap using provided credentials")
