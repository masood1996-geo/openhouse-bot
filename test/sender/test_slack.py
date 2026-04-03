import unittest

import requests_mock

from openhouse.notifiers import SenderSlack
from openhouse.config import YamlConfig


class SenderSlackTest(unittest.TestCase):

    @requests_mock.Mocker()
    def test_send_message(self, m):
        sender = SenderSlack(YamlConfig({"slack": {
            "webhook_url": "http://hooks.slack.com/dummy_webhook_url"}}))

        m.post("http://hooks.slack.com/dummy_webhook_url")
        self.assertEqual(None, sender.notify("result"),
                         "Expected message to be sent")
