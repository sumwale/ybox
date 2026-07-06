"""
Defines some constants used by other modules.
"""

import re
from typing import Iterable


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
    def root_mount_dir() -> str:
        """directory where container's root directory is mounted in a container during setup"""
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

    @staticmethod
    def containers_config_dir() -> str:
        """base directory name having all the container specific configuration directories"""
        return "containers"

    @staticmethod
    def container_env_file() -> str:
        """file having a container's environment variables required by `podman/docker run`"""
        return "env"

    @staticmethod
    def container_args_file() -> str:
        """file having a container's `podman/docker run` arguments separated by newlines"""
        return "args"

    @staticmethod
    def container_dynamic_args_file() -> str:
        """file having a container's dynamic arguments (with `DynamicToken` names)"""
        return "args.dyn"
