import os

import argparse
import getpass
import typing

from configparser import SectionProxy
from typeguard import typechecked

class Environ:
    @typechecked
    def __init__(self, args: argparse.Namespace, box_name: str):
        # prepare for the additional environment variables and NOW substitution
        os.environ["DISTRIBUTION_NAME"] = args.distribution
        os.environ["CONTAINER_NAME"] = box_name
        self._home_dir = os.environ['HOME']
        # local user home might be in a different location than /home but target user in the
        # container will always be in /home as ensured by zbox/entrypoint.py script
        self._target_home = "/home/" + getpass.getuser()
        os.environ["TARGET_HOME"] = self._target_home
        self._xdg_rtdir = os.environ.get("XDG_RUNTIME_DIR")
        self._box_name = box_name
        self._box_image = f"zbox-local/{args.distribution}/{box_name}"
        self._configuration_dirs = [f"{self._home_dir}/.config/zbox", "/etc/zbox"]
        # user data directory is $HOME/.local/share/zbox
        data_subdir = ".local/share/zbox"
        self._container_dir =  f"{self._home_dir}/{data_subdir}/{box_name}"
        os.environ["CONTAINER_DIR"] = self._container_dir
        self._configs_dir = f"{self._container_dir}/configs"
        self._target_configs_dir = f"{self._target_home}/{data_subdir}/{box_name}/configs"
        self._scripts_dir = f"{self._container_dir}/zbox-scripts"
        self._status_file = f"{self._container_dir}/status"

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
    def xdg_rtdir(self) -> str:
        return self._xdg_rtdir

    # name of the container
    @property
    @typechecked
    def box_name(self) -> str:
        return self._box_name

    # container image created with basic required user configuration from base image
    @property
    @typechecked
    def box_image(self) -> str:
        return self._box_image

    # local and global directories having configuration files for the containers
    @property
    @typechecked
    def configuration_dirs(self) -> list[str]:
        return self._configuration_dirs

    # base user directory where runtime data related to the container is stored
    @property
    @typechecked
    def container_dir(self) -> str:
        return self._container_dir

    # user directory where configuration files specified in [configs] are copied for sharing
    @property
    @typechecked
    def configs_dir(self) -> str:
        return self._configs_dir

    # target container directory where shared [configs] are mounted in the container
    @property
    @typechecked
    def target_configs_dir(self) -> str:
        return self._target_configs_dir

    # entrypoint script name for the base container
    @property
    @typechecked
    def entrypoint_base(self) -> str:
        return "entrypoint-base.sh"

    # entrypoint script name for the final container
    @property
    @typechecked
    def entrypoint(self) -> str:
        return "entrypoint.sh"

    # local directory where scripts to be shared with container are copied
    @property
    @typechecked
    def scripts_dir(self) -> str:
        return self._scripts_dir

    # target container directory where shared scripts are mounted
    @property
    @typechecked
    def scripts_target_dir(self) -> str:
        return "/usr/local/zbox"

    # local status file to communicate when the container is ready for use
    @property
    @typechecked
    def status_file(self) -> str:
        return self._status_file

    # target location where status_file is mounted in container
    @property
    @typechecked
    def status_target_file(self) -> str:
        return "/usr/local/zbox-status"

    # distribution specific scripts expected to be available for all supported distributions
    @property
    @typechecked
    def distribution_scripts(self) -> list[str]:
        return ["init-base.sh", "init.sh", "init-user.sh"]


@typechecked
def add_env_option(args: list[str], envvar: str, envval: typing.Optional[str] = None) -> None:
    if envval is None:
        args.append(f"-e={envvar}")
    else:
        args.append(f"-e={envvar}={envval}")

@typechecked
def process_env_section(env_section: SectionProxy, args: list[str]) -> None:
    for key in env_section:
        add_env_option(args, key, env_section[key])
