"""
Mark a package as a dependency or as explicitly installed.
"""

import argparse
from configparser import SectionProxy

from ybox.cmd import PkgMgr, build_shell_command, run_command
from ybox.config import StaticConfiguration
from ybox.print import print_error, print_info
from ybox.state import (CopyType, DependencyType, RuntimeConfiguration,
                        YboxStateManagement)
from ybox.util import check_package


def mark_package(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                 conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                 state: YboxStateManagement) -> int:
    """
    Mark a package as a dependency of another package or an explicitly installed one.

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :return: integer exit status of mark package command where 0 represents success
    """
    mark_explicit: bool = args.explicit
    mark_dependency_of: str = args.dependency_of or ""
    if not mark_explicit ^ bool(mark_dependency_of):
        print_error("ybox-pkg mark: exactly one of -e or -d option must be specified "
                    f"(explicit={mark_explicit}, dependency-of={mark_dependency_of})")
        return 1
    # check that the package(s) are installed and replace with actual installed name
    check_cmd = pkgmgr[PkgMgr.CHECK_INSTALL.value]
    all_packages = [str(args.package)]
    if mark_dependency_of:
        all_packages.insert(0, mark_dependency_of)  # keep the non-dependent package at the front
    for idx, package in enumerate(all_packages):
        code, inst_pkgs = check_package(docker_cmd, check_cmd, package, conf.box_name)
        if code != 0:
            print_error(f"Package '{package}' is not installed in container '{conf.box_name}'")
            return 1
        all_packages[idx] = inst_pkgs[0]
    # make entries in the state database if the packages are not present
    package = all_packages[0]
    state.register_package(conf.box_name, package, [], CopyType(0), {},
                           runtime_conf.shared_root, None, "", skip_if_exists=True)
    if mark_dependency_of:
        # currently "optional" is the only supported dependency type
        print_info(f"Marking '{all_packages[1]}' as an optional dependency of '{package}'")
        state.register_package(conf.box_name, all_packages[1], [], CopyType(0), {},
                               runtime_conf.shared_root, dep_type=DependencyType.OPTIONAL,
                               dep_of=package, skip_if_exists=True)
        # the package may or may not be a dependency in the underlying packaging, so don't mark
        # at the package manager level which may cause the package to be orphaned and auto-removed
    else:
        print_info(f"Marking '{package}' as explicitly installed")
        # remove any dependency entries for this package to mark it as explicitly installed
        state.unregister_dependency(conf.box_name, "%", package)
        # also mark as explicitly installed using the underlying package manager
        mark_cmd = pkgmgr[PkgMgr.MARK_EXPLICIT.value]
        return int(run_command(build_shell_command(
            docker_cmd, conf.box_name, mark_cmd.format(package=package)), exit_on_error=False,
            error_msg=f"marking '{package}' as explicitly installed"))
    return 0
