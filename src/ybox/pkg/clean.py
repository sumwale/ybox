"""
Clean package cache and related intermediate files of an active ybox container.
"""

import argparse
from configparser import SectionProxy

from ybox.cmd import (PkgMgr, build_shell_command, check_active_ybox,
                      run_command)
from ybox.config import StaticConfiguration
from ybox.print import print_info
from ybox.state import RuntimeConfiguration, YboxStateManagement


# noinspection PyUnusedLocal
def clean_cache(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                state: YboxStateManagement) -> int:
    # pylint: disable=unused-argument
    """
    Clean package cache and related intermediate files.

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :return: integer exit status of clean command where 0 represents success
    """
    clean_cmd = pkgmgr[PkgMgr.CLEAN.value] if args.ask else pkgmgr[PkgMgr.CLEAN_QUIET.value]
    # run clean for each container since it can involve actions that are container specific
    # apart from the generic ones for the shared root (e.g. AUR cache cleaning for Arch Linux)
    code = 0
    for container in state.get_containers(shared_root=runtime_conf.shared_root):
        if not check_active_ybox(docker_cmd, container):
            continue
        print_info(f"Cleaning package cache in container '{container}'")
        if (c := int(run_command(build_shell_command(docker_cmd, container, clean_cmd),
                                 exit_on_error=False, error_msg="cleaning package cache"))) != 0:
            code = c
        print()
    return code
