"""
Resolve package dependencies (primarily optional ones) that can be presented to the user for
selection during package installation.
"""

import operator
import sys
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import (Any, Callable, Final, Iterable, MutableSequence, Optional,
                    Union, cast, final)

from ybox.cmd import parse_opt_deps_args
from ybox.print import print_error, print_notice

# a function from the `operator` module
VersionCompare = Callable[[Any, Any], bool]


@dataclass
class PackageCondition:
    name: Final[str]
    # TODO: SW: add architecture field and checks
    version: Final[str] = ""  # optionally a version to be compared against
    version_cmp: Final[str] = ""  # comparison against the version e.g. <pkg> >= 1.1
    _version_cmp_op: Optional[VersionCompare] = None  # function equivalent of `version_cmp`

    def __hash__(self) -> int:
        return hash((self.name, self.version, self.version_cmp))

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, PackageCondition) and self.name == other.name \
            and self.version == other.version and self.version_cmp == other.version_cmp

    def __str__(self) -> str:
        return f"{self.name} {self.version_cmp} {self.version}" if self.version else self.name

    @property
    def version_cmp_op(self) -> Optional[VersionCompare]:
        """equivalent function for `version_cmp` from the `operator` module"""
        if self.version and not self._version_cmp_op:
            if self.version_cmp == "=" or self.version_cmp == "==":
                self._version_cmp_op = operator.eq
            elif self.version_cmp == ">":
                self._version_cmp_op = operator.gt
            elif self.version_cmp == "<":
                self._version_cmp_op = operator.lt
            elif self.version_cmp == ">=":
                self._version_cmp_op = operator.ge
            elif self.version_cmp == "<=":
                self._version_cmp_op = operator.le
            elif self.version_cmp == "<>" or self.version_cmp == "!=":
                self._version_cmp_op = operator.ne
            elif not self.version_cmp:
                raise TypeError(f"No version comparison operator for version '{self.version}")
            else:
                raise TypeError(f"Unknown version comparison operator '{self.version_cmp}'")
        self._version_cmp_op


# Package conditions that are ANDed (e.g. <pkg1> = 1.1, <pkg2> >= 2.0)
# These are initially unprocessed strings which are transformed to `PackageCondition`s when required
PackageConditions = Optional[Union[list[str], list[PackageCondition]]]
# ORed sets of package conditions that are ANDed (e.g. <pkg1> = 1.1 | <pkg11>, <pkg2> >= 2.0)
OrPackageConditions = Optional[Union[list[str], list[Iterable[PackageCondition]]]]
OrDependencies = list[Iterable[PackageCondition]]


@dataclass
class Package:
    name: Final[str]
    arch: Final[str]
    version: Final[str]
    desc: Final[str] = ""
    requires: OrPackageConditions = None
    recommends: OrPackageConditions = None
    suggests: OrPackageConditions = None
    conflicts: PackageConditions = None
    provides: Optional[list[PackageCondition]] = None
    provided_by: Final[Optional['Package']] = None
    _transformed: bool = False

    def __hash__(self) -> int:
        return hash((self.name, self.version))

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Package) and self.name == other.name \
            and self.version == other.version

    def transform_multi_deps(self, deps: OrPackageConditions,
                             distro_packages: 'DistributionPackages') -> OrPackageConditions:
        if not self._transformed and deps and isinstance(deps[0], str):
            return [distro_packages.parse_package_conditions(cast(str, s)) for s in deps]
        return deps

    def transform_deps(self, deps: PackageConditions,
                       distro_packages: 'DistributionPackages') -> PackageConditions:
        if not self._transformed and deps and isinstance(deps[0], str):
            return [distro_packages.parse_package_condition(cast(str, s)) for s in deps]
        return deps

    def transform_all(self, distro_packages: 'DistributionPackages') -> None:
        if not self._transformed:
            self.requires = self.transform_multi_deps(self.requires, distro_packages)
            self.recommends = self.transform_multi_deps(self.recommends, distro_packages)
            self.suggests = self.transform_multi_deps(self.suggests, distro_packages)
            self.conflicts = self.transform_deps(self.conflicts, distro_packages)
            self._transformed = True


