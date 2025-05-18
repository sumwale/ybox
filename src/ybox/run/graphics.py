"""
Methods for setting up graphics in the container including X11/Wayland, NVIDIA etc.
"""

import glob
import os
from itertools import chain
from os.path import realpath
from typing import Iterable, Optional

from ybox.config import Consts, StaticConfiguration
from ybox.env import Environ

# standard library directories to search for NVIDIA libraries
_STD_LIB_DIRS = ["/usr/lib", "/lib", "/usr/local/lib", "/usr/lib64", "/lib64",
                 "/usr/lib32", "/lib32"]
# additional library directory glob patterns to search for NVIDIA libraries in 32/64-bit systems;
# the '&' in front of the paths is an indicator to the code that this is a glob pattern
_STD_LIB_DIR_PATTERNS = ["&/usr/lib/*-linux-gnu", "&/lib/*-linux-gnu", "&/usr/lib64/*-linux-gnu",
                         "&/lib64/*-linux-gnu", "&/usr/lib32/*-linux-gnu", "&/lib32/*-linux-gnu"]
_STD_LD_LIB_PATH_VARS = ["LD_LIBRARY_PATH", "LD_LIBRARY_PATH_64", "LD_LIBRARY_PATH_32"]
_NVIDIA_LIB_PATTERNS = ["*nvidia*.so*", "*NVIDIA*.so*", "libcuda*.so*", "libnvcuvid*.so*",
                        "libnvoptix*.so*", "gbm/*nvidia*.so*", "vdpau/*nvidia*.so*",
                        "libXNVCtrl.so*"]
_NVIDIA_BIN_PATTERNS = ["nvidia-smi", "nvidia-cuda*", "nvidia-debug*", "nvidia-bug*"]
# note that the code below assumes that file name pattern below is always of the form *nvidia*
# (while others are directories), so if that changes then update _process_nvidia_data_files
_NVIDIA_DATA_PATTERNS = ["/usr/share/nvidia", "/usr/local/share/nvidia", "/lib/firmware/nvidia",
                         "/usr/share/egl/*/*nvidia*", "/usr/share/glvnd/*/*nvidia*",
                         "/usr/share/vulkan/*/*nvidia*"]
_LD_SO_CONF = "/etc/ld.so.conf"


def add_env_option(docker_args: list[str], env_var: str, env_val: Optional[str] = None) -> None:
    """
    Add option to the list of podman/docker arguments to set an environment variable.

    :param docker_args: list of podman/docker arguments to which required option has to be appended
    :param env_var: the environment variable to be set
    :param env_val: the value of the environment variable, defaults to None which implies that
                    its value will be set to be the same as in the host environment
    """
    if env_val is None:
        docker_args.append(f"-e={env_var}")
    else:
        docker_args.append(f"-e={env_var}={env_val}")


def add_mount_option(docker_args: list[str], src: str, dest: str, flags: str = "",
                     check_exists: bool = False) -> None:
    """
    Add option to the list of podman/docker arguments to bind mount a source directory to
    given destination directory.

    :param docker_args: list of podman/docker arguments to which required option has to be appended
    :param src: the source directory in the host system
    :param dest: the destination directory in the container
    :param flags: any additional flags to be passed to `-v` podman/docker argument, defaults to ""
    :param check_exists: check if the bind mount was already added (and skip if so)
    """
    mount_arg = f"-v={src}:{dest}:{flags}" if flags else f"-v={src}:{dest}"
    if not check_exists or mount_arg not in docker_args:
        docker_args.append(mount_arg)


def handle_variable_mount(docker_args: list[str], env: Environ, mount_path: str) -> str:
    """
    Handle the case where a mount point may change in different starts or even within the same
    started container instance. In these cases the "base" directory of the mount point is
    mounted instead which should normally be `/tmp` or `$XDG_RUNTIME_DIR`. The variable values
    are assumed to lie between these two, or the parent directory of the mount point if it does
    not lie within these two base directories. The actual passing of the required environment
    variable (that can change) is handled by the `run-in-dir` script that will adjust the variable
    value to reflect that mount point added by this method.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    :param env: an instance of the current :class:`Environ`
    :param mount_path: the variable path which is usually the value of an environment variable
    :return: the result mount point inside the container for the `mount_path`
    """
    base_dir = os.path.dirname(mount_path)
    # check if parent_dir is in $XDG_RUNTIME_DIR or /tmp
    if not env.xdg_rt_dir:
        base_dirs = {base_dir, "/tmp"}
    elif mount_path.startswith(env.xdg_rt_dir + "/") or mount_path.startswith("/tmp/"):
        base_dirs = (env.xdg_rt_dir, "/tmp")
        base_dir = "/tmp" if base_dir.startswith("/tmp") else env.xdg_rt_dir
    else:
        base_dirs = (base_dir, env.xdg_rt_dir, "/tmp")
    for b_dir in base_dirs:
        add_mount_option(docker_args, b_dir, f"{b_dir}-host", "ro", check_exists=True)
    return mount_path.replace(base_dir, f"{base_dir}-host")


