"""
Useful user environment settings.
"""

import getpass
import os
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
        data_subdir = ".local/share/zbox"
        self.__data_dir = f"{self.__home_dir}/{data_subdir}"
        self.__target_data_dir = f"{self.__target_home}/{data_subdir}"
        self.__xdg_rt_dir = os.environ.get("XDG_RUNTIME_DIR")
        self.__now = datetime.now()
        os.environ["NOW"] = str(self.__now)

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
