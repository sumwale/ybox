"""
Show detailed information of installed or repository packages in an active ybox container.
"""

import argparse
import sys
from configparser import SectionProxy

from ybox.cmd import PkgMgr, run_command
from ybox.config import StaticConfiguration
from ybox.state import RuntimeConfiguration, YboxStateManagement


# noinspection PyUnusedLocal
def info_packages(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                  conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                  state: YboxStateManagement) -> int:
    # pylint: disable=unused-argument
    """
    Show detailed information of an installed or repository package(s).

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `pkgmgr` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the docker/podman executable to use
    :param conf: the `StaticConfiguration` of the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of the `YboxStateManagement` class having the state of all yboxes

    :return: integer exit status of uninstall command where 0 represents success
    """
    quiet_flag = pkgmgr[PkgMgr.QUIET_DETAILS_FLAG.value] if args.quiet else ""
    packages: list[str] = args.packages
    info_cmd = pkgmgr[PkgMgr.INFO_ALL.value] if args.all else pkgmgr[PkgMgr.INFO.value]
    info_cmd = info_cmd.format(quiet=quiet_flag, packages=" ".join(packages))
    docker_args = [docker_cmd, "exec"]
    if sys.stdout.isatty():  # don't act as a terminal if it is being redirected
        docker_args.append("-it")
    docker_args.extend([conf.box_name, "/bin/bash", "-c", info_cmd])
    return int(run_command(docker_args, exit_on_error=False,
                           error_msg="showing information of package(s)"))
