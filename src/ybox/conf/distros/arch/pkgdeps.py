"""
Implementation of the `ybox.resolve.DistributionPackages` abstract class for Arch Linux packages
with a main stub that uses `ybox.resolve.ResolvePackage` to print the optional dependencies of
given packages as expected by `ybox-pkg`.
"""

import gzip
import os
import platform
import re
import sys
import time
import zlib
from pathlib import Path
from typing import Any, Iterable

import ijson  # type: ignore
import pyalpm
from pyalpm import Handle

from ybox.cmd import run_command
from ybox.config import Consts
from ybox.print import print_notice
from ybox.resolve import (ConflictMap, DependencyType, DistributionPackageMap,
                          DistributionPackages, Package, PackageCondition,
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
        self._platform_arch = platform.uname().machine

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

    def _populate_aur_packages(self, package_map: DistributionPackageMap, raise_error: bool) -> bool:
        """
        This will build a list of `Package` objects for all packages present in the AUR repository
        and populates them in the given `DistributionPackageMap`.

        This uses the AUR metadata downloaded explicitly. The alternative of using paru/yay to dump
        information of all available packages is much much slower. Querying using paru/yay for
        virtual packages in AUR database does not work since they maintain just the names of AUR
        packages locally, so just cannot query the optional deps.

        :param package_map: the instance of :class:`DistributionPackageMap` that should be populated
        :param raise_error: if True, then raise an error if there was one while reading the AUR
                            metadata else the method will return an empty list in case of failure
        :return bool: True if the map was populated successfully and False if `raise_error` was
                      False and there was an error while reading the AUR metadata
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
                    # AUR packages don't have an architecture and can be built for different
                    # platforms using custom compiler/cross-compiler flags but the package itself
                    # always has the native architecture
                    provides = [self.parse_package_condition(s, self._PKG_COND_RE,
                                                             self._platform_arch)
                                for s in provides_list] if provides_list else None
                    package_map.add_package(Package(
                        pkg.get("Name").lower(), self._platform_arch, pkg.get("Version"),
                        pkg.get("Description") or "", False, pkg.get("Depends"),
                        pkg.get("OptDepends"), None, pkg.get("Conflicts"), provides), None)
                return True
        except (gzip.BadGzipFile, EOFError, zlib.error, ijson.JSONError):
            if raise_error:
                raise
        return False

    def _to_package(self, pkg: pyalpm.Package, installed: bool, convert_conflicts: bool) -> Package:
        # Arch package descriptions don't have ORed dependency alternatives
        # Arch linux packages are always lower case which is enforced below
        provides = [self.parse_package_condition(s, self._PKG_COND_RE, pkg.arch)
                    for s in pkg.provides] if pkg.provides else None
        conflicts = [self.parse_package_condition(s, self._PKG_COND_RE, pkg.arch)
                     for s in pkg.conflicts] if convert_conflicts and pkg.conflicts \
            else pkg.conflicts
        return Package(pkg.name.lower(), pkg.arch, pkg.version, pkg.desc, installed, pkg.depends,
                       pkg.optdepends, None, conflicts, provides)

    def populate_primary_packages(self, package_map: DistributionPackageMap, conflicts: ConflictMap,
                                  resolve_pkgs: Iterable[PackageCondition]) -> None:
        """
        Populate all packages in pacman local and sync repositories into the given
        `DistributionPackageMap`.

        This is actually faster than querying the sync database multiple times (at least twice)
        using pacman/expac for the package and its optional dependencies since the sync databases
        are just a tarball of the packages that have to be read in entirety either way.

        :param package_map: the instance of :class:`DistributionPackageMap` that should be populated
        :param conflicts: the map of conflicts so far which should be populated with those from
                          the existing installed packages -- usually done by invoking the
                          :func:`add_package_to_map` method passing it already resolved `conflicts`
                          field of `Package` object for installed packages
        :param resolve_pkgs: the target packages (as an `Iterable` of `PackageCondition`) for which
                             packages are being fetched
        """
        for db_file in os.listdir("/var/lib/pacman/sync"):
            # assume all sync databases have already been downloaded (e.g. with `pacman -Syu`)
            if db_file.endswith(".db"):
                self._handle.register_syncdb(db_file.removesuffix(".db"),
                                             pyalpm.SIG_DATABASE_OPTIONAL)
        print_notice(f"Searching packages [{', '.join([str(p) for p in resolve_pkgs])}] in repos")
        for pkg in self._handle.get_localdb().pkgcache:
            package_map.add_package(self._to_package(pkg, pkg.installdate != 0, True), conflicts)
        for db in self._handle.get_syncdbs():
            for pkg in db.pkgcache:
                package_map.add_package(self._to_package(pkg, False, False), None)

    def has_extra_packages(self) -> bool:
        return True

    def populate_extra_packages(self, package_map: DistributionPackageMap, conflicts: ConflictMap,
                                resolve_pkgs: Iterable[PackageCondition]) -> None:
        """
        Populate all packages in the AUR repository into the given `DistributionPackageMap`.

        :param package_map: the instance of :class:`DistributionPackageMap` that should be populated
        :param conflicts: the map of conflicts so far which remains unchanged by this method
        :param resolve_pkgs: the target packages (as an `Iterable` of `PackageCondition`) for which
                             packages are being fetched
        """
        print_notice(f"Searching packages [{', '.join([str(p) for p in resolve_pkgs])}] in AUR")
        # fetch AUR metadata, populate into all_packages and try again else if download
        # fails or AUR metadata file is broken, then refresh it and try again
        if not self._refresh_aur_metadata(raise_error=False) \
                or not self._populate_aur_packages(package_map, raise_error=False):
            Path(self._AUR_META_FILE).unlink(missing_ok=True)
            self._refresh_aur_metadata(raise_error=True)
            self._populate_aur_packages(package_map, raise_error=True)

    def platform_architecture(self) -> str:
        return self._platform_arch

    def version_compare(self, v1: str, v2: str) -> int:
        return pyalpm.vercmp(v1, v2)

    def cannonical_name(self, pkg: str) -> str:
        return pkg.lower()

    def package_condition_has_arch(self) -> bool:
        return False

    def transform_package_conditions(self, pkg: Package, pkg_conds: Any,
                                     dep_type: DependencyType) -> Iterable[PackageCondition]:
        return [self.parse_package_condition(s, self._PKG_COND_RE, pkg.arch)
                for s in pkg_conds] if isinstance(pkg_conds[0], str) else pkg_conds

    def transform_or_package_conditions(
            self, pkg: Package, pkg_conds: Any,
            dep_type: DependencyType) -> Iterable[Iterable[PackageCondition]]:
        # Arch packages do not have multiple ORed conditions
        return [(self.parse_package_condition(s, self._PKG_COND_RE, pkg.arch),)
                for s in pkg_conds] if isinstance(pkg_conds[0], str) else pkg_conds


if __name__ == "__main__":
    package_map = DistributionPackageMap(ArchPackages())
    with ResolvePackage(package_map) as resolver:
        resolver.exec_cmdline(sys.argv[1:])
