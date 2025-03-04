"""
Methods for searching packages in the repositories matching given search terms.
"""

import argparse
import sys
from configparser import SectionProxy

from ybox.cmd import PkgMgr, page_command
from ybox.config import StaticConfiguration


def search_packages(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                    conf: StaticConfiguration) -> int:
    """
    Uninstall package specified by `args.package` on a ybox container with given podman/docker
    command. Additional flags honored are `args.quiet` to bypass user confirmation during
    uninstall, `args.keep_config_files` to keep the system configuration and/or data files
    of the package, `args.skip_deps` to skip removal of all orphaned dependencies of the package
    (including required and optional dependencies).

    :param args: arguments having `search` and all other attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :return: integer exit status of search command where 0 represents success
    """
    quiet_flag = pkgmgr[PkgMgr.QUIET_DETAILS_FLAG.value] if args.quiet else ""
    official = pkgmgr[PkgMgr.SEARCH_OFFICIAL_FLAG.value] if args.official else ""
    word_start = word_end = ""
    if args.word:
        word_start = pkgmgr[PkgMgr.SEARCH_WORD_START_FLAG.value]
        word_end = pkgmgr[PkgMgr.SEARCH_WORD_END_FLAG.value]
    search_terms: list[str] = args.search  # there will be at least one search term in the list
    search = pkgmgr[PkgMgr.SEARCH_ALL.value] if args.all else pkgmgr[PkgMgr.SEARCH.value]
    # quote the search terms for bash to properly see the full arguments if they contain spaces
    # or other special characters
    search_cmd = search.format(quiet=quiet_flag, official=official, word_start=word_start,
                               word_end=word_end, search="'" + "' '".join(search_terms) + "'")
    docker_args = [docker_cmd, "exec"]
    if sys.stdout.isatty():  # don't act as a terminal if it is being redirected
        docker_args.append("-it")
    docker_args.extend([conf.box_name, "/bin/bash", "-c", search_cmd])
    # empty pager argument is a valid one and indicates no pagination, hence the `is None` check
    pager: str = args.pager if args.pager is not None else conf.pager
    return page_command(docker_args, pager, error_msg="searching repositories")
