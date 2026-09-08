import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from bank_client import BankClient, load_config


class BankTests(unittest.TestCase):
    def setUp(self):
        self.values = dict(POPBILL_LINK_ID='fake-link', POPBILL_SECRET_KEY='fake-secret',
                           POPBILL_CORP_NUM='1234567890', POPBILL_BANK_CODE='0004',
                           POPBILL_ACCOUNT_NUMBER='123456789', QUERY_START_DATE='20260907',
                           QUERY_END_DATE='20260908')
        self.config = load_config(self.values, date(2026, 9, 8))
        self.service = Mock()
        self.client = BankClient(self.config, self.service)

    def test_invalid_config(self):
        for key, value in [('POPBILL_SECRET_KEY', ''), ('POPBILL_IS_TEST', 'yes'),
                           ('QUERY_START_DATE', '20260230'), ('QUERY_END_DATE', '20260906'),
                           ('POLL_INTERVAL_SECONDS', 'nan'), ('POPBILL_BANK_CODE', '004')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                load_config({**self.values, key: value}, date(2026, 9, 8))

    def test_default_korean_date_range(self):
        c = load_config({**self.values, 'QUERY_START_DATE': '', 'QUERY_END_DATE': ''}, date(2026, 9, 8))
        self.assertEqual((c['start_date'], c['end_date']), ('20260907', '20260908'))
        self.assertTrue(c['is_test'])

    def test_poll_success_and_failure(self):
        self.service.getJobState.side_effect = [SimpleNamespace(jobState='2'), SimpleNamespace(jobState='3', errorCode=1)]
        self.assertEqual(self.client.wait_for_job('fake-job', sleep=lambda _: None)['errorCode'], 1)
        self.service.getJobState.side_effect = None
        self.service.getJobState.return_value = SimpleNamespace(jobState=3, errorCode=-1)
        with self.assertRaisesRegex(RuntimeError, '수집 실패'):
            self.client.wait_for_job('fake-job')
        self.service.search.assert_not_called()

    def test_poll_timeout(self):
        self.service.getJobState.return_value = SimpleNamespace(jobState=2)
        ticks = iter([0, 0, 181, 181])
        with self.assertRaises(TimeoutError):
            self.client.wait_for_job('fake-job', sleep=lambda _: None, clock=lambda: next(ticks))

    def test_pagination_and_empty(self):
        self.service.search.side_effect = [SimpleNamespace(list=[{'balance': '9007199254740993'}, {'balance': '2'}]),
                                          SimpleNamespace(list=[{'balance': '3'}])]
        rows = self.client.transactions('fake-job', per_page=2)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['balance'], '9007199254740993')
        self.assertEqual(self.service.search.call_args_list[1].args[4], 2)
        self.service.search.side_effect = None
        self.service.search.return_value = SimpleNamespace(list=[])
        self.assertEqual(self.client.transactions('fake-job'), [])

    def test_error_redaction(self):
        self.service.requestJob.side_effect = ValueError('fake-secret 123456789')
        with self.assertRaises(RuntimeError) as caught:
            self.client.request_job()
        self.assertNotIn('fake-secret', str(caught.exception))
        self.assertNotIn('123456789', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
