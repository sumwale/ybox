"""Tests for `ybox/filelock.py`"""

import errno
import fcntl
import multiprocessing
import multiprocessing.context
import os
import time
import unittest
from datetime import datetime
from multiprocessing import Process
from multiprocessing.synchronize import Event
from pathlib import Path
from uuid import uuid4

from ybox.filelock import FileLock


class TestFileLock(unittest.TestCase):
    """unit tests for the `ybox.filelock` module"""

    # keep unique so that parallel runs in tox/nox will work
    _lock_file = f"test_locking-{uuid4()}.lck"

    def _run_in_process(self, func, args=(), expected_exitcode: int = 0,  # type: ignore
                        wait_for_process: bool = True) -> Process:
        """
        Run a given function with arguments in a separate process.

        :param func: the function to be run
        :param args: arguments to the function as an `Iterable` (default is empty tuple)
        :param expected_exitcode: the expected exit code of the process (default is 0)
        """
        proc = Process(target=func, args=args)  # type: ignore
        proc.start()
        if wait_for_process:
            proc.join()
            self.assertEqual(expected_exitcode, proc.exitcode)
        return proc

    def test_lock(self):
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
        # trying to lock an unwritable file should raise an error
        with self.assertRaises(PermissionError):
            with FileLock(f"/usr/{self._lock_file}"):
                pass

    def test_unlock(self):
        """test basic file unlocking behavior"""
        with FileLock(self._lock_file):
            self.assertTrue(os.path.exists(self._lock_file))

        # explicit locking and unlocking should succeed after release
        def do_lock() -> None:
            with open(self._lock_file, "w", encoding="utf-8") as lock_fd:
                fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.lockf(lock_fd, fcntl.LOCK_UN)

        self._run_in_process(do_lock)

    def test_timeout(self):
        """test timeout on a locked file"""
        def do_lock(ev: Event) -> None:
            with FileLock(self._lock_file):
                ev.set()
                time.sleep(6.0)

        # acquire the lock in a separate process, then check lock timeout in the main process
        ev = multiprocessing.Event()
        proc = self._run_in_process(do_lock, args=(ev,), wait_for_process=False)
        ev.wait()
        start = datetime.now()
        with self.assertRaises(TimeoutError):
            with FileLock(self._lock_file, timeout_secs=3.0):
                pass
        elapsed = (datetime.now() - start).total_seconds()
        self.assertGreaterEqual(elapsed, 3.0)
        self.assertLess(elapsed, 5.0)
        proc.join()
        self.assertEqual(0, proc.exitcode)

    def test_poll(self):
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

    def tearDown(self):
        """tearDown will clean up the lock file"""
        Path(self._lock_file).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
