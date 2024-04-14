import fcntl

from typeguard import typechecked


# A simple file locker class that takes an fcntl() lock on given file. The file is created
# on first access and never removed thereafter to avoid any complications.
class FileLock:

    @typechecked
    def __init__(self, lock_file: str):
        self._lock_file = lock_file

    def __enter__(self):
        self._lock_fd = open(self._lock_file, "w+")
        fcntl.lockf(self._lock_fd, fcntl.LOCK_EX)

    def __exit__(self, ex_type, ex_value, ex_traceback):
        fcntl.lockf(self._lock_fd, fcntl.LOCK_UN)
        self._lock_fd.close()
