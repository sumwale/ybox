import argparse
import os
import sys
from typing import Optional

from typeguard import typechecked

from zbox.env import Environ

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(script_dir))


class Configuration:
    @typechecked
    def __init__(self, args: argparse.Namespace, env: Environ, box_name: str):
        # set up the additional environment variables
        distro = args.distribution
        os.environ["DISTRIBUTION_NAME"] = distro
        os.environ["CONTAINER_NAME"] = box_name
        self.__box_name = box_name
        self.__box_image = f"zbox-local/{distro}/{box_name}"
        self.__shared_box_image = f"zbox-shared-local/{distro}"
        self.__configuration_dirs = [f"{env.home}/.config/zbox", "/etc/zbox"]
        # timezone properties
        self.__localtime = None
        self.__timezone = None
        if os.path.islink("/etc/localtime"):
            self.__localtime = os.readlink("/etc/localtime")
        if os.path.exists("/etc/timezone"):
            with open("/etc/timezone") as tz:
                self.__timezone = tz.read().rstrip("\n")
        # user data directory is $HOME/.local/share/zbox
        self.__data_dir = ".local/share/zbox"
        self.__shared_root_host_dir = f"{env.home}/{self.__data_dir}/ROOTS/{distro}"
        self.__container_dir = f"{env.home}/{self.__data_dir}/{box_name}"
        os.environ["CONTAINER_DIR"] = self.__container_dir
        self.__configs_dir = f"{self.__container_dir}/configs"
        self.__target_configs_dir = f"{env.target_home}/{self.__data_dir}/{box_name}/configs"
        self.__scripts_dir = f"{self.__container_dir}/zbox-scripts"
        self.__status_file = f"{self.__container_dir}/status"
        self.__config_list = f"{self.__scripts_dir}/config.list"
        self.__app_list = f"{self.__scripts_dir}/app.list"

    @typechecked
    def get_config_file(self, conf_file: str) -> str:
        # order is first search in user's config directory, and then the system config directory
        for config_dir in self.__configuration_dirs:
            path = f"{config_dir}/{conf_file}"
            if os.access(path, os.R_OK):
                return path
        search_dirs = ', '.join(self.__configuration_dirs)
        sys.exit(f"Configuration file '{conf_file}' not found in [{search_dirs}]")

    # name of the container
    @property
    @typechecked
    def box_name(self) -> str:
        return self.__box_name

    # Container image created with basic required user configuration from base image.
    # This can either be container specific, or if 'base.shared_root' is true, then
    # it will be common for all such images for the same distribution.
    @typechecked
    def box_image(self, shared_root: bool) -> str:
        return self.__shared_box_image if shared_root else self.__box_image

    # local and global directories having configuration files for the containers
    @property
    @typechecked
    def configuration_dirs(self) -> list[str]:
        return self.__configuration_dirs

    # the target link for /etc/localtime
    @property
    @typechecked
    def localtime(self) -> Optional[str]:
        return self.__localtime

    # the contents of /etc/timezone
    @property
    @typechecked
    def timezone(self) -> str:
        return self.__timezone

    # host directory that is bind mounted as the shared root directory on containers
    @property
    @typechecked
    def shared_root_host_dir(self) -> Optional[str]:
        return self.__shared_root_host_dir

    # directory where shared root directory is mounted in a container during setup
    @property
    @typechecked
    def shared_root_mount_dir(self) -> str:
        return "/zbox-root"

    # base user directory where runtime data related to the container is stored
    @property
    @typechecked
    def container_dir(self) -> str:
        return self.__container_dir

    # user directory where configuration files specified in [configs] are copied for sharing
    @property
    @typechecked
    def configs_dir(self) -> str:
        return self.__configs_dir

    # target container directory where shared [configs] are mounted in the container
    @property
    @typechecked
    def target_configs_dir(self) -> str:
        return self.__target_configs_dir

    # entrypoint script name for the base container
    @property
    @typechecked
    def entrypoint_base(self) -> str:
        return "entrypoint-base.sh"

    # entrypoint script name for the "copy" container that copies files to shared root
    @property
    @typechecked
    def entrypoint_cp(self) -> str:
        return "entrypoint-cp.sh"

    # entrypoint script name for the final container
    @property
    @typechecked
    def entrypoint(self) -> str:
        return "entrypoint.sh"

    # local directory where scripts to be shared with container are copied
    @property
    @typechecked
    def scripts_dir(self) -> str:
        return self.__scripts_dir

    # target container directory where shared scripts are mounted
    @property
    @typechecked
    def target_scripts_dir(self) -> str:
        return "/usr/local/zbox"

    # local status file to communicate when the container is ready for use
    @property
    @typechecked
    def status_file(self) -> str:
        return self.__status_file

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

    # file containing list of configuration files to be linked on that container to host
    # as mentioned in the [configs] section
    @property
    @typechecked
    def config_list(self) -> str:
        return self.__config_list

    # file containing list of applications to be installed in the container
    @property
    @typechecked
    def app_list(self) -> str:
        return self.__app_list
