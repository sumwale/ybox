"""
Clean package cache and related intermediate files of an active ybox container.
"""

import argparse
from configparser import SectionProxy

from ybox.cmd import PkgMgr, build_shell_command, run_command
from ybox.config import StaticConfiguration
from ybox.print import print_info


def clean_cache(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                conf: StaticConfiguration) -> int:
    """
    Clean package cache and related intermediate files.

    :param args: arguments having `quiet` and all other attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :return: integer exit status of clean command where 0 represents success
    """
    print_info(f"Cleaning package cache in container '{conf.box_name}'")
    clean_cmd = pkgmgr[PkgMgr.CLEAN_QUIET.value] if args.quiet else pkgmgr[PkgMgr.CLEAN.value]
    return int(run_command(build_shell_command(docker_cmd, conf.box_name, clean_cmd),
                           exit_on_error=False, error_msg="cleaning package cache"))
