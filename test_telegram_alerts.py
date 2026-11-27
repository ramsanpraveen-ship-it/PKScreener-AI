import unittest
from unittest.mock import Mock

from telegram_alerts import format_candidate_alert, send_telegram_alert


class TelegramAlertTests(unittest.TestCase):
    def setUp(self):
        self.scan = {
            "status": "FRESH", "expected_session": "2026-11-27",
            "candidates": [
                {"symbol": "TCS", "candidate_status": "SETUP_WATCH"},
                {"symbol": "INFY", "candidate_status": "BREAKOUT_CONFIRMED"},
                {"symbol": "ABC", "candidate_status": "NOT_QUALIFIED"},
            ],
        }

    def test_alert_contains_only_fresh_qualified_candidates(self):
        message = format_candidate_alert(self.scan)
        self.assertIn("NSE 2026-11-27", message)
        self.assertIn("TCS — SETUP_WATCH", message)
        self.assertIn("INFY — BREAKOUT_CONFIRMED", message)
        self.assertNotIn("ABC", message)

    def test_stale_scan_fails_before_network(self):
        post = Mock()
        with self.assertRaisesRegex(ValueError, "fresh validated scan"):
            send_telegram_alert({**self.scan, "status": "STALE"}, "token", "chat", post)
        post.assert_not_called()

    def test_missing_configuration_fails_before_network(self):
        post = Mock()
        with self.assertRaisesRegex(ValueError, "not configured"):
            send_telegram_alert(self.scan, "", "chat", post)
        post.assert_not_called()

    def test_manual_send_uses_configured_chat(self):
        response = Mock()
        response.json.return_value = {"ok": True}
        post = Mock(return_value=response)
        result = send_telegram_alert(self.scan, "secret-token", "chat-id", post)
        self.assertEqual(result["candidate_count"], 2)
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.telegram.org/botsecret-token/sendMessage")
        self.assertEqual(kwargs["json"]["chat_id"], "chat-id")
        self.assertEqual(kwargs["timeout"], 10)

    def test_delivery_error_does_not_expose_token(self):
        post = Mock(side_effect=RuntimeError("network error"))
        with self.assertRaisesRegex(RuntimeError, "delivery failed") as caught:
            send_telegram_alert(self.scan, "secret-token", "chat-id", post)
        self.assertNotIn("secret-token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
