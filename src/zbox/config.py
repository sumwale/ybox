"""
Configuration locations, distribution and box name of zbox container.
"""

import os
from typing import Optional

from .env import Environ


class ZboxConfiguration:
    """
    Configuration paths for a zbox container, its name and distribution.
    This class also setups up related environment variables which can be used by
    INI configuration files.
    """

    def __init__(self, env: Environ, distribution: str, box_name: str):
        # set up the additional environment variables
        os.environ["ZBOX_DISTRIBUTION_NAME"] = distribution
        os.environ["ZBOX_CONTAINER_NAME"] = box_name
        self.__distribution = distribution
        self.__box_name = box_name
        self.__box_image = f"zbox-local/{distribution}/{box_name}"
        self.__shared_box_image = f"zbox-shared-local/{distribution}"
        self.__configuration_dirs = (f"{env.home}/.config/zbox", "/etc/zbox")
        # timezone properties
        self.__localtime = None
        self.__timezone = None
        if os.path.islink("/etc/localtime"):
            self.__localtime = os.readlink("/etc/localtime")
        if os.path.exists("/etc/timezone"):
            with open("/etc/timezone", encoding="utf-8") as timezone:
                self.__timezone = timezone.read().rstrip("\n")
        self.__shared_root_host_dir = f"{env.data_dir}/ROOTS/{distribution}"
        self.__container_conf = self._ContainerConfig(env, box_name)

    def search_config_file(self, conf_file: str) -> str:
        """
        Search for given configuration file in user and system configuration directories
        (in that order).

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
    def distribution(self) -> str:
        """linux distribution being used by the zbox container"""
        return self.__distribution

    @property
    def box_name(self) -> str:
        """name of the zbox container"""
        return self.__box_name

    def box_image(self, shared_root: bool) -> str:
        """
        Container image created with basic required user configuration from base image.
        This can either be container specific, or if 'base.shared_root' is true, then
        it will be common for all such images for the same distribution.
        :param shared_root: whether 'base.shared_root' is true in configuration file
        :return: the docker/podman image to be created and used for the zbox
        """
        return self.__shared_box_image if shared_root else self.__box_image

    @property
    def localtime(self) -> Optional[str]:
        """the target link for /etc/localtime"""
        return self.__localtime

    @property
    def timezone(self) -> Optional[str]:
        """the contents of /etc/timezone"""
        return self.__timezone

    @property
    def shared_root_host_dir(self) -> str:
        """host directory that is bind mounted as the shared root directory on containers"""
        return self.__shared_root_host_dir

    @property
    def shared_root_mount_dir(self) -> str:
        """directory where shared root directory is mounted in a container during setup"""
        return "/zbox-root"

    @property
    def configs_dir(self) -> str:
        """user directory where configuration files specified in [configs] are copied or
           hard-linked for sharing with the container"""
        return self.__container_conf.configs_dir

    @property
    def target_configs_dir(self) -> str:
        """target container directory where shared [configs] are mounted in the container"""
        return self.__container_conf.target_configs_dir

    @property
    def entrypoint_base(self) -> str:
        """entrypoint script name for the base container (which is booted to configure
           the final container)"""
        return "entrypoint-base.sh"

    @property
    def entrypoint_cp(self) -> str:
        """entrypoint script name for the "copy" container that copies files to shared root"""
        return "entrypoint-cp.sh"

    @property
    def entrypoint(self) -> str:
        """entrypoint script name for the final zbox container"""
        return "entrypoint.sh"

    @property
    def scripts_dir(self) -> str:
        """local directory where scripts to be shared with container are copied"""
        return self.__container_conf.scripts_dir

    @property
    def target_scripts_dir(self) -> str:
        """target container directory where shared scripts are mounted"""
        return self.__container_conf.target_scripts_dir

    @property
    def status_file(self) -> str:
        """local status file to communicate when the container is ready for use"""
        return self.__container_conf.status_file

    @property
    def status_target_file(self) -> str:
        """target location where status_file is mounted in container"""
        return self.__container_conf.status_target_file

    @property
    def distribution_scripts(self) -> list[str]:
        """distribution specific scripts expected to be present for all supported distributions"""
        return self.__container_conf.distribution_scripts

    # file containing list of configuration files to be linked on that container to host
    # as mentioned in the [configs] section
    @property
    def config_list(self) -> str:
        """file containing list of configuration files to be linked on that container to host
            as mentioned in the [configs] section"""
        return self.__container_conf.config_list

    @property
    def app_list(self) -> str:
        """file containing list of applications to be installed in the container"""
        return self.__container_conf.app_list

    class _ContainerConfig:
        """Container specific paths are set up in this class"""

        def __init__(self, env: Environ, box_name: str):
            container_dir = f"{env.data_dir}/{box_name}"
            os.environ["ZBOX_CONTAINER_DIR"] = container_dir
            self.configs_dir = f"{container_dir}/configs"
            self.target_configs_dir = f"{env.target_data_dir}/{box_name}/configs"
            self.scripts_dir = f"{container_dir}/zbox-scripts"
            self.target_scripts_dir = "/usr/local/zbox"
            os.environ["ZBOX_TARGET_SCRIPTS_DIR"] = self.target_scripts_dir
            self.status_file = f"{container_dir}/status"
            self.config_list = f"{self.scripts_dir}/config.list"
            self.app_list = f"{self.scripts_dir}/app.list"

        @property
        def status_target_file(self) -> str:
            """target location where status_file is mounted in container"""
            return "/usr/local/zbox-status"

        @property
        def distribution_scripts(self) -> list[str]:
            """scripts expected to be present for all supported distributions"""
            return ["init-base.sh", "init.sh", "init-user.sh"]
