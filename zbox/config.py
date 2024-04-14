import os
import sys

import argparse
from typeguard import typechecked

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(script_dir))

from zbox.env import Environ

class Configuration:
    @typechecked
    def __init__(self, args: argparse.Namespace, env: Environ, box_name: str):
        # setup the additional environment variables
        os.environ["DISTRIBUTION_NAME"] = args.distribution
        os.environ["CONTAINER_NAME"] = box_name
        self._box_name = box_name
        self._box_image = f"zbox-local/{args.distribution}/{box_name}"
        self._configuration_dirs = [f"{env.home}/.config/zbox", "/etc/zbox"]
        # user data directory is $HOME/.local/share/zbox
        data_subdir = ".local/share/zbox"
        self._container_dir =  f"{env.home}/{data_subdir}/{box_name}"
        os.environ["CONTAINER_DIR"] = self._container_dir
        self._configs_dir = f"{self._container_dir}/configs"
        self._target_configs_dir = f"{env.target_home}/{data_subdir}/{box_name}/configs"
        self._scripts_dir = f"{self._container_dir}/zbox-scripts"
        self._status_file = f"{self._container_dir}/status"

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
    def target_scripts_dir(self) -> str:
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
