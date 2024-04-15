import argparse
import os
import sys

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
        self._box_name = box_name
        self._box_image = f"zbox-local/{distro}/{box_name}"
        self._shared_box_image = f"zbox-shared-local/{distro}"
        self._configuration_dirs = [f"{env.home}/.config/zbox", "/etc/zbox"]
        # timezone properties
        self._localtime = None
        self._timezone = None
        if os.path.islink("/etc/localtime"):
            self._localtime = os.readlink("/etc/localtime")
        if os.path.exists("/etc/timezone"):
            with open("/etc/timezone") as tz:
                self._timezone = tz.read().rstrip("\n")
        # user data directory is $HOME/.local/share/zbox
        self._data_dir = ".local/share/zbox"
        self._shared_root_host_dir = f"{env.home}/{self._data_dir}/ROOTS/{distro}"
        self._container_dir = f"{env.home}/{self._data_dir}/{box_name}"
        os.environ["CONTAINER_DIR"] = self._container_dir
        self._configs_dir = f"{self._container_dir}/configs"
        self._target_configs_dir = f"{env.target_home}/{self._data_dir}/{box_name}/configs"
        self._scripts_dir = f"{self._container_dir}/zbox-scripts"
        self._status_file = f"{self._container_dir}/status"
        self._config_list = f"{self._scripts_dir}/config.list"

    # name of the container
    @property
    @typechecked
    def box_name(self) -> str:
        return self._box_name

    # Container image created with basic required user configuration from base image.
    # This can either be container specific, or if 'base.shared_root' is true, then
    # it will be common for all such images for the same distribution.
    @typechecked
    def box_image(self, shared_root: bool) -> str:
        return self._shared_box_image if shared_root else self._box_image

    # local and global directories having configuration files for the containers
    @property
    @typechecked
    def configuration_dirs(self) -> list[str]:
        return self._configuration_dirs

    # the target link for /etc/localtime
    @property
    @typechecked
    def localtime(self) -> str:
        return self._localtime

    # the contents of /etc/timezone
    @property
    @typechecked
    def timezone(self) -> str:
        return self._timezone

    # host directory that is bind mounted as the shared root directory on containers
    @property
    @typechecked
    def shared_root_host_dir(self) -> str:
        return self._shared_root_host_dir

    # directory where shared root directory is mounted in a container during setup
    @property
    @typechecked
    def shared_root_mount_dir(self) -> str:
        return "/zbox-root"

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

    # file containing list of configuration files to be linked on that container to host
    # as mentioned in the [configs] section
    @property
    @typechecked
    def config_list(self) -> str:
        return self._config_list
