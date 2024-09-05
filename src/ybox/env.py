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

from .print import print_error, print_notice

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
        self._user_base = user_base = site.getuserbase()
        target_user_base = f"{self._target_home}/.local"
        self._data_dir = f"{user_base}/share/ybox"
        self._target_data_dir = f"{target_user_base}/share/ybox"
        self._xdg_rt_dir = os.environ.get("XDG_RUNTIME_DIR", "")
        self._now = datetime.now()
        os.environ["NOW"] = str(self._now)
        sys_conf_dir = files("ybox").joinpath("conf")
        os.environ["YBOX_SYS_CONF_DIR"] = str(sys_conf_dir)
        self._sys_conf_dirs = [sys_conf_dir]
        self._root_dir = [Path("/")]
        self._configuration_dirs: list[PathName] = []
        # for tests, only the bundled configurations should be tested
        if os.environ.get("YBOX_TESTING"):
            print_notice("Running with YBOX_TESTING enabled")
            self._configuration_dirs = self._sys_conf_dirs
        else:
            self._configuration_dirs = [Path(f"{self._home_dir}/.config/ybox"),
                                        sys_conf_dir]
        self._user_applications_dir = f"{user_base}/share/applications"
        self._user_executables_dir = f"{user_base}/bin"

    def search_config_path(self, conf_path: str, only_sys_conf: bool = False,
                           quiet: bool = False) -> PathName:
        """
        Search for given configuration path in user and system configuration directories
        (in that order). The path may refer to a file or a subdirectory.

        :param conf_path: the configuration file to search (expected to be a relative path)
        :param only_sys_conf: if True then search only system configuration directory else
                              search for user configuration directory first then the system one
        :param quiet: if False then prints an error message on standard output on failure
        :return: the path of the configuration file as `Path` or resource file from
                 importlib (i.e. `Traversable`)
        """
        if os.path.isabs(conf_path):
            conf_dirs = self._root_dir
        else:
            conf_dirs = self._sys_conf_dirs if only_sys_conf else self._configuration_dirs
        for config_dir in conf_dirs:
            path = config_dir.joinpath(conf_path)
            if os.access(path, os.R_OK):  # type: ignore
                return path
        search_dirs = ', '.join([str(file) for file in conf_dirs])
        if not quiet:
            print_error(f"Configuration file '{conf_path}' not found in [{search_dirs}]")
        raise FileNotFoundError(f"Missing configuration file '{conf_path}'")

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
    def user_base(self) -> str:
        """User's local base data directory which is typically ~/.local"""
        return self._user_base

    @property
    def user_applications_dir(self) -> str:
        """User's local applications directory that holds the .desktop files"""
        return self._user_applications_dir

    @property
    def user_executables_dir(self) -> str:
        """User's local executables directory which should be in the $PATH"""
        return self._user_executables_dir
