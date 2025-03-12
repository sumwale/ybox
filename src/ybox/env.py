"""
Useful user environment settings.
"""

import getpass
import os
import pwd
import site
import subprocess
from datetime import datetime
from importlib.abc import Traversable
from importlib.resources import files
from pathlib import Path
from typing import Optional, Union

from .print import print_error, print_notice

PathName = Union[Path, Traversable]


def get_docker_command() -> str:
    """
    If a custom podman/docker executable is defined by YBOX_CONTAINER_MANAGER environment variable,
    then return it else check for podman and docker (in that order) in the standard /usr/bin path.

    :return: the podman/docker executable specified in arguments or defined by
             YBOX_CONTAINER_MANAGER environment variable
    """
    # check for podman first then docker
    if cmd := os.environ.get("YBOX_CONTAINER_MANAGER"):
        if os.access(cmd, os.X_OK):
            return cmd
        raise PermissionError(
            f"Cannot execute '{cmd}' provided in YBOX_CONTAINER_MANAGER environment variable")
    if os.access("/usr/bin/podman", os.X_OK):
        return "/usr/bin/podman"
    if os.access("/usr/bin/docker", os.X_OK):
        return "/usr/bin/docker"
    raise FileNotFoundError(
        "No podman/docker found in /usr/bin and $YBOX_CONTAINER_MANAGER not defined")


class NotSupportedError(Exception):
    """Raised when an operation or configuration is not supported or invalid."""


