"""
Clean package cache and related intermediate files of an active ybox container.
"""

import argparse
from configparser import SectionProxy

from ybox.cmd import PkgMgr, run_command
from ybox.config import StaticConfiguration
from ybox.state import RuntimeConfiguration, YboxStateManagement


# noinspection PyUnusedLocal
def clean_cache(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                state: YboxStateManagement) -> int:
    # pylint: disable=unused-argument
    """
    Clean package cache and related intermediate files.

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `pkgmgr` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the docker/podman executable to use
    :param conf: the `StaticConfiguration` of the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of the `YboxStateManagement` class having the state of all yboxes

    :return: integer exit status of clean command where 0 represents success
    """
    clean_cmd = pkgmgr[PkgMgr.CLEAN_QUIET.value] if args.quiet else pkgmgr[PkgMgr.CLEAN.value]
    return int(run_command([docker_cmd, "exec", "-it", conf.box_name, "/bin/bash", "-c",
                            clean_cmd], exit_on_error=False, error_msg="cleaning package cache"))
