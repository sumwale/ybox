import errno
import fcntl
import os
import unittest
from datetime import datetime
from multiprocessing import Process
from pathlib import Path

from src.ybox.filelock import FileLock


class MyTestCase(unittest.TestCase):
    _lock_file = "test_locking.lck"

    def _run_in_process(self, func, args=(), expected_exitcode: int = 0) -> None:
        proc = Process(target=func, args=args)
        proc.start()
        proc.join()
        self.assertEqual(expected_exitcode, proc.exitcode)

    def test_lock(self) -> None:
        """test basic file locking behavior"""
        with FileLock(self._lock_file):
            # lock file should exist
            self.assertTrue(os.path.exists(self._lock_file))

            # trying to lock again in another process should throw an exception
            def do_lock() -> None:
                with self.assertRaises(OSError) as cm:
                    with open(self._lock_file, "w", encoding="utf-8") as lock_fd:
                        fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertIn(cm.exception.errno, (errno.EACCES, errno.EAGAIN))

            self._run_in_process(do_lock)

    def test_unlock(self) -> None:
        """test basic file unlocking behavior"""
        with FileLock(self._lock_file):
            self.assertTrue(os.path.exists(self._lock_file))

        # explicit locking and unlocking should succeed after release
        def do_lock() -> None:
            with open(self._lock_file, "w", encoding="utf-8") as lock_fd:
                fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.lockf(lock_fd, fcntl.LOCK_UN)

        self._run_in_process(do_lock)

    def test_timeout(self) -> None:
        """test timeout on a locked file"""
        with FileLock(self._lock_file):
            self.assertTrue(os.path.exists(self._lock_file))

            def do_lock() -> None:
                start = datetime.now()
                with self.assertRaises(TimeoutError):
                    with FileLock(self._lock_file, timeout_secs=3.0):
                        pass
                elapsed = (datetime.now() - start).total_seconds()
                self.assertGreaterEqual(elapsed, 3.0)
                self.assertLess(elapsed, 5.0)

            self._run_in_process(do_lock)

    def test_poll(self) -> None:
        """test timeout with poll interval on a locked file"""
        with FileLock(self._lock_file):
            self.assertTrue(os.path.exists(self._lock_file))

            def do_lock() -> None:
                start1 = datetime.now()
                with self.assertRaises(TimeoutError):
                    with FileLock(self._lock_file, timeout_secs=2.0, poll_interval=0.5):
                        pass
                start2 = datetime.now()
                with self.assertRaises(TimeoutError):
                    with FileLock(self._lock_file, timeout_secs=2.0, poll_interval=2.0):
                        pass
                elapsed1 = (start2 - start1).total_seconds()
                self.assertGreaterEqual(elapsed1, 2.0)
                self.assertLess(elapsed1, 3.0)
                elapsed2 = (datetime.now() - start2).total_seconds()
                self.assertGreaterEqual(elapsed2, 2.0)
                self.assertLess(elapsed2, 6.0)

            self._run_in_process(do_lock)

    def tearDown(self) -> None:
        Path(self._lock_file).unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
