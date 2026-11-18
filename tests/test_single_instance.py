import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ui_main import _try_acquire_instance_lock


class TestSingleInstance(unittest.TestCase):
    def test_lock_rejects_a_second_instance_and_releases_for_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "data" / "luma.instance.lock"
            first_lock = _try_acquire_instance_lock(lock_path, timeout_ms=0)

            self.assertIsNotNone(first_lock)
            self.assertIsNone(
                _try_acquire_instance_lock(lock_path, timeout_ms=0)
            )
            duplicate_process = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import sys; from pathlib import Path; "
                        "from ui_main import _try_acquire_instance_lock; "
                        "print(_try_acquire_instance_lock(Path(sys.argv[1]), timeout_ms=0))"
                    ),
                    str(lock_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                check=True,
                text=True,
            )
            self.assertEqual(duplicate_process.stdout.strip(), "None")

            first_lock.unlock()
            restarted_lock = _try_acquire_instance_lock(lock_path, timeout_ms=0)
            self.assertIsNotNone(restarted_lock)
            restarted_lock.unlock()


if __name__ == "__main__":
    unittest.main()
