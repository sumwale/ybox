"""
Methods for uninstalling package uninstallation on a running zbox container.
"""

import argparse
from configparser import SectionProxy
from pathlib import Path

from zbox.cmd import PkgMgr, run_command
from zbox.config import StaticConfiguration
from zbox.print import print_info, print_warn
from zbox.state import RuntimeConfiguration, ZboxStateManagement


def uninstall_package(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                      conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                      state: ZboxStateManagement) -> int:
    """
    Uninstall package specified by `args.package` on a zbox container with given docker/podman
    command. Additional flags honored are `args.quiet` to bypass user confirmation during
    uninstall, `args.purge` to remove everything related to the package including system
    configuration files and/or data files, `args.remove_deps` to remove all orphaned
    dependencies of the package (including required and optional dependencies).

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `pkgmgr` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the docker/podman executable to use
    :param conf: the `StaticConfiguration` of the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of the `ZboxStateManagement` class having the state of all zboxes

    :return: integer exit status of uninstall command where 0 represents success
    """
    package: str = args.package
    quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value] if args.quiet else ""
    purge_flag = pkgmgr[PkgMgr.PURGE_FLAG.value] if args.purge else ""
    remove_deps_flag = pkgmgr[PkgMgr.REMOVE_DEPS_FLAG.value] if args.remove_deps else ""
    uninstall_cmd = pkgmgr[PkgMgr.UNINSTALL.value].format(quiet=quiet_flag, purge=purge_flag,
                                                          remove_deps=remove_deps_flag)
    info_cmd = pkgmgr[PkgMgr.INFO.value]
    opt_deps: list[str] = []
    if remove_deps_flag:
        # more stuff can be added to the `type` field in the future, hence the '%' wildcards
        package_type = f"%{state.optional_package_type(package)}%"
        # package may be an orphan one sharing the same root directory, so search by shared_root
        # if applicable
        if runtime_conf.shared_root:
            opt_deps = state.get_packages(shared_root=runtime_conf.shared_root,
                                          package_type=package_type)
        else:
            opt_deps = state.get_packages(conf.box_name, package_type=package_type)

    code = _uninstall_package(package, uninstall_cmd, info_cmd, docker_cmd, conf, runtime_conf,
                              state)
    for opt_dep in opt_deps:
        _uninstall_package(opt_dep, uninstall_cmd, info_cmd, docker_cmd, conf, runtime_conf,
                           state, dep_msg="dependency ")
    return code


def _uninstall_package(package: str, uninstall_cmd: str, info_cmd: str, docker_cmd: str,
                       conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                       state: ZboxStateManagement, dep_msg: str = "") -> int:
    info_out = run_command([docker_cmd, "exec", conf.box_name, "/bin/bash", "-c",
                            f"{info_cmd} {package}"], capture_output=True,
                           exit_on_error=False, error_msg="SKIP")
    if isinstance(info_out, str):
        print_info(f"Uninstalling {dep_msg}'{package}' from '{conf.box_name}'")
        code = int(run_command([docker_cmd, "exec", "-it", conf.box_name, "/bin/bash", "-c",
                                f"{uninstall_cmd} {package}"], exit_on_error=False,
                               error_msg=f"uninstalling '{package}'"))
    else:
        code = int(info_out)
    for file in state.unregister_package(conf.box_name, package, runtime_conf.shared_root):
        print_warn(f"Removing local wrapper {file}")
        Path(file).unlink(missing_ok=True)
    return code
