"""
Methods for uninstalling package uninstallation on an active ybox container.
"""

import argparse
from configparser import SectionProxy
from pathlib import Path

from ybox.cmd import PkgMgr, run_command
from ybox.config import StaticConfiguration
from ybox.print import print_info, print_warn
from ybox.state import RuntimeConfiguration, YboxStateManagement
from ybox.util import check_installed_package


def uninstall_package(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                      conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                      state: YboxStateManagement) -> int:
    """
    Uninstall package specified by `args.package` on a ybox container with given docker/podman
    command. Additional flags honored are `args.quiet` to bypass user confirmation during
    uninstall, `args.keep_config_files` to keep the system configuration and/or data files
    of the package, `args.skip_deps` to skip removal of all orphaned dependencies of the package
    (including required and optional dependencies).

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `pkgmgr` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the docker/podman executable to use
    :param conf: the `StaticConfiguration` of the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of the `YboxStateManagement` class having the state of all yboxes

    :return: integer exit status of uninstall command where 0 represents success
    """
    package = str(args.package)
    quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value] if args.quiet else ""
    purge_flag = "" if args.keep_config_files else pkgmgr[PkgMgr.PURGE_FLAG.value]
    remove_deps_flag = "" if args.skip_deps else pkgmgr[PkgMgr.REMOVE_DEPS_FLAG.value]
    uninstall_cmd = pkgmgr[PkgMgr.UNINSTALL.value].format(quiet=quiet_flag, purge=purge_flag,
                                                          remove_deps=remove_deps_flag)
    check_cmd = pkgmgr[PkgMgr.INFO.value]
    opt_deps: list[str] = []
    if remove_deps_flag:
        # TODO: this doesn't take care of the case when multiple packages have the same opt-dep
        # more stuff can be added to the `type` field in the future, hence the '%' wildcards
        package_type = f"%{state.optional_package_type(package)}%"
        # package may be an orphan one sharing the same root directory, so search by shared_root
        # if applicable
        if runtime_conf.shared_root:
            opt_deps = state.get_packages(shared_root=runtime_conf.shared_root,
                                          package_type=package_type)
        else:
            opt_deps = state.get_packages(conf.box_name, package_type=package_type)

    if (code := _uninstall_package(package, uninstall_cmd, check_cmd, docker_cmd, conf,
                                   runtime_conf, state)) == 0:
        for opt_dep in opt_deps:
            _uninstall_package(opt_dep, uninstall_cmd, check_cmd, docker_cmd, conf, runtime_conf,
                               state, dep_msg="dependency ")
    return code


def _uninstall_package(package: str, uninstall_cmd: str, check_cmd: str, docker_cmd: str,
                       conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                       state: YboxStateManagement, dep_msg: str = "") -> int:
    code = check_installed_package(docker_cmd, check_cmd, package, conf.box_name)
    if code == 0:
        print_info(f"Uninstalling {dep_msg}'{package}' from '{conf.box_name}'")
        code = int(run_command([docker_cmd, "exec", "-it", conf.box_name, "/bin/bash", "-c",
                                f"{uninstall_cmd} {package}"], exit_on_error=False,
                               error_msg=f"uninstalling '{package}'"))
    else:
        code = 0  # go ahead with removal from local state and wrappers if present
    if code == 0:
        for file in state.unregister_package(conf.box_name, package, runtime_conf.shared_root):
            print_warn(f"Removing local wrapper {file}")
            Path(file).unlink(missing_ok=True)
    return code