class DistributionPackages(ABC):

    @abstractmethod
    def list_installed(self) -> Iterable[Package]:
        ...

    @staticmethod
    def add_package_to_map(pkg: Package, pkg_map: defaultdict[str, list[Package]]) -> None:
        pkg_map[pkg.name].append(pkg)
        if pkg.provides:
            for provide in pkg.provides:
                if provide.version and provide.version_cmp != "=" and provide.version_cmp != "==":
                    print_error(f"Unexpected provides '{provide}' with version comparison "
                                f"operator '{provide.version_cmp}'")
                    continue
                provide_pkg = Package(provide.name, pkg.arch, provide.version, provided_by=pkg)
                pkg_map[provide_pkg.name].append(provide_pkg)

    @abstractmethod
    def populate_primary_packages(self, resolve_pkgs: Iterable[PackageCondition],
                                  pkg_map: defaultdict[str, list[Package]]) -> None:
        ...

    @abstractmethod
    def has_extra_packages(self) -> bool:
        ...

    @abstractmethod
    def populate_extra_packages(self, resolve_pkgs: Iterable[PackageCondition],
                                pkg_map: defaultdict[str, list[Package]]) -> None:
        ...

    @abstractmethod
    def version_compare(self, v1: str, v2: str) -> int:
        ...

    def cannonical_name(self, pkg: str) -> str:
        return pkg

    @abstractmethod
    def parse_package_condition(self, pkg_dep: str) -> PackageCondition:
        ...

    @abstractmethod
    def parse_package_conditions(self, pkg_dep: str) -> Iterable[PackageCondition]:
        ...


