"""
Configuration locations, distribution and box name of ybox container.
"""

import os
import re
from typing import Iterable, Optional

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

    @property
    def localtime(self) -> Optional[str]:
        """the target link for /etc/localtime"""
        return self._localtime

    @property
    def timezone(self) -> Optional[str]:
        """the contents of /etc/timezone"""
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


class Consts:
    """
    Defines fixed file/path and other names used by ybox that are not configurable.
    """

    # standard system executable paths
    _SYS_BIN_DIRS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin", "/usr/local/sbin")
    # regex pattern to match all manual page directories
    _MAN_DIRS_PATTERN = re.compile(r"/usr(/local)?(/share)?/man(/[^/]*)?/man[0-9][a-zA-Z_]*")

    @staticmethod
    def image_prefix() -> str:
        """prefix used for the non-shared root images"""
        return "ybox-local"

    @staticmethod
    def shared_image_prefix() -> str:
        """prefix used for the shared root images"""
        return "ybox-shared-local"

    @staticmethod
    def default_directory_mode() -> int:
        """return the default mode to use for new directories"""
        return 0o750

    @staticmethod
    def entrypoint_base() -> str:
        """entrypoint script name for the base container (which is booted to configure
           the final container)"""
        return "entrypoint-base.sh"

    @staticmethod
    def entrypoint_cp() -> str:
        """entrypoint script name for the "copy" container that copies files to shared root"""
        return "entrypoint-cp.sh"

    @staticmethod
    def entrypoint() -> str:
        """entrypoint script name for the final ybox container"""
        return "entrypoint.sh"

    @staticmethod
    def run_user_bash_cmd() -> str:
        """script used to force run a command as non-root user using `sudo` with `/bin/bash`"""
        return "run-user-bash-cmd"

    @staticmethod
    def resource_scripts() -> Iterable[str]:
        """all the scripts in the resources directory"""
        return (Consts.entrypoint_base(), Consts.entrypoint_cp(), Consts.entrypoint(),
                "entrypoint-common.sh", "entrypoint-root.sh", "entrypoint-user.sh",
                "prime-run", "run-in-dir", Consts.run_user_bash_cmd())

    @staticmethod
    def shared_root_mount_dir() -> str:
        """directory where shared root directory is mounted in a container during setup"""
        return "/ybox-root"

    @staticmethod
    def status_target_file() -> str:
        """target location where status_file is mounted in container"""
        return "/usr/local/ybox-status"  # this should match the one in entrypoint-common.sh

    @staticmethod
    def entrypoint_init_done_file() -> str:
        """file that indicates completion of first run initialization by entrypoint.sh script"""
        return "ybox-init.done"

    @staticmethod
    def container_desktop_dirs() -> Iterable[str]:
        """directories on the container that has desktop files that may need to be wrapped"""
        return ("/usr/share/applications",)

    @staticmethod
    def container_icon_dirs() -> Iterable[str]:
        """directories on the container (as regexes) that may have application icons"""
        return ("/usr/share/icons/hicolor/scalable/.*", "/usr/share/icons/hicolor/([1-9]+)x.*",
                "/usr/share/icons/hicolor/symbolic/.*", "/usr/share/icons", "/usr/share/pixmaps")

    @staticmethod
    def container_bin_dirs() -> Iterable[str]:
        """directories on the container that has executables that may need to be wrapped"""
        return Consts._SYS_BIN_DIRS

    @staticmethod
    def container_man_dir_pattern() -> re.Pattern[str]:
        """directory regex pattern on the container having man-pages that may need to be linked"""
        return Consts._MAN_DIRS_PATTERN

    @staticmethod
    def sys_bin_dirs() -> Iterable[str]:
        """standard directories to search for system installed executables"""
        return Consts._SYS_BIN_DIRS

    @staticmethod
    def nvidia_target_base_dir() -> str:
        """base directory path where NVIDIA libs/data are linked in the container"""
        return "/usr/local/nvidia"

    @staticmethod
    def nvidia_setup_script() -> str:
        """
        name of the NVIDIA setup script in the container
        (location is `StaticConfiguration.target_scripts_dir`)
        """
        return "nvidia-setup.sh"

    @staticmethod
    def default_pager() -> str:
        """
        default pager to show output one screenful at a time on the terminal when YBOX_PAGER
        environment variable is not set
        """
        return "/usr/bin/less -RLFXK"

    @staticmethod
    def default_field_separator() -> str:
        """default separator used between the fields in output of podman/docker exec commands"""
        return "::::"

    @staticmethod
    def default_key_server() -> str:
        """default gpg key server to use when not specified in the distribution's `distro.ini`"""
        return "hkps://keys.openpgp.org"
