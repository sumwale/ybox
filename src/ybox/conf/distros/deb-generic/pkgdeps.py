"""
Show the optional dependencies for a package that may be in deb package repositories.
The output is in the format:

{header}
{prefix}<name>{separator}<level>{separator}<order>{separator}<installed>{separator}<description>

where:
 * <name>: name of the optional dependency
 * <level>: level of the dependency i.e. 1 for direct dependency, 2 for dependency of dependency
            and so on; resolution of level > 2 is not required since caller currently ignores those
 * <order>: this is a simple counter assigned to the dependencies where the value itself is of no
            significance but if multiple dependencies have the same value then it means that they
            are ORed dependencies and only one of them need to be selected for installation
 * <installed>: true if the dependency already installed and false otherwise
 * <description>: detailed description of the dependency; it can contain literal \n to indicate
                  newlines in the description
"""

import os
import re
import sys
from enum import Enum
from typing import Callable, Iterable, Optional, Union

from ybox.cmd import parse_opt_deps_args, run_command
from ybox.print import print_error, print_notice

# regex pattern for package name in Recommends or Suggests fields
PKG_DEP_RE = re.compile(r"([,|]?)\s*([^\s,|(]+)\s*(\([^)]*\))?\s*")

PackageAlternate = tuple[str, str, Optional[list[str]]]


def main() -> None:
    """main entrypoint for `pkgdeps.py` script"""
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    """
    Main entrypoint of `pkgdeps.py` that takes a list of arguments which are usually the
    command-line arguments of the `main()` function.

    :param argv: arguments to the function (main function passes `sys.argv[1:]`)
    """
    args = parse_opt_deps_args(argv)
    if args.level > 2:
        print_error(f"pkgdeps.py does not support level > 2 (given = {args.level})")
        sys.exit(1)

    print_notice(f"Searching dependencies of '{args.package}' in deb repositories")
    sep: str = args.separator
    if opt_deps := find_opt_deps(args.package, args.level):
        if args.header:
            print(args.header)
        prefix = args.prefix
        for pkg, (desc, level, order, installed) in opt_deps.items():
            # columns below are expected by ybox-pkg
            print(f"{prefix}{pkg}{sep}{level}{sep}{order}{sep}{installed}{sep}{desc}")


class PkgDetail(Enum):
    """Enumerates the package fields used by `pkgdeps`"""
    PACKAGE = 1
    DESCRIPTION = 2
    PROVIDE = 3
    REQUIRED_DEP = 4
    OPTIONAL_DEP = 5


# noinspection PyUnusedLocal
def process_next_item(line: str, parse_line: Callable[[str], tuple[PkgDetail, str]],
                      parse_dep: Callable[[str], Iterable[tuple[str, str, Optional[str]]]],
                      installed: Callable[[str], bool], max_level: int,
                      pkg_details: dict[str, list[PackageAlternate]], level: int = 1) -> None:
    """
    Process the next item in the package details.
    """
    # pylint: disable=unused-argument
    print("TODO: SW: refactor so that it can be used by pkgdeps of deb-generic as well as arch")
    sys.exit(1)


