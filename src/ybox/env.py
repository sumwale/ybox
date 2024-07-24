"""
Useful user environment settings.
"""

import getpass
import os
import site
from datetime import datetime
from importlib.abc import Traversable
from importlib.resources import files
from pathlib import Path
from typing import Union

from ybox.print import print_error

PathName = Union[Path, Traversable]


class Environ:
    """
    Holds common environment variables useful for the scripts like $HOME, $XDG_RUNTIME_DIR.
    It sets up the $TARGET_HOME environment variable which is the $HOME inside the container.
    Also captures the current time and sets up the $NOW environment variable.
    """

    def __init__(self):
        self._home_dir = os.path.expanduser("~")
        # local user home might be in a different location than /home but target user in the
        # container will always be in /home as ensured by ybox/entrypoint.py script
        self._target_home = f"/home/{getpass.getuser()}"
        os.environ["TARGET_HOME"] = self._target_home
        user_base = site.getuserbase()
        target_user_base = f"{self._target_home}/.local"
        self._data_dir = f"{user_base}/share/ybox"
        self._target_data_dir = f"{target_user_base}/share/ybox"
        self._xdg_rt_dir = os.environ.get("XDG_RUNTIME_DIR", "")
        self._now = datetime.now()
        os.environ["NOW"] = str(self._now)
        pkg_dir = files("ybox")
        os.environ["YBOX_PKG_DIR"] = str(pkg_dir)
        # for tests, only the bundled configurations should be tested
        self._configuration_dirs: list[PathName] = []
        if os.environ.get("YBOX_TESTING"):
            self._configuration_dirs = [pkg_dir.joinpath("conf")]
        else:
            self._configuration_dirs = [Path(f"{self._home_dir}/.config/ybox"),
                                        pkg_dir.joinpath("conf")]
        self._user_applications_dir = f"{user_base}/share/applications"
        self._user_executables_dir = f"{user_base}/bin"
        self._user_man_dir = f"{user_base}/share/man"

    def search_config_path(self, conf_path: str, quiet: bool = False) -> PathName:
        """
        Search for given configuration path in user and system configuration directories
        (in that order). The path may refer to a file or a subdirectory.

        :param conf_path: the configuration file to search (expected to be a relative path)
        :param quiet: if False then prints an error message on standard output on failure
        :return: the path of the configuration file as `Path` or resource file from
                 importlib (`Traversable`)
        """
        if os.path.isabs(conf_path):
            return Path(conf_path)
        # order is first search in user's config directory, and then the system config directory
        for config_dir in self._configuration_dirs:
            path = config_dir.joinpath(conf_path)
            if os.access(path, os.R_OK):  # type: ignore
                return path
        search_dirs = ', '.join([str(file) for file in self._configuration_dirs])
        if not quiet:
            print_error(f"Configuration file '{conf_path}' not found in [{search_dirs}]")
        raise FileNotFoundError

    @property
    def home(self) -> str:
        """home directory of the current user"""
        return self._home_dir

    # home directory of the container user (which is always $TARGET_HOME=/home/$USER and
    #   hence can be different from $HOME)
    @property
    def target_home(self) -> str:
        """home directory of the container user (which is always $TARGET_HOME=/home/$USER and
           hence can be different from $HOME)"""
        return self._target_home

    @property
    def data_dir(self) -> str:
        """base user directory where runtime data related to all the containers is
           stored in subdirectories"""
        return self._data_dir

    @property
    def target_data_dir(self) -> str:
        """base user directory of the container user where runtime data related to all
           the containers is stored"""
        return self._target_data_dir

    @property
    def xdg_rt_dir(self) -> str:
        """value of $XDG_RUNTIME_DIR in the current session"""
        return self._xdg_rt_dir

    @property
    def now(self) -> datetime:
        """current time as captured during Environ object creation"""
        return self._now

    @property
    def user_applications_dir(self) -> str:
        """User's local applications directory that holds the .desktop files"""
        return self._user_applications_dir

    @property
    def user_executables_dir(self) -> str:
        """User's local executables directory which should be in the $PATH"""
        return self._user_executables_dir

    @property
    def user_man_dir(self) -> str:
        """User's local man pages directory which should be in the path returned by `manpath`"""
        return self._user_man_dir


def resolve_inc_path(inc: str, src: PathName) -> PathName:
    """resolve `include` path specified relative to a given source, or as an absolute string"""
    return Path(inc) if os.path.isabs(inc) else src.parent.joinpath(inc)  # type: ignore
