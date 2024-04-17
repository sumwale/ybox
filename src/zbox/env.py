import getpass
import os
from configparser import SectionProxy
from datetime import datetime
from typing import Optional


class Environ:

    def __init__(self):
        self.__home_dir = os.environ['HOME']
        # local user home might be in a different location than /home but target user in the
        # container will always be in /home as ensured by zbox/entrypoint.py script
        self.__target_home = "/home/" + getpass.getuser()
        os.environ["TARGET_HOME"] = self.__target_home
        data_subdir = ".local/share/zbox"
        self.__data_dir = f"{self.__home_dir}/{data_subdir}"
        self.__target_data_dir = f"{self.__home_dir}/{data_subdir}"
        self.__xdg_rt_dir = os.environ.get("XDG_RUNTIME_DIR")
        self.__now = datetime.now()
        os.environ["NOW"] = str(self.__now)

    # home directory of the current user
    @property
    def home(self) -> str:
        return self.__home_dir

    # home directory of the container user (which is always $TARGET_HOME=/home/$USER and
    #   hence can be different from $HOME)
    @property
    def target_home(self) -> str:
        return self.__target_home

    @property
    def data_dir(self) -> str:
        """
        :return: base user directory where runtime data related to all the containers is
                 stored in subdirectories
        """
        return self.__data_dir

    @property
    def target_data_dir(self) -> str:
        """
        :return: base user directory of the container user where runtime data related to all
                the containers is stored
        """
        return self.__data_dir

    # $XDG_RUNTIME_DIR in the current session
    @property
    def xdg_rt_dir(self) -> str:
        return self.__xdg_rt_dir

    @property
    def now(self) -> datetime:
        return self.__now


class ZboxLabel:
    """
    Labels for zbox created objects.
    """
    CONTAINER_TYPE = "io.zbox.container.type"
    CONTAINER_BASE = f"{CONTAINER_TYPE}=base"
    CONTAINER_COPY = f"{CONTAINER_TYPE}=copy"
    CONTAINER_PRIMARY = f"{CONTAINER_TYPE}=primary"


def add_env_option(args: list[str], env_var: str, env_val: Optional[str] = None) -> None:
    if env_val is None:
        args.append(f"-e={env_var}")
    else:
        args.append(f"-e={env_var}={env_val}")


def process_env_section(env_section: SectionProxy, args: list[str]) -> None:
    for key in env_section:
        add_env_option(args, key, env_section[key])
