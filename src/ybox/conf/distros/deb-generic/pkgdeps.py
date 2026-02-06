"""
Implementation of the `ybox.resolve.DistributionPackages` abstract class for Debian packages
with a main stub that uses `ybox.resolve.ResolvePackage` to print the optional dependencies of
given packages as expected by `ybox-pkg`.
"""

import sys
from typing import Iterable, Optional, cast

import apt_pkg

from ybox.print import print_error, print_notice
from ybox.resolve import (CandidatePackages, ConflictMap, OrPackageConditions,
                          Package, PackageCondition, PackageMap,
                          ResolvePackage)


class APTPackageMap(PackageMap):

    def __init__(self):
        apt_pkg.init()
        self._cache = apt_pkg.Cache()
        self._records = apt_pkg.PackageRecords(self._cache)

    def finalize_package_desc(self, pkg: Package) -> None:
        if pkg.desc and not isinstance(pkg.desc, str):
            # should have only one PackageFile
            desc_file = cast(tuple[apt_pkg.PackageFile, int], pkg.desc[0])
            self._records.lookup(desc_file)
            pkg.desc = self._records.short_desc

    def _transform_or_deps(self, all_deps: dict[str, list[list[apt_pkg.Dependency]]],
                           dep_type: str) -> OrPackageConditions:
        if deps := all_deps.get(dep_type):
            return [[PackageCondition(dep.target_pkg.name, dep.target_ver, dep.comp_type)
                     for dep in or_deps] for or_deps in deps]
        return None

    def _transform_deps(self, all_deps: dict[str, list[list[apt_pkg.Dependency]]],
                        dep_type: str) -> Optional[list[PackageCondition]]:
        if deps := all_deps.get(dep_type):
            return [PackageCondition(dep.target_pkg.name, dep.target_ver, dep.comp_type)
                    for or_deps in deps if (dep := or_deps[0])]
        return None

    def finalize_package_deps(self, pkg: Package) -> None:
        if not pkg.transformed:
            all_deps = cast(dict[str, list[list[apt_pkg.Dependency]]], pkg.depends)
            pkg.depends = self._transform_or_deps(all_deps, "Depends")
            pkg.recommends = self._transform_or_deps(all_deps, "Recommends")
            pkg.suggests = self._transform_or_deps(all_deps, "Suggests")
            conflicts = self._transform_deps(all_deps, "Conflicts")
            if breaks := self._transform_deps(all_deps, "Breaks"):
                if conflicts:
                    conflicts.extend(breaks)
                else:
                    conflicts = breaks
            pkg.conflicts = conflicts
            pkg.transformed = True

    def version_compare(self, v1: str, v2: str) -> int:
        return apt_pkg.version_compare(v1, v2)

    def build_package_map(self, conflicts: ConflictMap,
                          resolve_pkgs: Iterable[PackageCondition]) -> CandidatePackages:
        # populate the conflicts map from installed packages
        with apt_pkg.TagFile("/var/lib/dpkg/status") as tagfile:
            for section in tagfile:
                if not section["Status"].endswith("installed"):
                    continue
                name = section["Package"]
                version = section["Version"]
                arch = section["Architecture"]
                pkg_all_conflicts = ()
                if pkg_conflicts := section.get("Conflicts"):
                    pkg_all_conflicts = apt_pkg.parse_depends(pkg_conflicts, strip_multi_arch=False)
                if pkg_conflicts := section.get("Breaks"):
                    pkg_breaks = apt_pkg.parse_depends(pkg_conflicts, strip_multi_arch=False)
                    if pkg_all_conflicts:
                        pkg_all_conflicts.extend(pkg_breaks)
                    else:
                        pkg_all_conflicts = pkg_breaks
                if pkg_all_conflicts:
                    # conflicts will never have ORed conditions
                    pkg_all_conflicts = [PackageCondition(tuples[0][0], tuples[0][1], tuples[0][2])
                                         for tuples in pkg_all_conflicts]
                self.add_conflicts(Package(name, arch, version, "", True,
                                           conflicts=pkg_all_conflicts), conflicts)
        resolved: CandidatePackages = []
        print_notice(f"Searching packages [{', '.join([str(p) for p in resolve_pkgs])}] in repos")
        if remaining := self._check_packages_in_map(resolve_pkgs, resolved):
            print_error(f"Packages [{', '.join([str(p) for p in remaining])}] not found")
            sys.exit(1)
        return resolved

    @staticmethod
    def _to_package(name: str, ver: apt_pkg.Version,
                    inst_ver: Optional[apt_pkg.Version]) -> Package:
        installed = inst_ver is not None and inst_ver.ver_str == ver.ver_str \
            and inst_ver.arch == ver.arch
        all_deps = ver.depends_list
        provides = ver.provides_list
        provides = [PackageCondition(p[0], p[1], "=") for p in provides] if provides else None
        return Package(name, ver.arch, ver.ver_str, ver.translated_description.file_list,
                       installed, all_deps, None, None, None, provides)

    def lookup(self, pkg_name: str) -> Iterable[Package]:
        try:
            pkg = self._cache[pkg_name]
            packages: list[Package] = []
            if pkg.has_provides and not pkg.has_versions:
                for name, ver_str, version in pkg.provides_list:
                    provided_by = self._to_package(version.parent_pkg.name, version,
                                                   version.parent_pkg.current_ver)
                    packages.append(Package(name, version.arch, ver_str, "",
                                            provided_by.installed, provided_by=provided_by))
            else:
                inst_version = pkg.current_ver
                for version in pkg.version_list:
                    packages.append(self._to_package(pkg.name, version, inst_version))
            return packages
        except KeyError:
            return ()

    def clear(self) -> None:
        pass


if __name__ == "__main__":
    with ResolvePackage(APTPackageMap()) as resolver:
        resolver.exec_cmdline(sys.argv[1:])
