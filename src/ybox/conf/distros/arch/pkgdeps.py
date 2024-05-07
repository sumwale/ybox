import argparse
import gzip
import os
import sys
import time
import zlib
from pathlib import Path
from typing import Optional, Tuple

import ijson  # type: ignore

from ybox.cmd import run_command
from ybox.print import print_error, print_notice, print_warn

_AUR_META_URL = "https://aur.archlinux.org/packages-meta-ext-v1.json.gz"
_PKG_CACHE_SUBDIR = os.path.basename(__file__).removesuffix(".py")
_AUR_META_CACHE_DIR = f"{os.path.expanduser('~/.cache')}/{_PKG_CACHE_SUBDIR}"
_AUR_META_FILE = f"{_AUR_META_CACHE_DIR}/packages-meta-ext-v1.json.gz"
# parallel download using aria2 is much faster on slower networks
_FETCH_AUR_META = f"/usr/bin/aria2c -x8 -j8 -s8 -k1M -d{_AUR_META_CACHE_DIR} {_AUR_META_URL}"
_REFRESH_AGE = 24.0 * 60 * 60  # consider AUR metadata file as stale after a day
_DEFAULT_SEP = "::::"  # something that does not appear in descriptions (at least so far)

# fields: name of original package, description, required dependencies, optional dependencies
PackageAlternate = Tuple[str, str, Optional[list[str]], Optional[list[str]]]


def main() -> None:
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        description="Recursively find optional dependencies of a package")
    parser.add_argument("-s", "--separator", type=str, default=_DEFAULT_SEP,
                        help="separator to use between the columns")
    parser.add_argument("-p", "--prefix", type=str, default="",
                        help="prefix string before each line of result")
    parser.add_argument("-H", "--header", type=str, default="",
                        help="header line to print before the results (without trailing newline)")
    parser.add_argument("-l", "--level", type=int, default=2,
                        help="maximum level to search for optional dependencies")
    parser.add_argument("package", type=str, help="name of the package")
    args = parser.parse_args(argv)

    # find optional dependencies of only the new packages that are going to be installed
    # i.e. the package and its new dependencies skipping the already installed dependencies,
    # otherwise the list can be too long and become pointless for the end-user

    print_notice(f"Searching dependencies of '{args.package}' in base Arch repositories")
    # first get the list of all installed packages to eliminate installed packages
    # (include their provides too)
    installed_packages = set(
        str(run_command(r"/usr/bin/expac %n\t%S", capture_output=True)).split())
    # next build a map of all packages in pacman database from their provides, dependencies and
    # optional dependencies; the map key will be original package name and their provides mapped
    # to a tuple having the name, description with list of required and optional dependencies
    all_packages: dict[str, list[PackageAlternate]] = {}
    sep = args.separator
    build_pacman_db_map(all_packages, sep)

    opt_deps: dict[str, Tuple[str, int, bool]] = {}
    find_opt_deps(args.package, installed_packages, all_packages, opt_deps, args.level)
    # columns below are expected by ybox-pkg
    if opt_deps:
        if args.header:
            print(args.header)
        prefix = args.prefix
        for key, val in opt_deps.items():
            desc, level, installed = val
            print(f"{prefix}{key}{sep}{desc}{sep}{level}{sep}{installed}")


def build_pacman_db_map(arch_packages: dict[str, list[PackageAlternate]], sep: str) -> None:
    for package_list in str(run_command(f"/usr/bin/expac -S %n{sep}%d{sep}%S{sep}%E{sep}%o",
                                        capture_output=True)).splitlines():
        if not package_list:
            continue
        name, desc, provides, required, optional = package_list.split(sep)
        deps = required.split() if required else None
        opt_deps = optional.split() if optional else None
        # arch linux packages are always lower case which is enforced below for the map
        map_val = (name.lower(), desc, deps, opt_deps)
        if existing := arch_packages.get(map_val[0]):
            existing.append(map_val)
        else:
            arch_packages[map_val[0]] = [map_val]
        for provide in provides.split():
            if existing := arch_packages.get(provide):
                existing.append(map_val)
            else:
                arch_packages[provide] = [map_val]


def refresh_aur_metadata() -> None:
    os.makedirs(_AUR_META_CACHE_DIR, mode=0o750, exist_ok=True)
    # fetch AUR metadata if not present or older than a day
    if (not os.access(_AUR_META_FILE, os.R_OK) or
            time.time() > os.path.getctime(_AUR_META_FILE) + _REFRESH_AGE):
        meta_file = Path(_AUR_META_FILE)
        meta_file.unlink(missing_ok=True)
        # delete any partial file in case of download failure
        if (code := int(run_command(_FETCH_AUR_META, exit_on_error=False))) != 0:
            meta_file.unlink(missing_ok=True)
            sys.exit(code)


# using ijson instead of the standard json because latter always loads the entire
# JSON in memory whereas here only a few fields are required
def build_aur_db_map(aur_packages: dict[str, list[PackageAlternate]], raise_error: bool) -> bool:
    try:
        with gzip.open(_AUR_META_FILE, mode="rt", encoding="utf-8") as aur_meta:
            for package in ijson.items(aur_meta, "item"):
                desc = package.get("Description")
                if not desc:
                    desc = ""
                deps = package.get("Depends")
                opt_deps = package.get("OptDepends")
                # arch linux packages are always lower case which is enforced below for the map
                map_val = (package.get("Name").lower(), desc, deps, opt_deps)
                if existing := aur_packages.get(map_val[0]):
                    existing.append(map_val)
                else:
                    aur_packages[map_val[0]] = [map_val]
                if provides := package.get("Provides"):
                    for provide in provides:
                        if existing := aur_packages.get(provide):
                            existing.append(map_val)
                        else:
                            aur_packages[provide] = [map_val]
        return True
    except (gzip.BadGzipFile, EOFError, zlib.error):
        if raise_error:
            raise
        return False


def find_opt_deps(package: str, installed: set[str],
                  all_packages: dict[str, list[PackageAlternate]],
                  opt_deps: dict[str, Tuple[str, int, bool]], max_level: int,
                  level: int = 1) -> None:
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
            refresh_aur_metadata()
            # if AUR metadata file is broken, then refresh it and try again
            if not build_aur_db_map(all_packages, raise_error=False):
                os.unlink(_AUR_META_FILE)
                refresh_aur_metadata()
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
            if pkg not in opt_deps:  # don't recurse on already encountered optional dependencies
                # lookup description
                dep_desc = ""
                pkg = pkg.lower()
                if opt_dep := all_packages.get(pkg):
                    dep_desc = search_alternates(pkg, opt_dep)[1]
                opt_deps[pkg] = (dep_desc, level, pkg in installed)
    if required:
        for pkg in required:
            if pkg not in installed:
                find_opt_deps(pkg, installed, all_packages, opt_deps, max_level, level + 1)


def search_alternates(package_name: str, alternates: list[PackageAlternate]) -> PackageAlternate:
    # choose the alternative with the same name else the first one
    for alternate in alternates:
        if alternate[0] == package_name:
            return alternate
    return alternates[0]


if __name__ == "__main__":
    main()