class ResolvePackage:

    def __init__(self, distro_pkgs: DistributionPackages):
        self._distro_pkgs = distro_pkgs

    def version_compare_op(self, v1: str, v2: str, cmp: Optional[VersionCompare]) -> bool:
        return not v2 or (cmp is not None and cmp(self._distro_pkgs.version_compare(v1, v2), 0))

    @final
    def _add_conflicts(self, pkg: Package,
                       conflicts: defaultdict[str, list[PackageCondition]]) -> None:
        conflicts[pkg.name].append(PackageCondition(pkg.name, pkg.version, "=", operator.eq))
        if pkg.conflicts:
            pkg.conflicts = pkg.transform_deps(pkg.conflicts, self._distro_pkgs)
            for conflict in cast(list[PackageCondition], pkg.conflicts):
                conflicts[conflict.name].append(conflict)

    def build_installed_package_map(self, conflicts: defaultdict[str, list[PackageCondition]]) -> \
            dict[str, Package]:
        installed_pkgs: dict[str, Package] = {}
        for pkg in self._distro_pkgs.list_installed():
            self._add_conflicts(pkg, conflicts)
            installed_pkgs[pkg.name] = pkg
        return installed_pkgs

    def _check_packages_in_map(self, resolve_pkgs: Iterable[PackageCondition],
                               package_map: defaultdict[str, list[Package]],
                               conflicts: defaultdict[str, list[PackageCondition]],
                               resolved: MutableSequence[Package]) -> Iterable[PackageCondition]:
        remaining_pkgs = ()
        for pkg in resolve_pkgs:
            for candidate in package_map.get(pkg.name, ()):
                if self.version_compare_op(candidate.version, pkg.version, pkg.version_cmp_op) \
                        and not self.has_conflict(candidate, conflicts):
                    resolved.append(candidate)
                    break
            else:
                if remaining_pkgs:
                    remaining_pkgs.append(pkg)
                else:
                    remaining_pkgs = [pkg]
        return remaining_pkgs

    def build_package_map(self, resolve_pkgs: Iterable[PackageCondition],
                          conflicts: defaultdict[str, list[PackageCondition]],
                          resolved: MutableSequence[Package]) -> dict[str, list[Package]]:
        pkg_map = defaultdict[str, list[Package]](list[Package])
        self._distro_pkgs.populate_primary_packages(resolve_pkgs, pkg_map)
        # check for extra packages only if a given package is not found in the current package map
        if remaining := self._check_packages_in_map(resolve_pkgs, pkg_map, conflicts, resolved):
            if self._distro_pkgs.has_extra_packages():
                self._distro_pkgs.populate_extra_packages(remaining, pkg_map)
                if remaining := self._check_packages_in_map(resolve_pkgs, pkg_map, conflicts,
                                                            resolved):
                    print_error(f"Packages [{', '.join([str(p) for p in remaining])}] not found")
                    sys.exit(1)
            else:
                print_error(f"Packages [{', '.join([str(p) for p in remaining])}] not found")
                sys.exit(1)
        return pkg_map

    def has_conflict(self, pkg: Package,
                     conflicts: defaultdict[str, list[PackageCondition]]) -> bool:
        # TODO: SW: do a proper conflict resolution with a conflict map initially populated
        # with the conflicts from all installed packages;
        # if no alternative satisfies due to conflicts then it can be skipped entirely for
        # recommends/suggests, whereas for packages to be installed and their required dependencies,
        # first loop through selected if there are more than one, then offer to uninstall existing
        # packages that need to be ranked in some way for the order in which the suggestions are
        # provided to the user (e.g. by number of uninstalls + orphans)
        # Once conflict resolution is sophisticated enough, then do the whole thing including for
        # the required dependencies, install all the packages explicitly including the version,
        # and then mark as dependency in the package manager at the end for all of the required,
        # recommended and suggested deps recursively
        if matches := conflicts.get(pkg.name):
            for conflict in matches:
                if self.version_compare_op(pkg.version, conflict.version, conflict.version_cmp_op):
                    print_notice(f"Skipping [{pkg}] that conflicts with [{conflict}]")
                    return True
        return False

    def _loop_package_deps(self, deps: OrDependencies, for_suggests: bool,
                           package_map: dict[str, list[Package]], included_pkg_names: set[str],
                           installed_pkgs: dict[str, Package],
                           conflicts: defaultdict[str, list[PackageCondition]],
                           dep_list: list[list[tuple[str, str, str, bool, bool]]]) -> None:
        for dep_alternates in deps:
            dep_alternate_list: list[tuple[str, str, str, bool, bool]] = []
            for dep in dep_alternates:
                for pkg in package_map.get(dep.name, ()):
                    dep_pkg = pkg.provided_by if pkg.provided_by else pkg
                    # if any dependency among a set of alternatives is installed, then skip the set
                    if dep_pkg.name in installed_pkgs:
                        dep_alternate_list.clear()
                        dep_alternate_list.append((dep_pkg.name, dep_pkg.version,
                                                   dep_pkg.desc, for_suggests, True))
                        break  # this breaks the inner loop as well as the outer loop
                    if self.version_compare_op(pkg.version, dep.version, dep.version_cmp_op) \
                            and dep_pkg.name not in included_pkg_names \
                            and not self.has_conflict(pkg, conflicts):
                        dep_alternate_list.append((dep_pkg.name, dep_pkg.version,
                                                   dep_pkg.desc, for_suggests, False))
                else:
                    continue
                break  # break outer loop in case a dependency is found to be in installed_pkgs
            if dep_alternate_list:
                dep_list.append(dep_alternate_list)
                if len(dep_alternate_list) == 1:
                    # don't show a package multiple times if there is only one choice
                    included_pkg_names.add(dep_alternate_list[0][0])

    def find_optional_deps(self, packages: Iterable[Package], package_map: dict[str, list[Package]],
                           installed_pkgs: dict[str, Package],
                           conflicts: defaultdict[str, list[PackageCondition]],
                           include_suggests: bool) -> list[list[tuple[str, str, str, bool, bool]]]:
        all_recommends: OrDependencies = []
        all_suggests: OrDependencies = []
        for selected in packages:
            selected.transform_all(self._distro_pkgs)
            installed_pkgs[selected.name] = selected  # put to-be-installed packages in installed
            self._add_conflicts(selected, conflicts)
            if selected.recommends:
                all_recommends.extend(cast(OrDependencies, selected.recommends))
            if include_suggests and selected.suggests:
                all_suggests.extend(cast(OrDependencies, selected.suggests))
        included_pkg_names = set[str]()
        optional_deps: list[list[tuple[str, str, str, bool, bool]]] = []
        self._loop_package_deps(all_recommends, False, package_map, included_pkg_names,
                                installed_pkgs, conflicts, optional_deps)
        if include_suggests:
            self._loop_package_deps(all_suggests, True, package_map, included_pkg_names,
                                    installed_pkgs, conflicts, optional_deps)
        return optional_deps

    def exec_cmdline(self, argv: list[str]) -> None:
        """
        Parse a list of arguments which are usually the command-line arguments of the calling
        script. Pass ["-h"]/["--help"] to see all the available arguments with help messages.

        :param argv: arguments to the function from the script command-line
        """
        args = parse_opt_deps_args(argv)

        # build the installed package map and the full package map
        conflicts = defaultdict[str, list[PackageCondition]](list[PackageCondition])
        installed_pkgs = self.build_installed_package_map(conflicts)
        resolved_pkgs: list[Package] = []
        new_pkgs: list[str] = args.packages
        install_pkgs = [self._distro_pkgs.parse_package_condition(pkg) for pkg in new_pkgs]
        package_map = self.build_package_map(install_pkgs, conflicts, resolved_pkgs)

        # finally find and print the optional dependencies as expected by `ybox-pkg`
        if optional_deps := self.find_optional_deps(resolved_pkgs, package_map, installed_pkgs,
                                                    conflicts, args.level > 1):
            if args.header:
                print(str(args.header))
            order = 0
            sep = args.separator
            for deps in optional_deps:
                order += 1
                for alt_dep in deps:
                    name, _, desc, suggests, installed = alt_dep
                    level = 2 if suggests else 1
                    # columns below are expected by ybox-pkg
                    # print(f"{args.prefix}{name}{sep}{version}{sep}{level}{sep}{order}{sep}{desc}")
                    # TODO: SW: temporarily using the old format
                    print(f"{args.prefix}{name}{sep}{level}{sep}{order}{sep}{installed}{sep}{desc}")