class Environ:
    """
    Holds common environment variables useful for the scripts like $HOME, $XDG_RUNTIME_DIR.
    It sets up the $TARGET_HOME environment variable which is the $HOME inside the container.
    Also captures the current time and sets up the $NOW environment variable.
    """

    def __init__(self, docker_cmd: Optional[str] = None, home_dir: Optional[str] = None):
        """
        Initialize the `Environ` object providing the podman/docker command to use.

        :param docker_cmd: the podman/docker executable to use,
                           defaults to :func:`get_docker_command()`
        :param home_dir: if a non-default user home directory has to be set
        """
        self._home_dir = home_dir or os.path.expanduser("~")
        self._home_dir = self._home_dir.rstrip("/")
        self._docker_cmd = docker_cmd or get_docker_command()
        cmd_version = subprocess.check_output([self._docker_cmd, "--version"])
        self._uses_podman = "podman" in cmd_version.decode("utf-8").lower()
        # local user home might be in a different location than /home but target user in the
        # container will always be in /home with podman else /root for the root user with docker
        # as ensured by entrypoint-base.sh script
        current_user = getpass.getuser()
        current_uid = pwd.getpwnam(current_user).pw_uid
        if self._uses_podman:
            self._target_user = current_user
            target_uid = current_uid
            self._target_home = f"/home/{self._target_user}"
        else:
            self._target_user = "root"
            target_uid = 0
            self._target_home = "/root"
            # confirm that docker is being used in rootless mode (not required for podman because
            #   it runs as rootless when run by a non-root user in any case without explicit sudo
            #   which the ybox tools don't use)
            if (docker_ctx := subprocess.check_output(
                    [self._docker_cmd, "context", "show"]).decode("utf-8")).strip() != "rootless":
                # check for DOCKER_HOST environment variable
                expected_docker_host = f"unix:///run/user/{current_uid}/docker.sock"
                if not docker_ctx or os.environ.get("DOCKER_HOST", "") != expected_docker_host:
                    raise NotSupportedError("docker should use the rootless mode (see "
                                            "https://docs.docker.com/engine/security/rootless/) "
                                            f"but the current context is '{docker_ctx}' and "
                                            f"$DOCKER_HOST is not set to '{expected_docker_host}'")
        os.environ["TARGET_HOME"] = self._target_home
        self._user_base = user_base = site.getuserbase()
        target_user_base = f"{self._target_home}/.local"
        self._data_dir = f"{user_base}/share/ybox"
        self._target_data_dir = f"{target_user_base}/share/ybox"
        self._xdg_rt_dir = os.environ.get("XDG_RUNTIME_DIR", "").rstrip("/")
        # the container user's one can be different because it is the root user for docker
        self._target_xdg_rt_dir = f"/run/user/{target_uid}"
        self._now = datetime.now()
        os.environ["NOW"] = str(self._now)
        sys_conf_dir = files("ybox").joinpath("conf")
        os.environ["YBOX_SYS_CONF_DIR"] = str(sys_conf_dir)
        self._sys_conf_dirs = [sys_conf_dir]
        self._root_dir = [Path("/")]
        self._configuration_dirs: list[PathName] = []
        # for tests, only the bundled configurations should be tested
        if os.environ.get("YBOX_TESTING"):
            print_notice("Running with YBOX_TESTING enabled")
            self._configuration_dirs = self._sys_conf_dirs
        else:
            self._configuration_dirs = [Path(f"{self._home_dir}/.config/ybox"),
                                        sys_conf_dir]
        self._user_applications_dir = f"{user_base}/share/applications"
        self._user_executables_dir = f"{user_base}/bin"

    def search_config_path(self, conf_path: str, only_sys_conf: bool = False,
                           quiet: bool = False) -> PathName:
        """
        Search for given configuration path in user and system configuration directories
        (in that order). The path may refer to a file or a subdirectory.

        :param conf_path: the configuration file to search (expected to be a relative path)
        :param only_sys_conf: if True then search only system configuration directory else
                              search for user configuration directory first then the system one
        :param quiet: if False then prints an error message on standard output on failure
        :return: the path of the configuration file as `Path` or resource file from
                 importlib (i.e. `Traversable`)
        """
        if os.path.isabs(conf_path):
            conf_dirs = self._root_dir
        else:
            conf_dirs = self._sys_conf_dirs if only_sys_conf else self._configuration_dirs
        for config_dir in conf_dirs:
            path = config_dir.joinpath(conf_path)
            if os.access(path, os.R_OK):  # type: ignore
                return path
        search_dirs = ', '.join([str(file) for file in conf_dirs])
        if not quiet:
            print_error(f"Configuration file '{conf_path}' not found in [{search_dirs}]")
        raise FileNotFoundError(f"Missing configuration file '{conf_path}'")

    @property
    def home(self) -> str:
        """home directory of the current user"""
        return self._home_dir

    @property
    def docker_cmd(self) -> str:
        """path of the podman/docker executable to use for all the commands"""
        return self._docker_cmd

    @property
    def uses_podman(self) -> bool:
        """if podman is the container manager being used"""
        return self._uses_podman

    def systemd_user_conf_dir(self) -> str:
        """standard configuration directory location of user specific systemd services"""
        return f"{self._home_dir}/.config/systemd/user"

    @property
    def target_user(self) -> str:
        """username of the container user (which is the same as the current user for podman
           and root for docker)"""
        return self._target_user

    # home directory of the container user (which is $TARGET_HOME=/home/$USER for podman
    #   and /root for docker)
    @property
    def target_home(self) -> str:
        """home directory of the container user (which is $TARGET_HOME=/home/$USER for podman
           and /root for docker)"""
        return self._target_home

    @property
    def data_dir(self) -> str:
        """base user directory where runtime data related to all the containers is
           stored in subdirectories"""
        return self._data_dir

    @property
    def target_data_dir(self) -> str:
        """base user directory of the container user where runtime data related to all
           the containers is stored"""
        return self._target_data_dir

    @property
    def xdg_rt_dir(self) -> str:
        """value of $XDG_RUNTIME_DIR in the current session"""
        return self._xdg_rt_dir

    @property
    def target_xdg_rt_dir(self) -> str:
        """value of $XDG_RUNTIME_DIR for the user in the container"""
        return self._target_xdg_rt_dir

    @property
    def now(self) -> datetime:
        """current time as captured during Environ object creation"""
        return self._now

    @property
    def user_base(self) -> str:
        """User's local base data directory which is typically ~/.local"""
        return self._user_base

    @property
    def user_applications_dir(self) -> str:
        """User's local applications directory that holds the .desktop files"""
        return self._user_applications_dir

    @property
    def user_executables_dir(self) -> str:
        """User's local executables directory which should be in the $PATH"""
        return self._user_executables_dir
