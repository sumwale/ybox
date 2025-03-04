"""
List packages or package files on an active ybox container.
"""

import argparse
import re
import sys
from configparser import SectionProxy
from typing import Callable

from ybox.cmd import PkgMgr, page_command
from ybox.config import Consts, StaticConfiguration
from ybox.print import fgcolor as fg
from ybox.print import print_warn
from ybox.state import RuntimeConfiguration, YboxStateManagement
from ybox.util import FormatTable


def list_packages(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                  conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                  state: YboxStateManagement) -> int:
    """
    List packages installed in a container including those not managed by `ybox-pkg`, if required.
    Some package details can also be listed like the version and whether a package has been
    installed as a dependency or is a top-level package.

    When multiple containers share the same root directory, then listing all packages will include
    those installed from other containers, if any.

    :param args: arguments having all attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :return: integer exit status of list packages command where 0 represents success
    """
    plain_sep: str = args.plain_separator
    separator = plain_sep or Consts.default_field_separator()
    if args.os_pkgs:
        # package list and details will all be fetched using distribution's package manager
        if args.verbose:
            list_cmd = pkgmgr[PkgMgr.LIST_ALL_LONG.value] if args.all else pkgmgr[
                PkgMgr.LIST_LONG.value]
        else:
            list_cmd = pkgmgr[PkgMgr.LIST_ALL.value] if args.all else pkgmgr[PkgMgr.LIST.value]
        list_cmd = list_cmd.format(packages="", separator=separator)
        if shared_containers := state.get_other_shared_containers(conf.box_name,
                                                                  runtime_conf.shared_root):
            print_warn("Package listing will include packages from other containers sharing the "
                       f"same root directory: {', '.join(shared_containers)}", file=sys.stderr)
    else:
        # package list will be fetched from the state database while the details, if required,
        # will be fetched using the distribution's package manager
        dependency_type = ".*" if args.all else ""
        packages = " ".join(state.get_packages(conf.box_name, dependency_type=dependency_type))
        if not packages:
            return 0
        # TODO: optional dependencies from state database should also be shown since those
        # can be different from the package manager
        list_cmd = pkgmgr[PkgMgr.LIST_ALL_LONG.value] if args.verbose else pkgmgr[
            PkgMgr.LIST_ALL.value]
        list_cmd = list_cmd.format(packages=packages, separator=separator)

    docker_args = [docker_cmd, "exec"]
    if sys.stdout.isatty():  # don't act as a terminal if it is being redirected
        docker_args.append("-it")
    docker_args.extend([conf.box_name, "/bin/bash", "-c", list_cmd])
    # empty pager argument is a valid one and indicates no pagination, hence the `is None` check
    pager: str = (args.pager or "") if args.pager is not None or plain_sep else conf.pager
    headers = ["Name", "Version", "Dependency Of (req,opt)",
               "Description"] if args.verbose else ["Name", "Version"]
    transform = None if plain_sep else _build_table_transform(args, separator, headers)
    header = plain_sep.join(headers) + "\n" if plain_sep else ""
    return page_command(docker_args, pager, "listing packages", transform, header)


def _build_table_transform(args: argparse.Namespace, separator: str,
                           headers: list[str]) -> Callable[[str], str]:
    """
    Return a transformation function that takes the output of the underlying package manager
    (invoked using podman/docker exec) and returns a string of table format layout appropriate
    for display on a terminal.

    :param args: the parsed arguments passed to the invoking script
    :param separator: the separator used between the fields
    :param headers: list of header strings to use for the columns
    :return: a transformation function that takes input string having the output from package
             manager and returns a string where the fields are formatted as a table appropriate
             for display in a terminal
    """
    def as_table(s: str) -> str:
        """
        Format output from the package manager having <name> and <version> fields as a table
        string for display in a terminal.
        """
        table = (line.split(separator, maxsplit=1) for line in s.splitlines())
        colors = (fg.lightgray, fg.orange)
        # outline formats like 'rounded_outline' would be preferable, but unfortunately they
        # are broken for multiline values, hence using the relatively better looking format
        # from the non-broken ones
        return FormatTable(table, headers, colors, "psql", (1.0, 1.0)).show()

    def as_long_table(s: str) -> str:
        """
        Format output from the package manager having <name>, <version>, <dependency of>
        and <description> fields as a table string for display in a terminal.
        """
        dep_of_idx = 2
        # add color to "Dependency Of" header to indicate the color scheme used in values
        headers[dep_of_idx] = f"Dependency Of ({fg.purple}req {fg.cyan}opt{fg.reset})"
        colors = (fg.lightgray, fg.orange, fg.reset, fg.blue)
        table_fmt = FormatTable((), headers, colors, "rounded_grid", (2.0, 2.0, 3.0, 3.0))
        # build the table data which uses the "Dependency Of" column width to decide on how
        # to truncate the various "req" and "opt" dependency lists
        table_fmt.table = (_format_long_line(line, separator, table_fmt.max_col_widths[dep_of_idx],
                                             args.no_trunc) for line in s.splitlines())
        return table_fmt.show()

    return as_long_table if args.verbose else as_table


