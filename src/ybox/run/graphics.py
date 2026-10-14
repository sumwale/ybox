"""
Methods for setting up graphics in the container including X11/Wayland and DRI.
"""

import os

from ybox.dyn_token import DynamicToken
from ybox.util import add_env_option, add_mount_option


def enable_x11(docker_args: list[str]) -> None:
    """
    Append options to podman/docker arguments to share host machine's Xorg X11 server
    with the new ybox container. This also sets up sharing of XAUTHORITY file (with automatic
    update, if required, in the `run-in-dir` script) so that no additional setup is required for
    X authentication to work.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    """
    add_env_option(docker_args, "DISPLAY")
    xsock = "/tmp/.X11-unix"
    if os.access(xsock, os.R_OK):
        add_mount_option(docker_args, xsock, xsock, "ro")
    add_env_option(docker_args, "XAUTHORITY")  # pick the value set in current env
    # special token string resolved when `ybox-launch` is invoked
    docker_args.append(f"{{{DynamicToken.XAUTHORITY_MOUNT.name}}}")


def enable_wayland(docker_args: list[str]) -> None:
    """
    Append options to podman/docker arguments to share host machine's Wayland server
    with the new ybox container.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    """
    add_env_option(docker_args, "WAYLAND_DISPLAY")  # pick the value set in current env
    # special token strings resolved when `ybox-launch` is invoked
    docker_args.append(f"{{{DynamicToken.WAYLAND_MOUNT.name}}}")
    docker_args.append(f"{{{DynamicToken.WAYLAND_LOCK.name}}}")


def enable_dri(docker_args: list[str]) -> None:
    """
    Append options to podman/docker arguments to enable DRI access.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    """
    if os.access("/dev/dri", os.R_OK):
        docker_args.append("--device=/dev/dri")
    if os.access("/dev/dri/by-path", os.R_OK):
        add_mount_option(docker_args, "/dev/dri/by-path", "/dev/dri/by-path")
