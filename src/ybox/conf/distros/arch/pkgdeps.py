"""
Implementation of the `ybox.resolve.DistributionPackages` abstract class for Arch Linux packages
with a main stub that uses `ybox.resolve.ResolvePackage` to print the optional dependencies of
given packages as expected by `ybox-pkg`.
"""

import gzip
import os
import re
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import ijson  # type: ignore
import pyalpm
from pyalpm import Handle

from ybox.cmd import run_command
from ybox.config import Consts
from ybox.print import print_notice, print_warn
from ybox.resolve import (DistributionPackages, Package, PackageCondition,
                          ResolvePackage)


class ArchPackages(DistributionPackages):

    _AUR_META_URL = "https://aur.archlinux.org/packages-meta-ext-v1.json.gz"
    _AUR_META_DIR = f"{os.path.expanduser('~/.cache')}/archresolve"
    _AUR_META_FILE = f"{_AUR_META_DIR}/packages-meta-ext-v1.json.gz"
    # parallel download using aria2 is much faster on slower networks
    _FETCH_AUR_META = f"/usr/bin/aria2c -x8 -j8 -s8 -k1M -d{_AUR_META_DIR} {_AUR_META_URL}"
    _REFRESH_AGE = 24.0 * 60 * 60  # consider AUR metadata file as stale after a day
    # split package name and its comparison against a version
    _PKG_COND_RE = re.compile(r"([^=<>!:]+)(([=<>!]+)(.*))?:*.*")

    def __init__(self):
        self._handle = Handle("/", "/var/lib/pacman")

    def _refresh_aur_metadata(self, raise_error: bool) -> bool:
        """
        Refresh AUR metadata having details on all available AUR packages which is refreshed if it
        is missing or older than 24 hours.
        """
        os.makedirs(self._AUR_META_DIR, mode=Consts.default_directory_mode(), exist_ok=True)
        # fetch AUR metadata if not present or older than a day
        if (not os.access(self._AUR_META_FILE, os.R_OK) or
                time.time() > os.path.getctime(self._AUR_META_FILE) + self._REFRESH_AGE):
            meta_file = Path(self._AUR_META_FILE)
            meta_file.unlink(missing_ok=True)
            # delete any partial file in case of download failure
            if (code := int(run_command(self._FETCH_AUR_META, exit_on_error=False))) != 0:
                meta_file.unlink(missing_ok=True)
                if raise_error:
                    raise RuntimeError(f"Download of AUR metadata failed with exit code {code}")
                return False
        return True

    def _populate_aur_packages(self, pkg_map: defaultdict[str, list[Package]],
                               raise_error: bool) -> bool:
        """
        This will build a list of `Package` objects for all packages present in the AUR.

        This uses the AUR metadata downloaded explicitly. The alternative of using paru/yay to dump
        information of all available packages is much much slower. Querying using paru/yay for
        virtual packages in AUR database does not work since they maintain just the names of AUR
        packages locally, so just cannot query the optional deps.

        This returns a `list` instead of a generator to deal with unexpected exceptions while
        reading/parsing the AUR metadata file in which case the caller can retry safely without
        having to worry about dealing with `Package` objects that may already have been processed
        by higher layers.

        :param raise_error: if True, then raise an error if there was one while reading the AUR
                            metadata else the method will return an empty list in case of failure
        :return list: list of `Package` objects corresponding to the AUR packages or empty if there
                      was an error in reading the fetched AUR metadata
        """
        try:
            with gzip.open(self._AUR_META_FILE, mode="rb") as aur_meta:
                # using ijson instead of the standard json because latter always loads the entire
                # JSON in memory whereas only a few fields are required for the list, and hence
                # using ijson is a bit faster as well as far less memory consuming
                for pkg in ijson.items(aur_meta, "item", use_float=True):
                    # arch linux packages are always lower case which is enforced below
                    # (no architecture information in AUR metadata)
                    provides_list = pkg.get("Provides")
                    provides = [self.parse_package_condition(s)
                                for s in provides_list] if provides_list else None
                    self.add_package_to_map(Package(
                        pkg.get("Name").lower(), "", pkg.get("Version"),
                        pkg.get("Description") or "", pkg.get("Depends"), pkg.get("OptDepends"),
                        None, pkg.get("Conflicts"), provides), pkg_map)
                return True
        except (gzip.BadGzipFile, EOFError, zlib.error, ijson.JSONError):
            if raise_error:
                raise
        return False

    def _to_package(self, pkg: pyalpm.Package) -> Package:
        # Arch package descriptions don't have ORed dependency alternatives
        # Arch linux packages are always lower case which is enforced below
        provides = [self.parse_package_condition(s) for s in pkg.provides] if pkg.provides else None
        return Package(pkg.name.lower(), pkg.arch, pkg.version, pkg.desc, pkg.depends,
                       pkg.optdepends, None, pkg.conflicts, provides)

    def list_installed(self) -> Iterable[Package]:
        localdb = self._handle.get_localdb()
        for pkg in localdb.pkgcache:
            if pkg.installdate != 0:
                yield self._to_package(pkg)

    def populate_primary_packages(self, resolve_pkgs: Iterable[PackageCondition],
                                  pkg_map: defaultdict[str, list[Package]]) -> None:
        """
        Return all packages in pacman sync repositories as an `Iterable` over `Package` objects.
        If the target packages passed are not available in those, then also include AUR packages.

        This is actually faster than querying the sync database multiple times (at least twice)
        using pacman/expac for the package and its optional dependencies since the sync databases
        are just a tarball of the packages that have to be read in entirety either way.

        :param resolve_pkgs: the target packages (as an `Iterable` of `PackageCondition`) for which
                             packages are being fetched
        :return: an `Iterable` over `Package` objects for each package found in the databases
        """
        for db_file in os.listdir("/var/lib/pacman/sync"):
            # assume all sync databases have already been downloaded (e.g. with `pacman -Syu`)
            if db_file.endswith(".db"):
                self._handle.register_syncdb(db_file.removesuffix(".db"),
                                             pyalpm.SIG_DATABASE_OPTIONAL)
        print_notice(f"Searching packages [{', '.join([str(p) for p in resolve_pkgs])}] in repos")
        for db in self._handle.get_syncdbs():
            for pkg in db.pkgcache:
                self.add_package_to_map(self._to_package(pkg), pkg_map)

    def has_extra_packages(self) -> bool:
        return True

    def populate_extra_packages(self, resolve_pkgs: Iterable[PackageCondition],
                                pkg_map: defaultdict[str, list[Package]]) -> None:
        """
        Return all packages in the AUR repository as an `Iterable` over `Package` objects.

        :param resolve_pkgs: the target packages (as an `Iterable` of `PackageCondition`) for which
                             packages are being fetched
        :return: an `Iterable` over `Package` objects for each package found in the AUR
        """
        print_notice(f"Searching packages [{', '.join([str(p) for p in resolve_pkgs])}] in AUR")
        # fetch AUR metadata, populate into all_packages and try again else if download
        # fails or AUR metadata file is broken, then refresh it and try again
        if not self._refresh_aur_metadata(raise_error=False) \
                or not self._populate_aur_packages(pkg_map, raise_error=False):
            Path(self._AUR_META_FILE).unlink(missing_ok=True)
            self._refresh_aur_metadata(raise_error=True)
            self._populate_aur_packages(pkg_map, raise_error=True)

    def version_compare(self, v1: str, v2: str) -> int:
        return pyalpm.vercmp(v1, v2)

    def cannonical_name(self, pkg: str) -> str:
        return pkg.lower()

    def parse_package_condition(self, pkg_dep: str) -> PackageCondition:
        if match := self._PKG_COND_RE.fullmatch(pkg_dep):
            return PackageCondition(self.cannonical_name(match.group(1)), match.group(4),
                                    match.group(3))
        print_warn(f"Found dependency with an unknown format [{pkg_dep}]")
        return PackageCondition(self.cannonical_name(pkg_dep))

    def parse_package_conditions(self, pkg_dep: str) -> Iterable[PackageCondition]:
        # Arch packages do not have multiple ORed conditions
        return (self.parse_package_condition(pkg_dep),)


if __name__ == "__main__":
    resolver = ResolvePackage(ArchPackages())
    resolver.exec_cmdline(sys.argv[1:])
