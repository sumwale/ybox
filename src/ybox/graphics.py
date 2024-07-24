"""
Methods for setting up graphics in the container including X11/Wayland, NVIDIA etc.
"""

import glob
import os
from itertools import chain
from os.path import realpath
from typing import Optional

from ybox.config import Consts, StaticConfiguration
from .env import Environ

_STD_LIB_DIRS = ["/usr/lib", "/lib", "/usr/local/lib"]
_STD_LIB64_DIRS = ["/usr/lib/x86_64-linux-gnu", "/lib/x86_64-linux-gnu", "/usr/lib64", "/lib64"]
_STD_LIB32_DIRS = ["/usr/lib/i386-linux-gnu", "/lib/i386-linux-gnu",
                   "/usr/lib/i686-linux-gnu", "/lib/i686-linux-gnu", "/usr/lib32", "/lib32"]
_STD_BIN_DIRS = ["/bin", "/usr/bin", "/sbin", "/usr/sbin", "/usr/local/bin", "/usr/local/sbin"]
_STD_LD_LIB_PATH_VARS = ["LD_LIBRARY_PATH", "LD_LIBRARY_PATH_64", "LD_LIBRARY_PATH_32"]
_NVIDIA_LIB_PATTERNS = ["*nvidia*.so*", "*NVIDIA*.so*", "libcuda*.so*", "libnvcuvid*.so*",
                        "libnvoptix*.so*", "gbm/*nvidia*.so*", "vdpau/*nvidia*.so*"]
_NVIDIA_BIN_PATTERNS = ["nvidia-smi", "nvidia-cuda*", "nvidia-debug*", "nvidia-bug*"]
# note that the code below assumes that file name pattern below is always of the form *nvidia*
# (while others are directories), so if that changes then update _process_nvidia_data_files
_NVIDIA_DATA_PATTERNS = ["/usr/share/nvidia", "/usr/local/share/nvidia", "/lib/firmware/nvidia",
                         "/usr/share/egl/*/*nvidia*", "/usr/share/glvnd/*/*nvidia*",
                         "/usr/share/vulkan/*/*nvidia*"]
_LD_SO_CONF = "/etc/ld.so.conf"


def add_env_option(args: list[str], env_var: str, env_val: Optional[str] = None) -> None:
    if env_val is None:
        args.append(f"-e={env_var}")
    else:
        args.append(f"-e={env_var}={env_val}")


def add_mount_option(args: list[str], src: str, dest: str, flags: str = "") -> None:
    if flags:
        args.append(f"-v={src}:{dest}:{flags}")
    else:
        args.append(f"-v={src}:{dest}")


def enable_x11(args: list[str]) -> None:
    add_env_option(args, "DISPLAY")
    xsock = "/tmp/.X11-unix"
    if os.access(xsock, os.R_OK):
        add_mount_option(args, xsock, xsock, "ro")
    if xauth := os.environ.get("XAUTHORITY"):
        # XAUTHORITY file may change after a restart or login (e.g. with Xwayland), so mount its
        # parent directory which is adjusted by run-in-dir script if it has changed
        parent_dir = os.path.dirname(xauth)
        target_dir = f"{parent_dir}-host"
        target_xauth = f"{target_dir}/{os.path.basename(xauth)}"
        add_mount_option(args, parent_dir, target_dir, "ro")
        add_env_option(args, "XAUTHORITY", target_xauth)
        add_env_option(args, "XAUTHORITY_ORIG", target_xauth)


def enable_wayland(args: list[str], env: Environ) -> None:
    if env.xdg_rt_dir and (wayland_display := os.environ.get("WAYLAND_DISPLAY")):
        add_env_option(args, "WAYLAND_DISPLAY", wayland_display)
        wayland_sock = f"{env.xdg_rt_dir}/{wayland_display}"
        if os.access(wayland_sock, os.W_OK):
            add_mount_option(args, wayland_sock, wayland_sock)


def enable_nvidia(args: list[str], conf: StaticConfiguration) -> None:
    # search for nvidia device files and add arguments for those
    for nvidia_dev in _find_nvidia_devices():
        args.append(f"--device={nvidia_dev}")
    # gather the library directories from standard paths, LD_LIBRARY_PATH* and /etc/ld.so.conf
    lib_dirs = _find_all_lib_dirs()
    # find the list of nvidia library directories to be mounted in the target container
    nvidia_lib_dirs = _filter_nvidia_dirs(lib_dirs, _NVIDIA_LIB_PATTERNS)
    # add the directories to tbe mounted to docker/podman arguments
    mount_nvidia_subdir = conf.target_scripts_dir
    mount_lib_dirs = _prepare_mount_dirs(nvidia_lib_dirs, args, f"{mount_nvidia_subdir}/mnt_lib")
    # create the script to be run in the container which will create the target
    # directories that will be added to LD_LIBRARY_PATH having symlinks to the mounted libraries
    nvidia_setup = _create_nvidia_setup(args, mount_lib_dirs)

    # mount nvidia binary directories and add code to script to link to them in container
    nvidia_bin_dirs = _filter_nvidia_dirs({realpath(d) for d in _STD_BIN_DIRS},
                                          _NVIDIA_BIN_PATTERNS)
    mount_bin_dirs = _prepare_mount_dirs(nvidia_bin_dirs, args, f"{mount_nvidia_subdir}/mnt_bin")
    _add_nvidia_bin_links(mount_bin_dirs, nvidia_setup)

    # finally mount nvidia data file directories and add code to script to link to them
    # which has to be the same paths as in the host
    _process_nvidia_data_files(args, nvidia_setup, f"{mount_nvidia_subdir}/mnt_share")

    # create the nvidia setup script
    setup_script = f"{conf.scripts_dir}/{Consts.nvidia_setup_script()}"
    with open(setup_script, "w", encoding="utf-8") as script_fd:
        script_fd.write("\n".join(nvidia_setup))


