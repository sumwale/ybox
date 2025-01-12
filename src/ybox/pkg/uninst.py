"""
Methods for uninstalling package uninstallation on an active ybox container.
"""

import argparse
from configparser import SectionProxy

from ybox.cmd import PkgMgr, build_shell_command, run_command
from ybox.config import StaticConfiguration
from ybox.print import print_error, print_info, print_notice
from ybox.state import RuntimeConfiguration, YboxStateManagement
from ybox.util import check_package, select_item_from_menu


def uninstall_package(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                      conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                      state: YboxStateManagement) -> int:
    """
    Uninstall package specified by `args.package` on a ybox container with given podman/docker
    command. Additional flags honored are `args.quiet` to bypass user confirmation during
    uninstall, `args.keep_config_files` to keep the system configuration and/or data files
    of the package, `args.skip_deps` to skip removal of all orphaned dependencies of the package
    (including required and optional dependencies).

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :return: integer exit status of uninstall command where 0 represents success
    """
    package: str = args.package
    quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value] if args.quiet else ""
    purge_flag = "" if args.keep_config_files else pkgmgr[PkgMgr.PURGE_FLAG.value]
    remove_deps_flag = "" if args.skip_deps else pkgmgr[PkgMgr.REMOVE_DEPS_FLAG.value]
    uninstall_cmd = pkgmgr[PkgMgr.UNINSTALL.value].format(
        quiet=quiet_flag, purge=purge_flag, remove_deps=remove_deps_flag, package="{package}")
    check_cmd = pkgmgr[PkgMgr.CHECK_INSTALL.value]
    return _uninstall_package(package, args.skip_deps, uninstall_cmd, check_cmd, docker_cmd, conf,
                              runtime_conf, state)


def _uninstall_package(package: str, skip_deps: bool, uninstall_cmd: str, check_cmd: str,
                       docker_cmd: str, conf: StaticConfiguration,
                       runtime_conf: RuntimeConfiguration, state: YboxStateManagement,
                       dep_msg: str = "") -> int:
    """
    Real workhorse of :func:`uninstall_package` that uninstalls given package on a ybox container
    with given podman/docker command.

    :param package: the package to be uninstalled
    :param skip_deps: true if orphaned dependencies of the package should not be uninstalled
    :param uninstall_cmd: fully formed uninstallation command from the distribution's `distro.ini`
    :param check_cmd: command to check for existence of the package returning the resolved name
                      as read from distribution's `distro.ini`; this should have {package}
                      placeholder in the string which will be resolved before execution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :param dep_msg: if this is invoked for uninstalling a dependency then the string "dependency "
                    to display in messages, defaults to ""
    :return: exit code of the underlying package manager command run using podman/docker
    """
    installed = False
    code, inst_packages = check_package(docker_cmd, check_cmd, package, conf.box_name)
    if code == 0:
        installed = True
        if len(inst_packages) > 1:
            print_notice(f"Multiple packages found for '{package}', select one to uninstall")
            if selected_pkg := select_item_from_menu(inst_packages):
                package = selected_pkg
            else:
                return 1
        else:
            package = inst_packages[0]
        print_info(f"Uninstalling {dep_msg}'{package}' from '{conf.box_name}'")
        code = int(run_command(build_shell_command(
            docker_cmd, conf.box_name, uninstall_cmd.format(package=package)),
            exit_on_error=False, error_msg=f"uninstalling '{package}'"))
    elif not dep_msg:  # dependency may have been uninstalled in original package uninstallation
        print_error(f"Package '{package}' is not installed in container '{conf.box_name}'")
    # go ahead with removal from local state and wrappers, even if package was not installed
    if code == 0 or not installed:
        orphans = state.unregister_package(conf.box_name, package, runtime_conf.shared_root)
        if not skip_deps and orphans:
            print_info(f"Uninstalling orphaned dependencies of '{package}' {list(orphans.keys())}")
            for opt_dep in orphans:
                _uninstall_package(opt_dep, skip_deps, uninstall_cmd, check_cmd, docker_cmd, conf,
                                   runtime_conf, state, dep_msg="dependency ")
    return code
