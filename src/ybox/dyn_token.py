"""
Defines the `DynamicToken` enumeration that helps resolve tokens embedded in podman/docker
arguments file to actual arguments that can change between container launches.
"""

import os
from enum import Enum
from typing import Callable

from ybox.config import StaticConfiguration
from ybox.run.nvidia import enable_nvidia


def _resolve_dbus_mount(conf: StaticConfiguration) -> str:
    # pylint: disable=unused-argument
    """return the podman/docker argument to mount the socket of user's session D-Bus"""
    if dbus_session := os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        dbus_path = dbus_session[dbus_session.find("=") + 1:]
        if (dbus_opts_idx := dbus_path.find(",")) != -1:
            dbus_path = dbus_path[:dbus_opts_idx]
        return f"-v={dbus_path}:{dbus_path}"
    return ""


def _resolve_wayland_mount(conf: StaticConfiguration, file_ext: str = "") -> str:
    """return the podman/docker argument to mount the Wayland socket or lock file"""
    env = conf.env
    if (wayland_display := os.environ.get("WAYLAND_DISPLAY")) and os.path.exists(
            wayland_file := f"{env.xdg_rt_dir}/{wayland_display}{file_ext}"):
        wayland_target_file = f"{env.target_xdg_rt_dir}/{wayland_display}{file_ext}"
        return f"-v={wayland_file}:{wayland_target_file}"
    return ""


def _resolve_any_mount(name: str, conf: StaticConfiguration) -> str:
    # pylint: disable=unused-argument
    """return the podman/docker argument to mount a path in the given environment variable"""
    if mount_path := os.environ.get(name):
        return f"-v={mount_path}:{mount_path}"
    return ""


def _enable_nvidia(conf: StaticConfiguration) -> list[str]:
    """return all the device and mount arguments required to enable NVIDIA support"""
    docker_args: list[str] = []
    enable_nvidia(docker_args, conf)
    return docker_args


def _enable_v4l(conf: StaticConfiguration) -> list[str]:
    # pylint: disable=unused-argument
    """return the device arguments required to enable all available v4l devices"""
    docker_args: list[str] = []
    sys_v4l = "/sys/class/video4linux"
    if os.path.exists(sys_v4l):
        # get all the paths in the dir and check which ones have a corresponding device in /dev
        for dev_name in os.listdir(sys_v4l):
            dev_path = f"/dev/{dev_name}"
            if os.path.exists(dev_path):
                docker_args.append(f"--device={dev_path}")
    return docker_args


class DynamicToken(Enum):
    """
    Holds the allowed 'tokens' in the container launch arguments file that are resolved at runtime.
    The value of each 'token' is a zero-argument function to be invoked to obtain the corresponding
    podman/docker arguments. A single argument is returned as a single string while multiple are
    returned as an `Iterable` of strings.
    """
    _XAUTH_MOUNT_FN: Callable[[StaticConfiguration], str] = lambda conf: \
        _resolve_any_mount("XAUTHORITY", conf)
    _WAYLAND_LOCK_FN: Callable[[StaticConfiguration], str] = lambda conf: \
        _resolve_wayland_mount(conf, ".lock")
    _SSH_MOUNT_FN: Callable[[StaticConfiguration], str] = lambda conf: \
        _resolve_any_mount("SSH_AUTH_SOCK", conf)
    _GPG_MOUNT_FN: Callable[[StaticConfiguration], str] = lambda conf: \
        _resolve_any_mount("GPG_AGENT_INFO", conf)

    DBUS_MOUNT = (_resolve_dbus_mount,)
    XAUTHORITY_MOUNT = (_XAUTH_MOUNT_FN,)
    WAYLAND_MOUNT = (_resolve_wayland_mount,)
    WAYLAND_LOCK = (_WAYLAND_LOCK_FN,)
    SSH_SOCK_MOUNT = (_SSH_MOUNT_FN,)
    GPG_AGENT_MOUNT = (_GPG_MOUNT_FN,)
    ENABLE_NVIDIA = (_enable_nvidia,)
    ENABLE_V4L = (_enable_v4l,)