def _find_nvidia_devices() -> list[str]:
    return [p for p in chain(glob.glob("/dev/nvidia*"), glob.glob(
        "/dev/nvidia*/**/*", recursive=True)) if not os.path.isdir(p)]


def _find_all_lib_dirs() -> set[str]:
    # iterate standard library paths, then LD_LIBRARY_PATH components
    ld_libs: list[str] = []
    for lib_path_var in _STD_LD_LIB_PATH_VARS:
        if ld_lib := os.environ.get(lib_path_var):
            ld_libs.extend(ld_lib.split(os.pathsep))
    lib_dirs = {r for p in chain(_STD_LIB_DIRS, _STD_LIB64_DIRS, _STD_LIB32_DIRS,
                                 ld_libs) if (r := realpath(p)) if os.path.isdir(r)}
    _parse_ld_so_conf(_LD_SO_CONF, lib_dirs)
    return lib_dirs


def _parse_ld_so_conf(conf: str, ld_lib_paths: set[str]) -> None:
    if os.access(conf, os.R_OK):
        with open(conf, "r", encoding="utf-8") as conf_fd:
            while line := conf_fd.readline():
                if line[0] != '#':
                    words = line.split()
                    if len(words) > 0:
                        if words[0].lower() == "include":
                            for inc in glob.glob(words[1]):
                                _parse_ld_so_conf(inc, ld_lib_paths)
                        else:
                            ld_lib_paths.add(realpath(line.strip()))


def _filter_nvidia_dirs(dirs: set[str], patterns: list[str]) -> list[str]:
    def has_nvidia_artifact(d: str) -> bool:
        for pat in patterns:
            if glob.glob(f"{d}/{pat}"):
                return True
        return False

    return [lib_dir for lib_dir in dirs if has_nvidia_artifact(lib_dir)]


def _prepare_mount_dirs(dirs: list[str], args: list[str], mount_dir_prefix: str) -> list[str]:
    mount_dirs: list[str] = []
    for idx, d in enumerate(dirs):
        mount_dir = f"{mount_dir_prefix}{idx}"
        add_mount_option(args, d, mount_dir, "ro")
        mount_dirs.append(mount_dir)
    return mount_dirs


def _create_nvidia_setup(args: list[str], mount_lib_dirs: list[str]) -> list[str]:
    target_dir = Consts.nvidia_target_base_dir()
    setup_script = ["# this script should be run using bash", "", "# setup libraries", "",
                    f"mkdir -p {target_dir} && chmod 0755 {target_dir}"]
    ld_lib_path: list[str] = []
    for idx, mount_lib_dir in enumerate(mount_lib_dirs):
        target_lib_dir = f"{target_dir}/lib{idx}"
        setup_script.append(f"rm -rf {target_lib_dir}")
        setup_script.append(f"mkdir -p {target_lib_dir} && chmod 0755 {target_lib_dir}")
        for pat in _NVIDIA_LIB_PATTERNS:
            setup_script.append(f'libs="$(compgen -G "{mount_lib_dir}/{pat}")"')
            setup_script.append(
                f'if [ "$?" -eq 0 ]; then ln -s $libs {target_lib_dir}/. 2>/dev/null; fi')
        ld_lib_path.append(target_lib_dir)
    # add libraries to LD_LIBRARY_PATH rather than adding to system /etc/ld.so.conf otherwise
    # the system ldconfig cache may go out of sync from another shared root container that does
    # not have nvidia enabled
    if ld_lib_path:
        add_env_option(args, "LD_LIBRARY_PATH", os.pathsep.join(ld_lib_path))
    return setup_script


def _add_nvidia_bin_links(mount_bin_dirs: list[str], script: list[str]) -> None:
    script.append("# setup binaries")
    for mount_bin_dir in mount_bin_dirs:
        for pat in _NVIDIA_BIN_PATTERNS:
            script.append(f'bins="$(compgen -G "{mount_bin_dir}/{pat}")"')
            script.append('if [ "$?" -eq 0 ]; then ln -sf $bins /usr/local/bin/. 2>/dev/null; fi')


def _process_nvidia_data_files(args: list[str], script: list[str],
                               mount_data_dir_prefix: str) -> None:
    script.append("# setup data files")
    nvidia_data_dirs = set[str]()
    idx = 0
    for pat in _NVIDIA_DATA_PATTERNS:
        for path in glob.glob(pat):
            if not os.path.exists(resolved_path := realpath(path)):
                continue
            path_is_dir = os.path.isdir(resolved_path)
            data_dir = resolved_path if path_is_dir else os.path.dirname(resolved_path)
            if data_dir in nvidia_data_dirs:
                continue
            mount_data_dir = f"{mount_data_dir_prefix}{idx}"
            idx += 1
            add_mount_option(args, data_dir, mount_data_dir, "ro")
            nvidia_data_dirs.add(data_dir)
            if path_is_dir:
                # links for data directories need to be in the same location as original
                script.append(f"rm -rf {path} && ln -s {mount_data_dir} {path}")
            else:
                # assume that files inside other directories have the pattern "*nvidia*",
                # so the code avoids hard-coding fully resolved patterns to deal with
                # a case when the data file name changes after driver upgrade
                path_dir = os.path.dirname(path)
                script.append(f"mkdir -p {path_dir} && chmod 0755 {path_dir} && \\")
                script.append(f"  ln -sf {mount_data_dir}/*nvidia* {path_dir}/. 2>/dev/null")