def enable_x11(docker_args: list[str], env: Environ) -> None:
    """
    Append options to podman/docker arguments to share host machine's Xorg X11 server
    with the new ybox container. This also sets up sharing of XAUTHORITY file (with automatic
    update, if required, in the `run-in-dir` script) so that no additional setup is required for
    X authentication to work.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    :param env: an instance of the current :class:`Environ`
    """
    add_env_option(docker_args, "DISPLAY")
    xsock = "/tmp/.X11-unix"
    if os.access(xsock, os.R_OK):
        add_mount_option(docker_args, xsock, xsock, "ro")
    if xauth := os.environ.get("XAUTHORITY"):
        # XAUTHORITY file may change after a restart or login (e.g. with Xwayland), so mount some
        # parent directory which is adjusted by run-in-dir script if it has changed;
        # For now the known common parents are used below since using just the immediate
        # parent can cause trouble if one changes the display manager, for example, which
        # uses an entirely different mount point (e.g. gdm uses /run/user/... while sddm
        #   uses /tmp)
        target_xauth = handle_variable_mount(docker_args, env, xauth)
        add_env_option(docker_args, "XAUTHORITY", target_xauth)
        add_env_option(docker_args, "XAUTHORITY_ORIG", target_xauth)


def enable_wayland(docker_args: list[str], env: Environ) -> None:
    """
    Append options to podman/docker arguments to share host machine's Wayland server
    with the new ybox container.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    :param env: an instance of the current :class:`Environ`
    """
    if env.xdg_rt_dir:
        add_env_option(docker_args, "WAYLAND_DISPLAY")
        # don't bind wayland sockets rather link in entrypoint so that it works even
        # when run in X11 setup after being created in Wayland setup
        add_env_option(docker_args, "ENABLE_WAYLAND", "true")


def enable_dri(docker_args: list[str]) -> None:
    """
    Append options to podman/docker arguments to enable DRI access.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    """
    if os.access("/dev/dri", os.R_OK):
        docker_args.append("--device=/dev/dri")
    if os.access("/dev/dri/by-path", os.R_OK):
        add_mount_option(docker_args, "/dev/dri/by-path", "/dev/dri/by-path")


def enable_nvidia(docker_args: list[str], conf: StaticConfiguration) -> None:
    """
    Append options to podman/docker arguments to share host machine's NVIDIA libraries and
    data files with the new ybox container.

    It mounts the required directories from the host system, creates a script in the container
    that is invoked by the container entrypoint script which create links to the NVIDIA libraries
    and data files and sets up LD_LIBRARY_PATH in the container to point to the NVIDIA library
    directories.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    :param conf: the :class:`StaticConfiguration` for the container
    """
    # search for nvidia device files and add arguments for those
    for nvidia_dev in _find_nvidia_devices():
        docker_args.append(f"--device={nvidia_dev}")
    # gather the library directories from standard paths, LD_LIBRARY_PATH* and /etc/ld.so.conf
    lib_dirs = _find_all_lib_dirs()
    # find the list of nvidia library directories to be mounted in the target container
    nvidia_lib_dirs = _filter_nvidia_dirs(lib_dirs, _NVIDIA_LIB_PATTERNS)
    # add the directories to tbe mounted to podman/docker arguments
    mount_nvidia_subdir = conf.target_scripts_dir
    mount_lib_dirs = _prepare_mount_dirs(nvidia_lib_dirs, docker_args,
                                         f"{mount_nvidia_subdir}/mnt_lib")
    # create the script to be run in the container which will create the target
    # directories that will be added to LD_LIBRARY_PATH having symlinks to the mounted libraries
    nvidia_setup = _create_nvidia_setup(docker_args, nvidia_lib_dirs, mount_lib_dirs)

    # mount nvidia binary directories and add code to script to link to them in container
    nvidia_bin_dirs = _filter_nvidia_dirs({realpath(d) for d in Consts.container_bin_dirs()},
                                          _NVIDIA_BIN_PATTERNS)
    mount_bin_dirs = _prepare_mount_dirs(nvidia_bin_dirs, docker_args,
                                         f"{mount_nvidia_subdir}/mnt_bin")
    _add_nvidia_bin_links(mount_bin_dirs, nvidia_setup)

    # finally mount nvidia data file directories and add code to script to link to them
    # which has to be the same paths as in the host
    _process_nvidia_data_files(docker_args, nvidia_setup, f"{mount_nvidia_subdir}/mnt_share")

    # create the nvidia setup script
    setup_script = f"{conf.scripts_dir}/{Consts.nvidia_setup_script()}"
    with open(setup_script, "w", encoding="utf-8") as script_fd:
        script_fd.write("\n".join(nvidia_setup))


