"""
Show the optional dependencies for a package that may be in a pacman repository or the AUR.
The output is in the format:

{header}
{prefix}<name>{separator}<level>{separator}<order>{separator}<installed>{separator}<description>

where:
 * <name>: name of the optional dependency
 * <level>: level of the dependency i.e. 1 for direct dependency, 2 for dependency of dependency
            and so on; resolution of level > 2 is not required since caller currently ignores those
 * <order>: this is a simple counter assigned to the dependencies where the value itself is of no
            significance but if multiple dependencies have the same value then it means that they
            are ORed dependencies and only one of them should normlly be selected for installation
 * <installed>: true if the dependency already installed and false otherwise
 * <description>: detailed description of the dependency; it can contain literal \n to indicate
                  newlines in the description
"""

# TODO: SW: this is returning back installed packages too which should be skipped

import gzip
import os
import re
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Optional

import ijson  # type: ignore

from ybox.cmd import parse_opt_deps_args, run_command
from ybox.config import Consts
from ybox.print import print_error, print_notice, print_warn

_AUR_META_URL = "https://aur.archlinux.org/packages-meta-ext-v1.json.gz"
_PKG_CACHE_SUBDIR = os.path.basename(__file__).removesuffix(".py")
_AUR_META_CACHE_DIR = f"{os.path.expanduser('~/.cache')}/{_PKG_CACHE_SUBDIR}"
_AUR_META_FILE = f"{_AUR_META_CACHE_DIR}/packages-meta-ext-v1.json.gz"
# parallel download using aria2 is much faster on slower networks
_FETCH_AUR_META = f"/usr/bin/aria2c -x8 -j8 -s8 -k1M -d{_AUR_META_CACHE_DIR} {_AUR_META_URL}"
_REFRESH_AGE = 24.0 * 60 * 60  # consider AUR metadata file as stale after a day
_PACKAGE_NAME_RE = re.compile(r"^[\w@.+-]+")  # used to strip out version comparisons

# fields: name of original package, description, required dependencies, optional dependencies
PackageAlternate = tuple[str, str, list[str], list[str]]


def main() -> None:
    """main function for `pkgdeps.py` script"""
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    """
    Main entrypoint of `pkgdeps.py` that takes a list of arguments which are usually the
    command-line arguments of the `main()` function. Pass ["-h"]/["--help"] to see all the
    available arguments with help message for each.

    :param argv: arguments to the function (main function passes `sys.argv[1:]`)
    """
    args = parse_opt_deps_args(argv)

    print_notice(f"Searching dependencies of '{args.package}' in base Arch repositories")
    # first get the list of all installed packages to eliminate installed packages
    # (include their provides too)
    installed_packages = set(
        str(run_command(r"/usr/bin/expac %n\t%S", capture_output=True)).split())
    # next build a map of all packages in pacman database from their provides, dependencies and
    # optional dependencies; the map key will be original package name and their provides mapped
    # to a tuple having the name, description with list of required and optional dependencies
    sep: str = args.separator
    all_packages = build_pacman_db_map(sep)

    opt_deps: dict[str, tuple[str, int, bool]] = {}
    find_opt_deps(args.package, installed_packages, all_packages, opt_deps, args.level)
    # columns below are expected by ybox-pkg
    if opt_deps:
        if args.header:
            print(args.header)
        prefix = args.prefix
        for key, val in opt_deps.items():
            desc, level, installed = val
            print(f"{prefix}{key}{sep}{level}{sep}{installed}{sep}{desc}")


