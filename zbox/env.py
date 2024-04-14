import getpass
import os
import typing
from configparser import SectionProxy

from typeguard import typechecked


class Environ:
    def __init__(self):
        self._home_dir = os.environ['HOME']
        # local user home might be in a different location than /home but target user in the
        # container will always be in /home as ensured by zbox/entrypoint.py script
        self._target_home = "/home/" + getpass.getuser()
        os.environ["TARGET_HOME"] = self._target_home
        self._xdg_rt_dir = os.environ.get("XDG_RUNTIME_DIR")

    # home directory of the current user
    @property
    @typechecked
    def home(self) -> str:
        return self._home_dir

    # home directory of the container user (which is always $TARGET_HOME=/home/$USER and
    #   hence can be different from $HOME)
    @property
    @typechecked
    def target_home(self) -> str:
        return self._target_home

    # $XDG_RUNTIME_DIR in the current session
    @property
    @typechecked
    def xdg_rt_dir(self) -> str:
        return self._xdg_rt_dir


@typechecked
def add_env_option(args: list[str], env_var: str, env_val: typing.Optional[str] = None) -> None:
    if env_val is None:
        args.append(f"-e={env_var}")
    else:
        args.append(f"-e={env_var}={env_val}")


@typechecked
def process_env_section(env_section: SectionProxy, args: list[str]) -> None:
    for key in env_section:
        add_env_option(args, key, env_section[key])
