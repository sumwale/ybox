"""
Useful user environment settings.
"""

import getpass
import os
import site
from datetime import datetime


class Environ:
    """
    Holds common environment variables useful for the scripts like $HOME, $XDG_RUNTIME_DIR.
    It sets up the $TARGET_HOME environment variable which is the $HOME inside the container.
    Also captures the current time and sets up the $NOW environment variable.
    """

    def __init__(self):
        self.__home_dir = os.environ['HOME']
        # local user home might be in a different location than /home but target user in the
        # container will always be in /home as ensured by zbox/entrypoint.py script
        self.__target_home = "/home/" + getpass.getuser()
        os.environ["TARGET_HOME"] = self.__target_home
        user_base = site.getuserbase()
        target_user_base = self.__target_home + "/.local"
        self.__data_dir = f"{user_base}/share/zbox"
        self.__target_data_dir = f"{target_user_base}/share/zbox"
        self.__xdg_rt_dir = os.environ.get("XDG_RUNTIME_DIR", "")
        self.__now = datetime.now()
        os.environ["NOW"] = str(self.__now)
        self.__configuration_dirs = (f"{self.__home_dir}/.config/zbox", "/etc/zbox")
        self.__user_applications_dir = f"{user_base}/share/applications"
        self.__user_executables_dir = f"{user_base}/bin"

    def search_config_path(self, conf_file: str) -> str:
        """
        Search for given configuration path in user and system configuration directories
        (in that order). The path may refer to a file or a subdirectory.

        :param conf_file: the configuration file to search (expected to be a relative path)
        :return: the full path of the configuration file
        """
        # order is first search in user's config directory, and then the system config directory
        for config_dir in self.__configuration_dirs:
            path = f"{config_dir}/{conf_file}"
            if os.access(path, os.R_OK):
                return path
        search_dirs = ', '.join(self.__configuration_dirs)
        raise FileNotFoundError(f"Configuration file '{conf_file}' not found in [{search_dirs}]")

    @property
    def home(self) -> str:
        """home directory of the current user"""
        return self.__home_dir

    # home directory of the container user (which is always $TARGET_HOME=/home/$USER and
    #   hence can be different from $HOME)
    @property
    def target_home(self) -> str:
        """home directory of the container user (which is always $TARGET_HOME=/home/$USER and
           hence can be different from $HOME)"""
        return self.__target_home

    @property
    def data_dir(self) -> str:
        """base user directory where runtime data related to all the containers is
           stored in subdirectories"""
        return self.__data_dir

    @property
    def target_data_dir(self) -> str:
        """base user directory of the container user where runtime data related to all
           the containers is stored"""
        return self.__target_data_dir

    @property
    def xdg_rt_dir(self) -> str:
        """value of $XDG_RUNTIME_DIR in the current session"""
        return self.__xdg_rt_dir

    @property
    def now(self) -> datetime:
        """current time as captured during Environ object creation"""
        return self.__now

    @property
    def user_applications_dir(self) -> str:
        """User's local applications directory that holds the .desktop files"""
        return self.__user_applications_dir

    @property
    def user_executables_dir(self) -> str:
        """User's local executables directory which should be in the $PATH"""
        return self.__user_executables_dir
