"""Unit tests for `ybox/filelock.py`"""

import errno
import fcntl
import multiprocessing
import os
import time
from datetime import datetime
from multiprocessing import Process
from multiprocessing.synchronize import Event
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from ybox.filelock import FileLock

# keep unique so that parallel runs in tox/nox will work
_LOCK_FILE = f"test_locking-{uuid4()}.lck"


def _run_in_process(func, args=(), expected_exitcode: int = 0,  # type: ignore
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
        assert proc.exitcode == expected_exitcode
    return proc


def test_lock():
    """test basic file locking behavior"""
    with FileLock(_LOCK_FILE):
        # lock file should exist
        assert os.path.exists(_LOCK_FILE)

        # trying to lock again in another process should throw an exception
        def do_lock() -> None:
            with pytest.raises(OSError) as cm:
                with open(_LOCK_FILE, "w", encoding="utf-8") as lock_fd:
                    fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            assert cm.value.errno in (errno.EACCES, errno.EAGAIN)

        _run_in_process(do_lock)
    # trying to lock an un-writable file should raise an error
    with pytest.raises(PermissionError):
        with FileLock(f"/usr/{_LOCK_FILE}"):
            pass
    # mock the case of an OSError with errno other than EACCES or EAGAIN
    with patch("ybox.filelock.fcntl.lockf", side_effect=OSError(errno.ENOLCK, "too many locks")):
        with pytest.raises(OSError) as cm:
            with FileLock(_LOCK_FILE):
                assert cm.value.errno == errno.ENOLCK


def test_unlock():
    """test basic file unlocking behavior"""
    with FileLock(_LOCK_FILE):
        assert os.path.exists(_LOCK_FILE)

    # explicit locking and unlocking should succeed after release
    def do_lock() -> None:
        with open(_LOCK_FILE, "w", encoding="utf-8") as lock_fd:
            fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.lockf(lock_fd, fcntl.LOCK_UN)

    _run_in_process(do_lock)


def test_timeout():
    """test timeout on a locked file"""
    def do_lock(e: Event) -> None:
        with FileLock(_LOCK_FILE):
            e.set()
            time.sleep(6.0)

    # acquire the lock in a separate process, then check lock timeout in the main process
    ev = multiprocessing.Event()
    proc = _run_in_process(do_lock, args=(ev,), wait_for_process=False)
    ev.wait()
    start = datetime.now()
    with pytest.raises(TimeoutError):
        with FileLock(_LOCK_FILE, timeout_secs=3.0):
            pass
    elapsed = (datetime.now() - start).total_seconds()
    assert 3.0 <= elapsed < 5.0
    proc.join()
    assert proc.exitcode == 0


def test_poll():
    """test timeout with poll interval on a locked file"""
    with FileLock(_LOCK_FILE):
        assert os.path.exists(_LOCK_FILE)

        def do_lock() -> None:
            start1 = datetime.now()
            with pytest.raises(TimeoutError):
                with FileLock(_LOCK_FILE, timeout_secs=2.0, poll_interval=0.5):
                    pass
            start2 = datetime.now()
            with pytest.raises(TimeoutError):
                with FileLock(_LOCK_FILE, timeout_secs=2.0, poll_interval=2.0):
                    pass
            elapsed1 = (start2 - start1).total_seconds()
            assert 2.0 <= elapsed1 < 3.0
            elapsed2 = (datetime.now() - start2).total_seconds()
            assert 2.0 <= elapsed2 < 6.0

        _run_in_process(do_lock)


@pytest.fixture(autouse=True)
def cleanup():
    """clean up the lock file"""
    yield
    Path(_LOCK_FILE).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
