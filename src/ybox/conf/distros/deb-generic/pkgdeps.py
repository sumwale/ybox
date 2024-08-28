"""
Show the optional dependencies for a package that may be in deb package repositories.
The output is in the format:

{header}
{prefix}<name>{separator}<level>{separator}<installed>{separator}<description>

where:
 * <name>: name of the optional dependency
 * <level>: level of the dependency i.e. 1 for direct dependency, 2 for dependency of dependency
            and so on; resolution of level > 2 is not required since caller currently ignores those
 * <installed>: true if the dependency already installed and false otherwise
"""

import re
import sys
from collections import defaultdict
from typing import Union

from ybox.cmd import run_command
from ybox.print import print_error, print_notice
from ybox.util import parse_opt_deps_args

# regex pattern for package name in Recommends or Suggests fields
_PKG_NAME_RE = re.compile(r"\s*([^\s,|(]*)")


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
        for key, val in opt_deps.items():
            desc, level, installed = val
            # columns below are expected by ybox-pkg
            print(f"{prefix}{key}{sep}{level}{sep}{installed}{sep}{desc}")


def find_opt_deps(package: str, max_level: int) -> dict[str, tuple[str, int, bool]]:
    """
    Find the optional dependencies of a package till the given `level`. Here `Recommends` packages
    are treated as level 1 while `Suggests` are treated as level 2. Higher levels than 2 will fail.

    The result is returned as a dictionary having package name as the key with a tuple having its
    description, the level it was found and a boolean indicating whether the package is already
    installed or not.

    :param package: name of the package whose optional dependencies have to be searched
    :param max_level: the maximum level to which the search will extend
    :return: a dictionary which will be populated with the result having dependency name
             as the key with a tuple of description, level and whether package is installed
    """
    # Fetching optional dependencies consists of two steps:
    #  1. find the recomends and suggests fields of the package
    #  2. determine whether those packages are installed or not and obtain their descriptions
    # It also needs to take care of "|" dependencies where either of the two can be present,
    # so the check for installed packages needs to be done appropriately.
    line = ""
    # The map below stores all the available package names to their description.
    # This deliberately uses only the first line of the description for a multi-line description
    # since it is used for display of the optional dependencies menu where single line is enough.
    all_packages: defaultdict[str, str] = defaultdict(str)
    # the map below stores all the virtual packages to the list of the packages that provide them,
    # including the actual package itself which always provides itself
    provides_map: dict[str, Union[str, list[str]]] = {}
    # dictionary of required optional dependencies for the package to the tuple having
    # (description, level, installed); note that `Recommends` are level 1 while `Suggests`
    # are level 2 and recursion for levels is skipped)
    opt_deps: dict[str, tuple[str, int, bool]] = {}
    # dump all available packages, build a map of package name and its description, then pick the
    # package and its dependencies; the total map size with just those fields will be a few MB
    # while using `grep-aptavail` multiple times will be inefficient
    check_optional = False
    current_pkg = ""
    for line in str(run_command(["/usr/bin/apt-cache", "dumpavail"],
                                capture_output=True)).splitlines():
        if line.startswith("Package:"):
            if (current_pkg := line[len("Package:"):].strip()) == package:
                check_optional = True
            else:
                check_optional = False
                provides_map[current_pkg] = current_pkg
        elif check_optional:
            if line.startswith("Recommends:"):
                start_pos = len("Recommends:")
                while match := _PKG_NAME_RE.match(line, start_pos):
                    opt_deps[match.group(1)] = ("", 1, False)
                    start_pos = match.end()
            elif max_level > 1 and line.startswith("Suggests:"):
                start_pos = len("Suggests:")
                while match := _PKG_NAME_RE.match(line, start_pos):
                    opt_deps[match.group(1)] = ("", 2, False)
                    start_pos = match.end()
        else:
            if line.startswith("Provides:"):
                start_pos = len("Provides:")
                while match := _PKG_NAME_RE.match(line, start_pos):
                    provide = match.group(1)
                    if provides := provides_map.get(provide):
                        assert isinstance(provides, list)
                        provides.append(current_pkg)
                    else:
                        provides_map[provide] = [current_pkg]
                    start_pos = match.end()
            elif line.startswith("Description:"):
                assert all_packages[current_pkg]  # filled up by lambda of its declaration

    # fields = "-sRecommends,Suggests" if max_level > 1 else "-sRecommends"
    return opt_deps


if __name__ == "__main__":
    main()