def build_pacman_db_map(sep: str) -> defaultdict[str, list[PackageAlternate]]:
    """
    Build a map of all packages in pacman repositories returning a `defaultdict` having name of
    package as the key with a list of `PackageAlternate` objects as values which captures
    the name, description, required depedencies and optional dependencies in the tuple.
    The first element element in the list is always the package itself while subsequent ones
    are all packages that provide the same package, if any.

    This is actually faster than querying the sync database multiple times (at least twice)
    using pacman/expac for the package and its optional dependencies since the sync databases are
    just a tarball of the packages that have to be read in entirety either way.

    :param sep: the separator string to use between the output fields of `expac`
    :return: a `defaultdict` having package names as keys with list of `PackageAlternate` values
    """
    arch_packages = defaultdict[str, list[PackageAlternate]](list[PackageAlternate])
    for package_list in str(run_command(f"/usr/bin/expac -S %n{sep}%S{sep}%E{sep}%o{sep}%d",
                                        capture_output=True)).splitlines():
        if not package_list:
            continue
        name, provides, required, optional, desc = package_list.split(sep)
        deps = _process_pkg_names(required.split()) if required else []
        opt_deps = _process_pkg_names(optional.split()) if optional else []
        # arch linux packages are always lower case which is enforced below for the map
        map_val = (name.lower(), desc, deps, opt_deps)
        arch_packages[map_val[0]].append(map_val)
        for provide in _process_pkg_names(provides.split()):
            arch_packages[provide].append(map_val)
    return arch_packages


def _process_pkg_names(pkgs: Optional[list[str]]) -> list[str]:
    """internal method to strip out versions from each package name of a list of package names"""
    return [m.group(0) for pkg in pkgs if (m := _PACKAGE_NAME_RE.match(pkg))] if pkgs else []


def refresh_aur_metadata(raise_error: bool) -> bool:
    """
    refresh AUR metadata having details on all available AUR packages which is refreshed if it
    is missing or older than 24 hours
    """
    os.makedirs(_AUR_META_CACHE_DIR, mode=Consts.default_directory_mode(), exist_ok=True)
    # fetch AUR metadata if not present or older than a day
    if (not os.access(_AUR_META_FILE, os.R_OK) or
            time.time() > os.path.getctime(_AUR_META_FILE) + _REFRESH_AGE):
        meta_file = Path(_AUR_META_FILE)
        meta_file.unlink(missing_ok=True)
        # delete any partial file in case of download failure
        if (code := int(run_command(_FETCH_AUR_META, exit_on_error=False))) != 0:
            meta_file.unlink(missing_ok=True)
            if raise_error:
                raise RuntimeError(f"Download of AUR metadata failed with exit code {code}")
            return False
    return True

# using ijson instead of the standard json because latter always loads the entire JSON in memory
# whereas only a few fields are required for the map, and hence using ijson is a bit faster as
# well as far less memory consuming


def build_aur_db_map(aur_packages: defaultdict[str, list[PackageAlternate]],
                     raise_error: bool) -> bool:
    """
    Like :func:`build_pacman_db_map` this will build a map of package names to a list of
    `PackageAlternate` objects which contains the name, description, required dependencies and
    optional dependencies of the package as well as any packages that provide this package.
    The result is added to the passed `aur_packages` argument which should be a `defaultdict`.

    This downloads the AUR metadata explicitly and builds the map from the downloaded file.
    The AUR metadata is refreshed if it is missing or older than 24 hours.
    The alternative of using paru/yay to dump information of all available packages is much much
    slower. Querying using paru/yay for virtual packages in AUR database does not work since they
    maintain just the names of AUR packages locally, so cannot just query the optional deps.

    :param aur_packages: a `defaultdict` which will be populated wih the package names as keys
                         and list of `PackageAlternate` objects as the values
    :param raise_error: if True, then raise an error if there was one while reading the AUR
                        metadata else the method will return a boolean indicating success/failure
    :return: True if `aur_packages` was successfully populated and False if there was an error
             in reading the fetched AUR metadata
    """
    try:
        with gzip.open(_AUR_META_FILE, mode="rb") as aur_meta:
            for package in ijson.items(aur_meta, "item", use_float=True):
                desc = package.get("Description") or ""
                deps = _process_pkg_names(package.get("Depends"))
                opt_deps = _process_pkg_names(package.get("OptDepends"))
                # arch linux packages are always lower case which is enforced below for the map
                map_val = (package.get("Name").lower(), desc, deps, opt_deps)
                aur_packages[map_val[0]].append(map_val)
                for provide in _process_pkg_names(package.get("Provides")):
                    aur_packages[provide].append(map_val)
        return True
    except (gzip.BadGzipFile, EOFError, zlib.error, ijson.JSONError):
        if raise_error:
            raise
        return False


