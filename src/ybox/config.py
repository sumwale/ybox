"""
Configuration locations, distribution and box name of ybox container.
"""

import os
import shutil
import subprocess

from .consts import Consts
from .env import Environ


class StaticConfiguration:
    """
    Configuration paths for a ybox container, its name and distribution.
    This class also setups up related environment variables which can be used by the
    INI configuration files.
    """

    def __init__(self, env: Environ, distribution: str, box_name: str):
        self._env = env
        # set up the additional environment variables
        os.environ["YBOX_DISTRIBUTION_NAME"] = distribution
        os.environ["YBOX_CONTAINER_NAME"] = box_name
        self._distribution = distribution
        self._box_name = box_name
        self._box_image = f"{Consts.image_prefix()}/{distribution}/{box_name}"
        self._shared_box_image = f"{Consts.shared_image_prefix()}/{distribution}"
        # timezone properties
        self._localtime = None
        self._timezone = None
        if os.path.islink("/etc/localtime"):
            self._localtime = os.readlink("/etc/localtime")
        if os.path.exists("/etc/timezone"):
            with open("/etc/timezone", "r", encoding="utf-8") as timezone:
                self._timezone = timezone.read().rstrip("\n")
        elif (tdctl := shutil.which("timedatectl", path=os.pathsep.join(Consts.sys_bin_dirs()))):
            self._timezone = subprocess.check_output([tdctl, "show", "--property=Timezone",
                                                      "--value"]).decode("utf-8").rstrip("\n")
        self._pager = os.environ.get("YBOX_PAGER", Consts.default_pager())
        container_dir = f"{env.data_dir}/{box_name}"
        os.environ["YBOX_CONTAINER_DIR"] = container_dir
        self._configs_dir = f"{container_dir}/configs"
        self._target_configs_dir = f"{env.target_data_dir}/{box_name}/configs"
        self._scripts_dir = f"{container_dir}/ybox-scripts"
        self._target_scripts_dir = "/usr/local/ybox"
        os.environ["YBOX_TARGET_SCRIPTS_DIR"] = self._target_scripts_dir
        self._status_file = f"{container_dir}/status"
        self._config_list = f"{self._scripts_dir}/config.list"
        self._app_list = f"{self._scripts_dir}/app.list"
        self._startup_list = f"{self._scripts_dir}/startup.list"
        self._container_config_dir = env.container_config_dir(box_name)

    @property
    def env(self) -> Environ:
        """the `Environ` object used for this configuration"""
        return self._env

    @property
    def distribution(self) -> str:
        """linux distribution being used by the ybox container"""
        return self._distribution

    @staticmethod
    def distribution_config(distribution: str, config_file: str = "distro.ini") -> str:
        """
        Relative configuration file path for the Linux distribution being used.

        :param distribution: name of the Linux distribution
        :param config_file: name of the configuration file, defaults to "distro.ini"
        :return: relative path of the configuration file
        """
        return f"distros/{distribution}/{config_file}"

    @property
    def box_name(self) -> str:
        """name of the ybox container"""
        return self._box_name

    def box_image(self, has_shared_root: bool) -> str:
        """
        Container image created with basic required user configuration from base image.
        This can either be container specific, or if `base.shared_root` is provided, then
        it will be common for all such images for the same distribution.

        :param has_shared_root: whether `base.shared_root` is provided in configuration file
        :return: the podman/docker image to be created and used for the ybox
        """
        return self._shared_box_image if has_shared_root else self._box_image

    def unshared_root(self) -> str:
        """
        path of the directory on the host used for storing root subdirs of the container for the
        case when `shared_root` is not set (i.e. a unique directory is used for the container).
        """
        return f"{self._env.data_dir}/{self._box_name}/ROOT"

    @property
    def localtime(self) -> str | None:
        """the target link for /etc/localtime"""
        return self._localtime

    @property
    def timezone(self) -> str | None:
        """the contents of /etc/timezone or output of timedatectl"""
        return self._timezone

    @property
    def pager(self) -> str:
        """pager command to show output one screenful at a time on the terminal"""
        return self._pager

    @property
    def configs_dir(self) -> str:
        """user directory where configuration files specified in [configs] are copied or
           hard-linked for sharing with the container"""
        return self._configs_dir

    @property
    def target_configs_dir(self) -> str:
        """target container directory where shared [configs] are mounted in the container"""
        return self._target_configs_dir

    @property
    def scripts_dir(self) -> str:
        """local directory where scripts to be shared with container are copied"""
        return self._scripts_dir

    @property
    def target_scripts_dir(self) -> str:
        """target container directory where shared scripts are mounted"""
        return self._target_scripts_dir

    @property
    def status_file(self) -> str:
        """local status file to communicate when the container is ready for use"""
        return self._status_file

    @property
    def config_list(self) -> str:
        """file containing list of configuration files to be linked on that container to host
            as mentioned in the [configs] section"""
        return self._config_list

    @property
    def app_list(self) -> str:
        """file containing list of applications to be installed in the container"""
        return self._app_list

    @property
    def startup_list(self) -> str:
        """file containing list of commands to be executed in the container on startup"""
        return self._startup_list

    @property
    def container_config_dir(self) -> str:
        """directory where container specific configuration files are stored"""
        return self._container_config_dir
