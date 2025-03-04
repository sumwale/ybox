"""
Show detailed information of installed or repository packages in an active ybox container.
"""

import argparse
import sys
from configparser import SectionProxy

from ybox.cmd import PkgMgr, page_command
from ybox.config import StaticConfiguration


def info_packages(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                  conf: StaticConfiguration) -> int:
    """
    Show detailed information of an installed or repository package(s).

    :param args: arguments having `packages` and all other attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :return: integer exit status of info command where 0 represents success
    """
    quiet_flag = pkgmgr[PkgMgr.QUIET_DETAILS_FLAG.value] if args.quiet else ""
    packages: list[str] = args.packages
    info_cmd = pkgmgr[PkgMgr.INFO_ALL.value] if args.all else pkgmgr[PkgMgr.INFO.value]
    info_cmd = info_cmd.format(quiet=quiet_flag, packages=" ".join(packages))
    docker_args = [docker_cmd, "exec"]
    if sys.stdout.isatty():  # don't act as a terminal if it is being redirected
        docker_args.append("-it")
    docker_args.extend([conf.box_name, "/bin/bash", "-c", info_cmd])
    # empty pager argument is a valid one and indicates no pagination, hence the `is None` check
    pager: str = args.pager if args.pager is not None else conf.pager
    return page_command(docker_args, pager, error_msg="SKIP")