def find_opt_deps(package: str, installed: set[str],
                  all_packages: defaultdict[str, list[PackageAlternate]],
                  opt_deps: dict[str, tuple[str, int, bool]], max_level: int,
                  level: int = 1) -> None:
    """
    Find and populate optional dependencies of a package till the given `level`. This will
    recursively keep finding optional dependencies of all required and optional dependencies till
    the `max_level` is not reached. For example, max_level=1 will obtain just the immediate
    optional dependencies, max_level=2 will go one level down and also obtain any optional
    dependencies of those as well as the required dependencies of the package, and so on.

    The result is populated in the given `opt_deps` argument which is a dictionary having
    package name as the key with a tuple having its description, the level it was found and
    a boolean indicating whether the package is already installed or not.

    :param package: name of the package whose optional dependencies have to be searched
    :param installed: a set of all installed packages in the system
    :param all_packages: a dictionary having all the available packages which includes those
                         in pacman as well as AUR repositories
    :param opt_deps: a dictionary which will be populated with the result having dependency name
                     as the key with a tuple of description, level and whether package is installed
    :param max_level: the maximum level to which the search will extend
    :param level: the current level of search which will terminate if it exceed the `max_level`,
                  defaults to 1 which should be what external callers should use while it will
                  be incremented in recursive calls
    """
    if level > max_level:
        return
    # arch linux names are always lower case though sometimes upper case parts can appear
    # in opt-depends field (e.g. 'hunspell-en_US' while package is 'hunspell-en_us')
    package = package.lower()
    # search all_packages to obtain the required and optional dependencies
    if not (alternates := all_packages.get(package)):
        if level == 1:
            print_notice(f"Searching dependencies of '{package}' in AUR")
            # fetch AUR metadata, populate into all_packages and try again
            # else if download fails or AUR metadata file is broken, then refresh it and try again
            if not refresh_aur_metadata(raise_error=False) or not build_aur_db_map(
                    all_packages, raise_error=False):
                os.unlink(_AUR_META_FILE)
                refresh_aur_metadata(raise_error=True)
                build_aur_db_map(all_packages, raise_error=True)
            alternates = all_packages.get(package)
    if not alternates:
        if level == 1:
            print_error(f"Package '{package}' not found")
            sys.exit(1)
        else:
            print_warn(f"Skipping unknown dependency '{package}'")
            return

    # choose the alternative with the same name else the first one
    (_, _, required, opts) = search_alternates(package, alternates)

    if opts:
        for pkg in opts:
            pkg = pkg.lower()
            if pkg in opt_deps:  # don't recurse on already encountered optional dependencies
                continue
            # lookup description
            dep_desc = ""
            if opt_dep := all_packages.get(pkg):
                dep_desc = search_alternates(pkg, opt_dep)[1]
            opt_deps[pkg] = (dep_desc, level, pkg in installed)
    if not required:
        return
    for pkg in required:
        if pkg not in installed:
            find_opt_deps(pkg, installed, all_packages, opt_deps, max_level, level + 1)


def search_alternates(package_name: str, alternates: list[PackageAlternate]) -> PackageAlternate:
    """
    Search for a package in the given list of `PackageAlternate` objects, else if the package
    is not found then the first element from the list is returned (which is the original package
      name as populated by :func:`build_pacman_db_map` and :func:`build_aur_db_map`)

    :param package_name: the package name to search
    :param alternates: the list of `PackageAlternate` objects which is to be searched
    :return: the `PackageAlternate` with matching package name or the first element in the
             `alternates` list if the package was not found
    """
    # choose the alternative with the same name else the first one
    for alternate in alternates:
        if alternate[0] == package_name:
            return alternate
    return alternates[0]


if __name__ == "__main__":
    main()
