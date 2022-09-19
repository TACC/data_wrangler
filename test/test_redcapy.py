import os
import unittest
import requests

from redcapy import Redcapy


class TestRedcapy(unittest.TestCase):
    """
        Note that when checking the Redcap log, the order of operations may not correspond to the order of tests
        in code because test execution order is arbitrary.
    """
    @classmethod
    def setUpClass(cls) -> None:
        # Substitute values as needed
        cls.redcap_url = os.environ['REDCAP_URL']
        cls.redcap_token = os.environ['REDCAP_API_CAPS_DEMO']
        cls.rc = Redcapy(api_token=cls.redcap_token, redcap_url=cls.redcap_url)
        print('Using', cls.rc)

    def test_correct_init(self):
        self.assertEqual(self.redcap_url, self.rc.redcap_url)
        self.assertEqual(self.redcap_token, self.rc._redcap_token)

    def test_null_args(self):
        self.assertRaises(ValueError, Redcapy, api_token=self.redcap_token, redcap_url='')
        self.assertRaises(ValueError, Redcapy, api_token='', redcap_url=self.redcap_url)
        self.assertRaises(ValueError, Redcapy, api_token='', redcap_url='')

    def test_malformed_url(self):
        """
            This will capture most, but not all possible types of malformed URLs.
            For instance, invalid top level domain names will pass
        """
        self.assertRaises(ValueError, Redcapy, api_token=self.redcap_token, redcap_url='http:/redcap.ucsf.edu')
        self.assertRaises(ValueError, Redcapy, api_token=self.redcap_token, redcap_url='http://redcap.ucsf,edu')
        self.assertRaises(ValueError, Redcapy, api_token=self.redcap_token, redcap_url='redcap.ucsf.edu')
        self.assertRaises(ValueError, Redcapy, api_token=self.redcap_token, redcap_url='http://redcap,')

    # def test_export_events(self):
    #     self.fail()
    #
    # def test_export_data_dictionary(self):
    #     self.fail()
    #
    # def test_export_survey_link(self):
    #     self.fail()
    #
    # def test_export_survey_participants(self):
    #     self.fail()
    #
    # def test_export_records(self):
    #     self.fail()
    #
    # def test_import_records(self):
    #     self.fail()
    #
    # def test_delete_record(self):
    #     self.fail()
    #
    # def test_delete_form(self):
    #     self.fail()
    #
    def test_import_file(self):
        """
            This test presupposes some data has been populated into the test project.
            It will discover a list of existing record ids.
            Adjust test data as required to reflect data
        :return:
        """
        rc_export = self.rc.export_records()
        record_ids = list(set(d['record_id'] for d in rc_export))
        invalid_test_id = ''
        valid_test_id = record_ids[0]

        for rid in list(range(100000)):
            if str(rid) not in record_ids:
                invalid_test_id = str(rid)
                break

        response = requests.get('http://lorempixel.com/400/200', stream=True)
        filename = 'test_img.png'

        with open(filename, 'wb') as f:
            f.write(response.content)

        del response

        # This is expected to fail and Redcapy will print an error as a result, which can be ignored
        rv = self.rc.import_file(
            record_id=invalid_test_id,
            field='exam_photo',
            event='6_month_arm_2',
            filename=filename,
        )
        self.assertFalse(rv, 'Result of importing file when no valid record id exists should be False')

        if valid_test_id:
            rv = self.rc.import_file(
                record_id=valid_test_id,
                field='exam_photo',
                event='6_month_arm_2',
                filename=filename,
            )
            self.assertTrue(rv, 'Expected to receive True as result of importing file')
        else:
            assert ValueError, 'No valid records found in test project'

    #
    # def test_export_file(self):
    #     self.fail()
    #

    def test_delete_file(self):
        """
            First, import a file, then delete it.  Results can be verified in the Redcap log.
        """
        rc_export = self.rc.export_records()
        record_ids = sorted(list(set(d['record_id'] for d in rc_export)))
        valid_test_id = record_ids[0]

        if valid_test_id:
            response = requests.get('http://lorempixel.com/400/200')
            filename = 'test_img.png'

            with open(filename, 'wb') as f:
                f.write(response.content)
            del response

            field = 'exam_photo'
            event = '6_month_arm_2'

            rv = self.rc.import_file(
                record_id=valid_test_id,
                field=field,
                event=event,
                filename=filename,
            )
            self.assertTrue(rv, 'Expected to receive True as result of importing file')

            rv = self.rc.delete_file(
                record_id=valid_test_id,
                field=field,
                event=event,
            )
            self.assertTrue(rv, 'Expected to receive True as result of deleting file')
        else:
            assert ValueError, 'No valid records found in test project'


if __name__ == '__main__':
    unittest.main()
