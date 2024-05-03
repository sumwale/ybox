"""
Methods for searching packages in the repositories matching given search terms.
"""

import argparse
import sys
from configparser import SectionProxy

from zbox.cmd import PkgMgr, run_command
from zbox.config import StaticConfiguration
from zbox.state import RuntimeConfiguration, ZboxStateManagement


# noinspection PyUnusedLocal
def search_packages(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                    conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                    state: ZboxStateManagement) -> int:
    """
    Uninstall package specified by `args.package` on a zbox container with given docker/podman
    command. Additional flags honored are `args.quiet` to bypass user confirmation during
    uninstall, `args.keep_config_files` to keep the system configuration and/or data files
    of the package, `args.skip_deps` to skip removal of all orphaned dependencies of the package
    (including required and optional dependencies).

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `pkgmgr` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the docker/podman executable to use
    :param conf: the `StaticConfiguration` of the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of the `ZboxStateManagement` class having the state of all zboxes

    :return: integer exit status of uninstall command where 0 represents success
    """
    quiet_flag = pkgmgr[PkgMgr.SEARCH_QUIET_FLAG.value] if args.quiet else ""
    official = pkgmgr[PkgMgr.SEARCH_OFFICIAL_FLAG.value] if args.official else ""
    search_terms: list[str] = args.search  # there will be at least one search term in the list
    search = pkgmgr[PkgMgr.SEARCH_FULL.value] if args.full else pkgmgr[PkgMgr.SEARCH.value]
    # quote the search terms for bash to properly see the full arguments if they contain spaces
    # or other special characters
    search_cmd = search.format(quiet=quiet_flag, official=official,
                               search="'" + "' '".join(search_terms) + "'")
    docker_args = [docker_cmd, "exec"]
    if sys.stdout.isatty():  # don't act as a terminal if it is being redirected
        docker_args.append("-it")
    docker_args.extend([conf.box_name, "/bin/bash", "-c", search_cmd])
    return int(run_command(docker_args, exit_on_error=False, error_msg="searching repositories"))
