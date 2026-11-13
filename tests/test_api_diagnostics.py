import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests
import trendyol_labels


class TestApiDiagnostics(unittest.TestCase):
    def test_authentication_error_is_actionable_without_response_body(self):
        response = SimpleNamespace(
            status_code=403,
            content=b"credential-reflected-response",
            headers={"x-request-id": "request-123"},
            text="credential-reflected-response",
        )

        with patch("requests.get", return_value=response), \
                patch("core.logger.log") as log:
            with self.assertRaises(SystemExit) as raised:
                trendyol_labels._get(
                    "https://example.test/orders",
                    {"Authorization": "Basic never-log-this"},
                    {"status": "Created", "page": 0},
                )

        self.assertIn("HTTP 403", str(raised.exception))
        self.assertNotIn("credential-reflected-response", str(raised.exception))
        self.assertNotIn("never-log-this", " ".join(str(call) for call in log.call_args_list))

    def test_network_failure_logs_exception_type_without_request_credentials(self):
        with patch("requests.get", side_effect=requests.ConnectionError()), \
                patch("core.logger.log") as log:
            with self.assertRaisesRegex(RuntimeError, "network request failed"):
                trendyol_labels._get(
                    "https://example.test/orders",
                    {"Authorization": "Basic never-log-this"},
                    {"status": "Created", "page": 0},
                )

        message = " ".join(str(call) for call in log.call_args_list)
        self.assertIn("ConnectionError", message)
        self.assertNotIn("never-log-this", message)


if __name__ == "__main__":
    unittest.main()
