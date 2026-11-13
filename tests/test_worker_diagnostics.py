import builtins
import unittest
from unittest.mock import patch

from worker import SellerWorker


class TestWorkerDiagnostics(unittest.TestCase):
    def test_watcher_import_failure_is_reported_instead_of_silent(self):
        messages = []
        worker = SellerWorker([])
        worker.log_emitted.connect(messages.append)
        original_import = builtins.__import__

        def fail_packaged_import(name, *args, **kwargs):
            if name == "trendyol_labels":
                raise ImportError("simulated missing bundled module")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fail_packaged_import):
            worker.run()

        self.assertTrue(
            any("Watcher stopped: ImportError" in message for message in messages),
            messages,
        )


if __name__ == "__main__":
    unittest.main()