def _find_nvidia_devices() -> list[str]:
    """
    Return the list of NVIDIA device files in /dev by matching against appropriate glob patterns.
    """
    return [p for p in chain(glob.glob("/dev/nvidia*"), glob.glob(
        "/dev/nvidia*/**/*", recursive=True)) if not os.path.isdir(p)]


def _find_all_lib_dirs() -> Iterable[str]:
    """
    Return the list of all the library directories used by the system for shared libraries which
    includes the LD_LIBRARY_PATH, /etc/ld.so.conf and standard library paths.
    """
    # add LD_LIBRARY_PATH components, then /etc/ld.so.conf and then standard library paths
    ld_libs: list[str] = []
    for lib_path_var in _STD_LD_LIB_PATH_VARS:
        if ld_lib := os.environ.get(lib_path_var):
            ld_libs.extend(ld_lib.split(os.pathsep))
    _parse_ld_so_conf(_LD_SO_CONF, ld_libs)
    # using dict with None values instead of set to preserve order while keeping keys unique
    lib_dirs = {r: None for p in chain(ld_libs, _STD_LIB_DIRS, _STD_LIB_DIR_PATTERNS)
                for d in (glob.glob(p[1:]) if p[0] == "&" else (p,))
                if (r := realpath(d)) and os.path.isdir(r)}
    return lib_dirs.keys()


def _parse_ld_so_conf(conf: str, ld_lib_paths: list[str]) -> None:
    """
    Read /etc/ld.so.conf and append all the mentioned library directories (including the
      `include` directives) in the list that has been passed.

    :param conf: the path to ld.so.conf being processed which is either /etc/ld.so.conf or
                 one of the files included by it (in the recursive call)
    :param ld_lib_paths: list of library directories to which the results are appended
    """
    if not os.access(conf, os.R_OK):
        return
    with open(conf, "r", encoding="utf-8") as conf_fd:
        while line := conf_fd.readline():
            if not (line := line.strip()) or line[0] == '#':
                continue
            if words := line.split():
                if words[0].lower() == "include":
                    for inc in glob.glob(words[1]):
                        _parse_ld_so_conf(inc, ld_lib_paths)
                else:
                    ld_lib_paths.append(realpath(line))


def _filter_nvidia_dirs(dirs: Iterable[str], patterns: list[str]) -> list[str]:
    """
    Filter out the directories having NVIDIA artifacts from the given `dirs`.

    :param dirs: an `Iterable` of directory paths that are checked for NVIDIA artifacts
    :param patterns: directory or file patterns to search in `dirs`
    :return: list of filtered directories that contain an NVIDIA artifact
    """
    def has_nvidia_artifact(d: str) -> bool:
        for pat in patterns:
            if glob.glob(f"{d}/{pat}"):
                return True
        return False

    return [nvidia_dir for nvidia_dir in dirs if has_nvidia_artifact(nvidia_dir)]


def _prepare_mount_dirs(dirs: list[str], docker_args: list[str],
                        mount_dir_prefix: str) -> list[str]:
    """
    Append options to the list of podman/docker arguments to bind mount given source directories
    to target directories having given prefix and index as the suffix. This means that the first
    directory in the given `dirs` will be mounted in `<prefix>0`, second in `<prefix>1` and so on.

    :param dirs: the list of source directories to be mounted
    :param docker_args: list of podman/docker arguments to which the options have to be appended
    :param mount_dir_prefix: the prefix of the destination directories
    :return: list of destination directories where the source directories will be mounted
    """
    mount_dirs: list[str] = []
    for idx, d in enumerate(dirs):
        mount_dir = f"{mount_dir_prefix}{idx}"
        add_mount_option(docker_args, d, mount_dir, "ro")
        mount_dirs.append(mount_dir)
    return mount_dirs