# regex that matches the values in the "Dependency Of" column
_DEP_OF_RE = re.compile(r"(req\((?P<req>[^)]+)\))?,?(opt\((?P<opt>.+)\))?")


def _format_long_line(line: str, separator: str, dep_of_width: int,
                      no_trunc: bool) -> tuple[str, str, str, str]:
    """
    Format the `Dependency Of` column to include the required and optional dependencies while the
    other three fields are returned as is after extraction from the given `line`.

    :param line: a line of output from the package manager which is expected to be of the form:
                 <name>{separator}<version>{separator}<dependency of>{separator}<description>
    :param separator: the separator used between the fields
    :param dep_of_width: the final calculated display width of the "Dependency Of" column
    :param no_trunc: if True then do not truncate the 'Dependency Of' column value
    :return: tuple of formatted (<name>, <version>, <dependency of>, <description>) fields
    """
    name, version, dep_of, description = line.split(separator, maxsplit=3)
    # replace literal "\n" with newline
    description = description.replace(r"\n", "\n")
    if dep_of and (dep_of_match := _DEP_OF_RE.fullmatch(dep_of)):
        dep_of_dict = dep_of_match.groupdict()
        req_by = dep_of_dict.get("req") or ""
        opt_for = dep_of_dict.get("opt") or ""
        # description is not trimmed and is shown multi-line, so use its size as an upper limit
        if not no_trunc and len(dep_of) > (max_width := max(dep_of_width, len(description))):
            trim_factor = (len(dep_of) - max_width) / float(len(req_by) + len(opt_for))
            if req_by:
                trim_size = int(trim_factor * len(req_by) + 0.5)  # floor to nearest int
                req_by = req_by[:max(0, len(req_by) - trim_size - 3)] + "..."
            if opt_for:
                trim_size = int(trim_factor * len(opt_for) + 0.5)  # floor to nearest int
                opt_for = opt_for[:max(0, len(opt_for) - trim_size - 3)] + "..."
        dep_of_parts: list[str] = []
        if req_by:
            dep_of_parts.extend((fg.purple, "req(", req_by, ")", fg.reset))
        if opt_for:
            if req_by:
                dep_of_parts.append(" ")
            dep_of_parts.extend((fg.cyan, "opt(", opt_for, ")", fg.reset))
        return name, version, "".join(dep_of_parts), description
    return name, version, dep_of, description


def list_files(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
               conf: StaticConfiguration) -> int:
    """
    List the files of a package installed in a container including those not managed by `ybox-pkg`.

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :return: integer exit status of list package files command where 0 represents success
    """
    package: str = args.package
    list_cmd = pkgmgr[PkgMgr.LIST_FILES.value]
    docker_args = [docker_cmd, "exec"]
    if sys.stdout.isatty():  # don't act as a terminal if it is being redirected
        docker_args.append("-it")
    docker_args.extend([conf.box_name, "/bin/bash", "-c", list_cmd.format(package=package)])
    # empty pager argument is a valid one and indicates no pagination, hence the `is None` check
    pager: str = args.pager if args.pager is not None else conf.pager
    return page_command(docker_args, pager, error_msg=f"listing files of '{package}'")
