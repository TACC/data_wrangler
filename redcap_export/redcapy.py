"""
    Redcapy.py interacts with more commonly used Redcap 8.5/9.0 API endpoints.  Tested with Python 3.6/7

    Note that the methods using self._core_api_code may return False to other instance methods
    in the event of a connection failure, in lieu of an expected response.
"""

import attr
import json
import re
import requests
import time

from bs4 import BeautifulSoup
from collections import namedtuple
from functools import wraps
from validator_collection import checkers


@attr.s
class Redcapy:
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
                    Returns JSON containing either the expected output or an error message for most calls.
                    Returns False when error encountered
                    Returns True after successfully deleting a file
                    Returns str after exporting a survey URL

            WARNING: Code has only been tested to return JSON responses from server. CSV or XML not yet supported.
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
            if import_file:
                files = {"file": open(post_data["file"], "rb")}

                r = requests.post(self.redcap_url, data=post_data, files=files)
            else:
                # Added 'identity' value to override default use of gzip and deflate, which can cause requests module
                # to fail in the apparent presence of improper data in the Redcap project.
                r = requests.post(
                    self.redcap_url,
                    data=post_data,
                    headers={"Accept-Encoding": "identity"},
                )

            self.last_status_code = r.status_code
            self.last_response = r

            if (
                r.status_code == 400
                and json.loads(r.text)["error"]
                == "There is no file to delete for this record"
            ):
                print(json.loads(r.text)["error"])
                return True
            elif r.status_code != 200:
                msg = "Critical: Redcap server returned a {} status code. ".format(
                    r.status_code
                )

                try:
                    return_soup = BeautifulSoup(str(r.text), "xml")
                    msg += "Error received from Redcap: {}".format(
                        return_soup.hash.error.get_text()
                    )
                except Exception as e:
                    msg += "Error received from Redcap: {}".format(r.text)

                print(msg)

                return False
        except Exception as e:
            msg = "Redcapy: Error received when connecting to Redcap using requests.post(). Error: {}".format(
                e
            )
            print(msg)
            return False

        return_value = r.text

        # export_survey_link returns a URL as a str, so try this first
        if return_value and isinstance(return_value, str):
            if self._find_url(return_value) == return_value:
                return return_value

        if delete_file and len(return_value) == 0:
            return True

        if (len(return_value) > 0 and import_file) or not import_file:
            try:
                return json.loads(return_value)
            except Exception as e:  # delete method on error returns xml
                try:
                    return_soup = BeautifulSoup(str(return_value), "xml")
                    return return_soup.hash.error.get_text()
                except Exception as e2:
                    print(
                        "Error: Data returned from Redcap was not a JSON nor XML object. Data: ",
                        return_value,
                    )
                    return return_value
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

            Example of returned content:
                [{"event_name":"Baseline","arm_num":"2","day_offset":"0","offset_min":"0",
                "offset_max":"0", "unique_event_name":"baseline_arm_2","custom_event_label":null}]

        :param kwargs:
            token: {your token}
            content: event
            format: json/csv/xml
            arms: a comma separated string of arm numbers that you wish to pull events for (Default = all arms)
            returnFormat: json/csv/xml

        :return: JSON object containing either the expected output or an error message from __core_api_code__ method
        """

        checked_args = self._check_args(limit=limit, wait_secs=wait_secs)
        limit = checked_args.limit
        wait_secs = checked_args.wait_secs

        post_data = {
            "token": self._redcap_token,
            "content": "event",
            "format": "json",
            "returnFormat": "json",
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
                format: json/csv/xml

                OPTIONAL
                --------
                fields: string (Comma separated if multiple)
                forms: string (Comma separated if multiple)
                returnFormat: json/csv/xml

            :return: JSON object containing either the expected output or an error message from
                    __core_api_code__ method
        """

        checked_args = self._check_args(limit=limit, wait_secs=wait_secs)
        limit = checked_args.limit
        wait_secs = checked_args.wait_secs

        post_data = {
            "token": self._redcap_token,
            "content": "metadata",
            "format": "json",
            "returnFormat": "json",
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

    def export_survey_link(
        self, instrument, event, record, limit=3, wait_secs=3, **kwargs
    ):
        """
            Export a survey link to a single survey based on required arguments.

            Any changes to the POST data will be passed entirely to core_api_code method to
                replace the default POST options.
            Note that the format for returned data is the format field, not the returnFormat field.

            :param instrument: Redcap instrument name
            :param event: Redcap event name
            :param record: record_id
            :param limit: int, >= 1, max number of recursive attempts
            :param wait_secs: int, >= 0, number of secs to wait between API calls
            :param kwargs: Available options (check post_data for defaults)
                token: {your instance token}
                content: 'surveyLink' appears to be the only valid option
                format: json/csv/xml CSV and XML not yet implemented
                returnFormat: json/csv/xml CSV and XML not yet implemented

            :return: JSON object containing either the expected output or an error message from
                    __core_api_code__ method
        """

        checked_args = self._check_args(limit=limit, wait_secs=wait_secs)
        limit = checked_args.limit
        wait_secs = checked_args.wait_secs

        post_data = {
            "token": self._redcap_token,
            "content": "surveyLink",
            "format": "json",
            "instrument": instrument,
            "event": event,
            "record": record,
            "returnFormat": "json",
        }

        if kwargs is not None:
            for key, value in kwargs.items():
                if (
                    key
                    in ["token", "content", "format", "returnFormat"] + self.retry_keys
                ):
                    post_data[key] = kwargs[key]
                else:
                    print("{} is not a valid key".format(key))

        return_value = self._core_api_code(
            post_data=post_data, limit=limit, wait_secs=wait_secs
        )

        return return_value if return_value else ""

    def export_survey_participants(
        self, instrument, event, limit=3, wait_secs=3, **kwargs
    ):
        """
            Export full list of surveys for a combination of instrument and event

            Any changes to the POST data will be passed entirely to core_api_code method to
                replace the default POST options.
            Note that the format for returned data is the format field, not the returnFormat field.

            :param instrument: Redcap instrument name
            :param event: Redcap event name
            :param limit: int, >= 1, max number of recursive attempts
            :param wait_secs: int, >= 0, number of secs to wait between API calls
            :param kwargs: Available options (check post_data for defaults)
                token: {your instance token}
                content: metadata
                format: json/csv/xml
                returnFormat: json/csv/xml

            :return: JSON object containing either the expected output or an error message from
                    __core_api_code__ method
        """

        checked_args = self._check_args(limit=limit, wait_secs=wait_secs)
        limit = checked_args.limit
        wait_secs = checked_args.wait_secs

        post_data = {
            "token": self._redcap_token,
            "content": "participantList",
            "format": "json",
            "instrument": instrument,
            "event": event,
            "returnFormat": "json",
        }

        if kwargs is not None:
            for key, value in kwargs.items():
                if (
                    key
                    in ["token", "content", "format", "returnFormat"] + self.retry_keys
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

            Example usage:
                from redcap.redcapy import Redcapy
                redcap_token = os.environ['your project token string']
                redcap_url = os.environ['redcap server url']
                rc = Redcapy(api_token=redcap_token, redcap_url=redcap_url)
                data_export = rc.export_records(rawOrLabel='label',
                                    fields='consent_date, randomization_id, record_id')

            :param limit: int, >= 1, max number of recursive attempts
            :param wait_secs: int, >= 0, number of secs to wait between API calls
            :param kwargs: Available options
                token: {your token}
                content: record
                format: json/csv/xml
                type: flat/eav
                rawOrLabel: raw/label
                rawOrLabelHeaders: raw/label
                exportCheckboxLabel: false/true
                exportSurveyFields: false/true
                exportDataAccessGroups: false/true
                returnFormat: json/csv/xml
                fields: string (Comma separated as a single string, not list, if multiple)
                forms: string (Comma separated as a single string, not list, if multiple)
                events: string (Comma separated as a single string, not list, if multiple)

            :return JSON object containing either the expected output or an error message from
                    __core_api_code__ method, or False if self._core_api_code fails
        """

        checked_args = self._check_args(limit=limit, wait_secs=wait_secs)
        limit = checked_args.limit
        wait_secs = checked_args.wait_secs

        # TODO Add handling of record filter, in the form of record[0], record[1], etc.
        # TODO Add more defaults to method parameter list
        post_data = {
            "token": self._redcap_token,
            "content": "record",
            "format": "json",
            "type": "flat",
            "rawOrLabel": "raw",
            "rawOrLabelHeaders": "raw",
            "exportCheckboxLabel": "false",
            "exportSurveyFields": "false",
            "exportDataAccessGroups": "false",
            "returnFormat": "json",
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
                    ]
                    + self.retry_keys
                ):
                    post_data[key] = kwargs[key]
                else:
                    print("{} is not a valid key".format(key))

        return self._core_api_code(
            post_data=post_data, limit=limit, wait_secs=wait_secs
        )

    def import_records(self, data_to_upload, **kwargs):
        """
            Upload single records into Redcap.  Bulk imports have not been tested.
            Note the post_data format field should match the data of the data field
            JSON data should be passed in as a string, formatted to dump into JSON format, or a list that can
                be dumped into JSON.
            When passed as a jaon formatted string, the json should be enclosed with [].  If not present, then this
                will add [].
            So the tested json data_to_upload format is a dict wrapped by json.dumps

            Example USAGE:

                If using a pandas Dataframe, for example, at minimum it needs to have the following column names:
                  record_id
                  redcap_event_name

                For a repeating instrument, it should also have
                 redcap_repeat_instrument (form name)
                 redcap_repeat_instance (int, one-based, not zero-based)

                And of course the name of any other valid Redcap fields
                To update the form completion status, the column name is typically the form name (underscores for blanks),
                followed by _complete.  The name can be verified by exporting from the API Playground in Redcap.
                Then use data values of 0 or 1 or 2 for various completion states.  Form completion status is optional.

                df_to_upload = pd.DataFrame('Your Data')
                for i in range(len(df_to_upload)):
                    record_to_upload = df_to_upload.iloc[i].to_json(orient='columns')
                    import_return = rc.import_records(data_to_upload=record_to_upload)

                It is your responsibility to check the response above and react to errors for each record.  Despite the
                small performance overhead of single vs. bulk record imports, this makes it easy to manage exceptions
                and retries.


            WARNING: Not all optional arguments have been tested.  Defaults are set in post_data.


            :param data_to_upload: json str
            :param kwargs:  Available options (check post_data for defaults)
                token: {your token}
                content: record
                format: json/csv/xml
                type: flat/eav
                overwriteBehavior: normal/overwrite (Use overwrite to overwrite non-null fields with empty strings)
                data: {your data}
                dateFormat: MDY, DMY, YMD: NOTE: The default format is Y-M-D (with dashes), while MDY and DMY
                        values should always be formatted as M/D/Y or D/M/Y (with slashes), respectively.
                returnContent: count/ids/nothing
                returnFormat: json/csv/xml

            :return: JSON object containing either the expected output or an error message from__core_api_code__ method
                Server response contains an 'error' key if an error occurs.
                Otherwise returns a count of successful imports by default.
        """

        post_data = {
            "token": self._redcap_token,
            "content": "record",
            "format": "json",
            "type": "flat",
            "overwriteBehavior": "normal",
            "data": data_to_upload,
            "dateFormat": "YMD",
            "returnContent": "count",
            "returnFormat": "json",
        }

        if kwargs is not None:
            for key, value in kwargs.items():
                if (
                    key
                    in [
                        "token",
                        "content",
                        "format",
                        "type",
                        "overwriteBehavior",
                        "data",
                        "dateFormat",
                        "returnContent",
                        "returnFormat",
                    ]
                    + self.retry_keys
                ):
                    post_data[key] = kwargs[key]
                else:
                    print("{} is not a valid key".format(key))

        if post_data["format"] == "json":
            if type(data_to_upload) == str:
                if data_to_upload[:1] != "[":
                    try:
                        json.loads(data_to_upload)
                        data_to_upload = json.dumps([json.loads(data_to_upload)])
                        post_data["data"] = data_to_upload
                    except Exception as e:
                        print(
                            "Please check if the data_to_upload field is formatted properly for conversion to JSON\n"
                        )
        else:
            # TODO
            pass

        return self._core_api_code(post_data=post_data)

    def delete_record(self, id_to_delete, **kwargs):
        """
            Delete a single record from Redcap.
            This has been reduced from a more general multiple record delete, which requires additional
                keys in the format of record[0], record[1], record[2], ...
            To delete multiple records, iterate a list of IDs in a loop, which is acceptable for small scale deletes

            WARNING: Not all optional arguments have been tested.  Defaults are set in post_data.

            :param id_to_delete: str
            :param kwargs: Available options (check post_data for defaults)
                token: {your token}
                content: record
                format: json/csv/xml
                records[0]: id string
                arm: optional (longitudinal study may have multiple arms, so specify a single arm, else delete from all)

            :return: The number of records deleted
        """

        post_data = {
            "token": self._redcap_token,
            "action": "delete",
            "content": "record",
            "records[0]": id_to_delete,
        }

        if kwargs is not None:
            for key, value in kwargs.items():
                if key in ["token", "content", "records[0]", "arm"] + self.retry_keys:
                    post_data[key] = kwargs[key]
                else:
                    print("{} is not a valid key".format(key))

        return self._core_api_code(post_data=post_data)

    def delete_form(self, id, field, event, repeat_instance, **kwargs):
        """
            Delete a single field from a form in Redcap.
            This has been reduced from a more general multiple record delete, which requires additional
                keys in the format of record[0], record[1], record[2], ...

            WARNING: Not all optional arguments have been tested.  Defaults are set in post_data.

            :param id: str
            :param field: str
            :param event: str
            :param repeat_instance: str
            :param kwargs: Available options (check post_data for defaults)
                token: {your token}
                content: record
                format: json/csv/xml
                records[0]: id string
                arm: optional (longitudinal study may have multiple arms, so specify a single arm, else delete from all)

            :return: The number of records deleted
        """

        post_data = {
            "token": self._redcap_token,
            "content": "file",
            "action": "delete",
            "record": id,
            "field": field,
            "event": event,
            "repeat_instance": repeat_instance,
        }

        if kwargs is not None:
            for key, value in kwargs.items():
                if (
                    key
                    in [
                        "token",
                        "content",
                        "action",
                        "records[0]",
                        "field",
                        "event",
                        "repeat_instance",
                    ]
                    + self.retry_keys
                ):
                    post_data[key] = kwargs[key]
                else:
                    print("{} is not a valid key".format(key))

        return self._core_api_code(post_data=post_data)

    def import_file(
        self, record_id, field, event, filename, repeat_instance=None, **kwargs
    ):
        """
            Upload a file into Redcap.

            Example Usage:
                from redcap.redcapy import Redcapy
                redcap_token = os.environ['your project token string']
                redcap_url = os.environ['redcap server url']
                rc = Redcapy(api_token=redcap_token, redcap_url=redcap_url)
                html_full_path = os.path.abspath('my_filename.html')
                import_response = rc.import_file(event='data_import_arm_1',
                                                 field='redcap_field_name',
                                                 filename=html_full_path,
                                                 record_id='1',
                                                 repeat_instance='2',
                                                )
                # import_response is null if upload is successful

            :param data_to_upload: json str
            :param record_id: record_id
            :param field: field name of field in Redcap
            :param event: event name in Redcap
            :param filename: file name (on local system) to import
            # Note that unlike a data import, this next param is not called redcap_repeat_instance
            :param repeat_instance: optional
            :param kwargs:  Available options (check post_data for defaults)
                token: {your token}

            :return: None if successful, else potentially useful debugging info is returned
        """
        post_data = {
            "token": self._redcap_token,
            "content": "file",
            "format": "json",
            "action": "import",
            "record": record_id,
            "field": field,
            "event": event,
            "returnFormat": "json",
            "file": filename,
        }

        if repeat_instance:
            post_data["repeat_instance"] = str(repeat_instance)

        if kwargs is not None:
            for key, value in kwargs.items():
                if (
                    key
                    in [
                        "token",
                        "content",
                        "format",
                        "action",
                        "record",
                        "field",
                        "event",
                        "returnContent",
                        "file",
                    ]
                    + self.retry_keys
                ):
                    post_data[key] = str(kwargs[key])
                else:
                    print("{} is not a valid key".format(key))

            if "action" in kwargs and kwargs["action"] in ["export", "delete"]:
                post_data.pop("file")

        else:
            # TODO
            pass

        if "action" in kwargs and kwargs["action"] in ["delete"]:
            return self._core_api_code(post_data=post_data, delete_file=True)
        elif "action" in kwargs and kwargs["action"] in ["export"]:
            print("File export method not yet implemented")
            return False
        else:
            return self._core_api_code(post_data=post_data, import_file=True)

    def export_file(self, record_id, field, event, repeat_instance=None):
        """
            Identical to import file method, except for the action parameter, to export a file
        """
        pass  # TODO

        # return self.import_file(record_id=record_id, field=field, event=event, filename=None,
        #                         repeat_instance=repeat_instance, action='export')

    def delete_file(self, record_id, field, event, repeat_instance=None):
        """
            Identical to import file method, except for the action parameter, to delete a file
        """
        return self.import_file(
            record_id=record_id,
            field=field,
            event=event,
            filename=None,
            repeat_instance=repeat_instance,
            action="delete",
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