def find_opt_deps(package: str, max_level: int) -> dict[str, tuple[str, int, int, bool]]:
    """
    Find the optional dependencies of a package till the given `level`. Here `Recommends` packages
    are treated as level 1 while `Suggests` are treated as level 2. Higher levels than 2 will fail.

    The result is returned as a dictionary having package name as the key with a tuple having its
    description, the level it was found, its `order` and a boolean indicating whether the package
    is already installed or not.

    :param package: name of the package whose optional dependencies have to be searched
    :param max_level: the maximum level to which the search will extend
    :return: a dictionary which will be populated with the result having dependency name
             as the key with a tuple of description, level, order and whether package is installed
    """
    # Fetching optional dependencies consists of two steps:
    #  1. find the recomends and suggests fields of the package
    #  2. determine whether those packages are installed or not and obtain their descriptions
    # It also needs to take care of "|" dependencies where either of the two can be present,
    # so the `order` needs to be set appropriately.

    # The map below stores all the available package names to their description.
    # This deliberately uses only the first line of the description for a multi-line description
    # since it is used for display of the optional dependencies menu where single line is enough.
    all_packages: dict[str, str] = {}
    # the map below stores all the virtual packages to the list of the packages that provide them,
    # including the actual package itself which always provides itself
    provides_map: dict[str, Union[str, list[str]]] = {}

    def insert_or_update_provides(provide: str, pkg: str) -> None:
        """insert a single value in provides map if not present, else change to list and append"""
        if provides := provides_map.get(provide):
            if isinstance(provides, list):
                provides.append(pkg)
            else:
                provides_map[provide] = [provides, pkg]
        else:
            provides_map[provide] = pkg

    # map of `Recommends` and `Suggests` dependencies to their level and order
    opt_dep_map: dict[str, tuple[int, int]] = {}
    # dump all available packages, build a map of package name and its description, then pick the
    # package and its dependencies; the total map size with just those fields will be a few MB
    # while using `grep-aptavail` multiple times will be inefficient
    check_optional = False
    current_pkg = ""
    # this counter is for assigning a counter to the dependencies which has a significance only
    # for ORed dependencies which will have the same order (and thus indicate to the higher level
    #   that only one of them should be installed)
    order = 0
    for line in str(run_command(["/usr/bin/apt-cache", "dumpavail"],
                                capture_output=True)).splitlines():
        if line.startswith("Package:"):
            if (current_pkg := line[len("Package:"):].strip()) == package:
                check_optional = True
            else:
                check_optional = False
                insert_or_update_provides(current_pkg, current_pkg)
        elif check_optional:
            # Note: version comparisons are not required here since all we need is the description
            # of the package. This assumes that the best package available for installation in the
            # repositories satisfies the version mentioned in the Recommends/Suggests dependencies,
            # but that may not be true in some rare cases in which case the installation of the
            # optional dependency will fail after user selects it.
            if line.startswith("Recommends:"):
                for match in PKG_DEP_RE.finditer(line, len("Recommends:")):
                    if match.group(1) != "|":  # ORed dependencies have the same `order`
                        order += 1
                    opt_dep_map[match.group(2)] = (1, order)
            elif max_level > 1 and line.startswith("Suggests:"):
                for match in PKG_DEP_RE.finditer(line, len("Suggests:")):
                    if match.group(1) != "|":  # ORed dependencies have the same `order`
                        order += 1
                    opt_dep_map[match.group(2)] = (2, order)
        else:
            if line.startswith("Provides:"):
                for match in PKG_DEP_RE.finditer(line, len("Provides:")):
                    insert_or_update_provides(match.group(2), current_pkg)
            elif line.startswith("Description:"):
                all_packages[current_pkg] = line[len("Description:"):].strip()

    if not opt_dep_map:
        return {}
    # get the system architecture to quickly check for existence of an installed package
    sys_arch = str(run_command(["/usr/bin/dpkg", "--print-architecture"],
                               capture_output=True)).strip()
    # list of required optional dependencies as a tuple (name, (description, level, order,
    #   installed)); note that `Recommends` are level 1 while `Suggests` are level 2 and recursion
    # for levels is skipped
    opt_deps: list[tuple[str, tuple[str, int, int, bool]]] = []
    # loop through the `opt_deps_map` and look them up in the `provides` map to get the actual
    # packages which will be inserted in `opt_deps` with their level and order while description
    # will be looked up from `all_packages` map
    last_installed_order = 0
    for dep, (level, order) in opt_dep_map.items():
        if provides := provides_map.get(dep):
            if isinstance(provides, str):
                provides = (provides,)
            for provide in provides:
                if provide == package:  # for the possible case of self-recommend/suggest
                    continue
                # for each `provide` check if its installed
                installed = os.path.exists(f"/var/lib/dpkg/info/{provide}.list") or os.path.exists(
                    f"/var/lib/dpkg/info/{provide}:{sys_arch}.list")
                # if there is an installed package, then remove the uninstalled packages in the
                # same order since one of them is already installed (installed ones are required
                #   for registeration as existing dependency by ybox-pkg, so they are still kept)
                if installed:
                    last_installed_order = order
                    # pop uninstalled ones in the same `order` which will be at the end since
                    # opt_dep_map iterator will be insertion order which is sorted by `order`;
                    # previous installed one in same `order` would have removed all uninstalled
                    # ones in that order that were before it, so don't need to check before it
                    while opt_deps and opt_deps[-1][1][2] == order and not opt_deps[-1][1][3]:
                        opt_deps.pop()
                elif order == last_installed_order:
                    continue
                opt_deps.append((provide, (all_packages[provide], level, order, installed)))

    # sort opt_deps by level and order and return
    opt_deps.sort(key=lambda x: (x[1][1], x[1][2]))
    return dict(opt_deps)


if __name__ == "__main__":
    main()