def _create_nvidia_setup(docker_args: list[str], src_dirs: list[str],
                         mount_lib_dirs: list[str]) -> list[str]:
    """
    Generate contents of a `bash` script (returned as a list of strings) to be run on container
    which will set up required NVIDIA libraries from the mounted host library directories.

    The script will create new directories in the container and links to NVIDIA libraries in those
    from the mounted directories. Then it will add option to podman/docker arguments to set
    LD_LIBRARY_PATH in the target container to point to these directories. The returned `bash`
    script should be executed as superuser by the container entrypoint script.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    :param src_dirs: the list of source directories to be mounted
    :param mount_lib_dirs: list of destination directory mounts
    :return: contents of a `bash` script as a list of strings for each line of the script which
             should be joined with newlines to get the final contents of the script
    """
    target_dir = Consts.nvidia_target_base_dir()
    setup_script = ["#!/bin/bash", "", "# this script should be run using bash", "",
                    "# setup libraries", "", f"mkdir -p {target_dir} && chmod 0755 {target_dir}"]
    ld_lib_path: list[str] = []
    for idx, mount_lib_dir in enumerate(mount_lib_dirs):
        target_lib_dir = f"{target_dir}/lib{idx}"
        setup_script.append(f"rm -rf {target_lib_dir}")
        setup_script.append(f"mkdir -p {target_lib_dir} && chmod 0755 {target_lib_dir}")
        for pat in _NVIDIA_LIB_PATTERNS:
            setup_script.append(f'libs="$(compgen -G "{mount_lib_dir}/{pat}")"')
            setup_script.append('if [ "$?" -eq 0 ]; then')
            setup_script.append(f"  ln -s $libs {target_lib_dir}/. 2>/dev/null")
            # if host library is in a sub-directory then create sub-directory on target too
            if (slash_index := pat.find("/")) != -1:
                # check for corresponding library in host path and /usr/lib
                pat_subdir = pat[:slash_index]
                src_dir = f"{src_dirs[idx]}/{pat_subdir}"
                usr_lib_dir = f"/usr/lib/{pat_subdir}"
                setup_script.append(
                    f'  if compgen -G "{src_dirs[idx]}/lib{pat_subdir}.so*" >/dev/null; then')
                setup_script.append(f"    mkdir -p {src_dir} && chmod 0755 {src_dir}")
                setup_script.append(f"    ln -s $libs {src_dir}/. 2>/dev/null")
                setup_script.append(
                    f'  elif compgen -G "/usr/lib/lib{pat_subdir}.so*" >/dev/null; then')
                setup_script.append(f"    mkdir -p {usr_lib_dir} && chmod 0755 {usr_lib_dir}")
                setup_script.append(f"    ln -s $libs {usr_lib_dir}/. 2>/dev/null")
                setup_script.append("  fi")
            setup_script.append("fi")
        ld_lib_path.append(target_lib_dir)
    # add libraries to LD_LIBRARY_PATH rather than adding to system /etc/ld.so.conf in the
    # container since the system ldconfig cache may go out of sync with latter due to `ldconfig`
    # invocation on another container having the same shared root but with disabled NVIDIA support
    if ld_lib_path:
        # this assumes that LD_LIBRARY_PATH is not touched anywhere else, so NVIDIA will not
        # work if user explicitly overrides LD_LIBRARY_PATH in the [env] section
        add_env_option(docker_args, "LD_LIBRARY_PATH", os.pathsep.join(ld_lib_path))
    return setup_script


def _add_nvidia_bin_links(mount_bin_dirs: list[str], script: list[str]) -> None:
    """
    Add `bash` code to given script contents to create links to NVIDIA programs in `/usr/local/bin`
    inside the container.

    :param mount_bin_dirs: target directories where host's directories having NVIDIA programs
                           will be mounted
    :param script: the `bash` script contents as a list of string to which the new code is appended
    """
    script.append("# setup binaries")
    for mount_bin_dir in mount_bin_dirs:
        for pat in _NVIDIA_BIN_PATTERNS:
            script.append(f'bins="$(compgen -G "{mount_bin_dir}/{pat}")"')
            script.append('if [ "$?" -eq 0 ]; then ln -sf $bins /usr/local/bin/. 2>/dev/null; fi')


def _process_nvidia_data_files(docker_args: list[str], script: list[str],
                               mount_data_dir_prefix: str) -> None:
    """
    Add `bash` code to given script contents to create symlinks to NVIDIA data files mounted
    from the host environment.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    :param script: the `bash` script contents as a list of string to which the new code is appended
    :param mount_data_dir_prefix: the prefix of the destination directories where the host
                                  data directories have to be mounted
    """
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
            add_mount_option(docker_args, data_dir, mount_data_dir, "ro")
            nvidia_data_dirs.add(data_dir)
            path_dir = os.path.dirname(path)
            script.append(f"mkdir -p {path_dir} && chmod 0755 {path_dir} && \\")
            if path_is_dir:
                # links for data directories need to be in the same location as original
                script.append(f"  rm -rf {path} && ln -s {mount_data_dir} {path}")
            else:
                # assume that files inside other directories have the pattern "*nvidia*",
                # so the code avoids hard-coding fully resolved patterns to deal with
                # a case when the data file name changes after driver upgrade
                script.append(f"  ln -sf {mount_data_dir}/*nvidia* {path_dir}/. 2>/dev/null")
