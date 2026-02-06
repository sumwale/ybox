"""
Resolve package dependencies (primarily optional ones) that can be presented to the user for
selection during package installation.
"""

import operator
import re
import sys
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Final, Iterable, Optional, Union, cast

from ybox.cmd import parse_opt_deps_args
from ybox.print import fgcolor, print_color, print_error, print_warn

# a function from the `operator` module
VersionCompare = Callable[[Any, Any], bool]


@dataclass
class PackageCondition:
    name: Final[str]
    arch: Final[str]
    version: Final[str]  # optionally a version to be compared against
    version_cmp: Final[str]  # comparison against the version e.g. <pkg> >= 1.1
    _version_cmp_op: Optional[VersionCompare] = None  # function equivalent of `version_cmp`

    def __hash__(self) -> int:
        return hash((self.name, self.version, self.version_cmp))

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, PackageCondition) and self.name == other.name and self.arch == \
            other.arch and self.version == other.version and self.version_cmp == other.version_cmp

    def __str__(self) -> str:
        name_arch = f"{self.name}:{self.arch}" if self.arch else self.name
        return f"{name_arch}{self.version_cmp}{self.version}" if self.version else name_arch

    __repr__ = __str__

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
# These are initially unprocessed objects which are transformed to `PackageCondition`s when required
PackageConditions = Union[Any, Iterable[PackageCondition]]
# ORed sets of package conditions that are ANDed (e.g. <pkg1> = 1.1 | <pkg11>, <pkg2> >= 2.0)
OrPackageConditions = Union[Any, Iterable[Iterable[PackageCondition]]]
OrDependencies = list[Iterable[PackageCondition]]


class DependencyType(str, Enum):
    """Different types of package dependencies in the fields of `Package` class."""
    DEPENDS = "Depends"
    RECOMMENDS = "Recommends"
    SUGGESTS = "Suggests"
    CONFLICTS = "Conflicts"


@dataclass
class Package:
    name: Final[str]
    arch: Final[str]
    version: Final[str]
    desc: Any
    installed: bool = False
    depends: OrPackageConditions = None
    recommends: OrPackageConditions = None
    suggests: OrPackageConditions = None
    conflicts: PackageConditions = None
    provides: PackageConditions = None  # required upfront by `DistributionPackageMap` for all
    provided_by: Final[Optional['Package']] = None
    transformed: bool = False

    def __hash__(self) -> int:
        return hash((self.name, self.arch, self.version))

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Package) and self.name == other.name \
            and self.arch == other.arch and self.version == other.version

    def __str__(self) -> str:
        if self.provided_by:
            return f"[{self.provided_by} provides {self.name}={self.version}]" if self.version \
                else f"[{self.provided_by} provides {self.name}]"
        installed_str = "(installed)" if self.installed else ""
        return f"{self.name}:{self.arch}={self.version}{installed_str}" if self.arch \
            else f"{self.name}={self.version}{installed_str}"


ConflictMap = defaultdict[str, list[PackageCondition]]
CandidatePackages = list[tuple[PackageCondition, list[Package]]]


class BasePackageCollection(ABC):

    # split package name, architecture and its comparison against a version
    PKG_COND_RE = re.compile(r"\s*([^=<>!:\s]+)(:[^=<>!:\s]+)?\s*(([=<>!]+)\s*(\S+)\s*)?")

    @abstractmethod
    def platform_architecture(self) -> str:
        ...

    @abstractmethod
    def version_compare(self, v1: str, v2: str) -> int:
        ...

    def cannonical_name(self, pkg: str) -> str:
        return pkg

    def package_condition_has_arch(self) -> bool:
        return True

    def parse_package_condition(self, pkg_dep: str, pkg_cond: re.Pattern[str] = PKG_COND_RE,
                                default_arch: str = "") -> PackageCondition:
        if mt := pkg_cond.fullmatch(pkg_dep):
            index_inc = 0
            if self.package_condition_has_arch():
                index_inc = 1
                if arch := mt.group(2):
                    arch = arch[1:]  # strip off the leading colon
                default_arch = arch or default_arch
            return PackageCondition(self.cannonical_name(mt.group(1)),
                                    default_arch or self.platform_architecture(),
                                    mt.group(4 + index_inc) or "", mt.group(3 + index_inc) or "")
        print_warn(f"Found dependency with an unknown format [{pkg_dep}]")
        return PackageCondition(self.cannonical_name(pkg_dep.strip()),
                                default_arch or self.platform_architecture(), "", "")


class PackageMap(BasePackageCollection):

    def add_conflicts(self, pkg: Package, conflicts: ConflictMap) -> None:
        conflicts[pkg.name].append(PackageCondition(pkg.name, pkg.arch, pkg.version,
                                                    "=", operator.eq))
        if pkg.conflicts:
            for conflict in pkg.conflicts:
                conflicts[conflict.name].append(conflict)

    def verify_package_condition(self, pkg: Package, pkg_cond: PackageCondition) -> bool:
        cmp = pkg_cond.version_cmp_op
        return (pkg.arch == pkg_cond.arch or pkg.arch == "all" or pkg.arch == "any") and (
            not pkg_cond.version or (cmp is not None and cmp(
                self.version_compare(pkg.version, pkg_cond.version), 0)))

    def _check_packages_in_map(self, resolve_pkgs: Iterable[PackageCondition],
                               resolved: CandidatePackages) -> Iterable[PackageCondition]:
        remaining_pkgs = ()
        for pkg in resolve_pkgs:
            candidates: Optional[list[Package]] = None
            installed: Optional[list[Package]] = None
            for candidate in self.lookup(pkg.name):
                if self.verify_package_condition(candidate, pkg):
                    if candidate.installed:
                        if installed:
                            installed.append(candidate)
                        else:
                            installed = [candidate]
                    elif candidates:
                        candidates.append(candidate)
                    else:
                        candidates = [candidate]
            if installed:
                print_color(f"Skipping {pkg} which is already installed: " +
                            ", ".join(str(p) for p in installed), fgcolor.cyan)
            elif candidates:
                resolved.append((pkg, candidates))
            elif remaining_pkgs:
                remaining_pkgs.append(pkg)
            else:
                remaining_pkgs = [pkg]
        return remaining_pkgs

    @abstractmethod
    def build_package_map(self, conflicts: ConflictMap,
                          resolve_pkgs: Iterable[PackageCondition]) -> CandidatePackages:
        ...

    @abstractmethod
    def lookup(self, pkg_name: str) -> Iterable[Package]:
        ...

    @abstractmethod
    def finalize_package_desc(self, pkg: Package) -> None:
        ...

    @abstractmethod
    def finalize_package_deps(self, pkg: Package) -> None:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...


class DistributionPackages(BasePackageCollection):

    @abstractmethod
    def populate_primary_packages(self, package_map: 'DistributionPackageMap',
                                  conflicts: ConflictMap,
                                  resolve_pkgs: Iterable[PackageCondition]) -> None:
        ...

    @abstractmethod
    def has_extra_packages(self) -> bool:
        ...

    @abstractmethod
    def populate_extra_packages(self, package_map: 'DistributionPackageMap', conflicts: ConflictMap,
                                resolve_pkgs: Iterable[PackageCondition]) -> None:
        ...

    def transform_description(self, desc: Any) -> Any:
        return desc

    @abstractmethod
    def transform_package_conditions(self, pkg: Package, pkg_conds: Any,
                                     dep_type: DependencyType) -> Iterable[PackageCondition]:
        ...

    @abstractmethod
    def transform_or_package_conditions(
            self, pkg: Package, pkg_conds: Any,
            dep_type: DependencyType) -> Iterable[Iterable[PackageCondition]]:
        ...


class DistributionPackageMap(PackageMap):

    def __init__(self, distro_pkgs: DistributionPackages):
        self._distro_pkgs = distro_pkgs
        self._package_map = defaultdict[str, list[Package]](list[Package])

    def platform_architecture(self) -> str:
        return self._distro_pkgs.platform_architecture()

    def version_compare(self, v1: str, v2: str) -> int:
        return self._distro_pkgs.version_compare(v1, v2)

    def cannonical_name(self, pkg: str) -> str:
        return self._distro_pkgs.cannonical_name(pkg)

    def add_package(self, pkg: Package, conflicts: Optional[ConflictMap]) -> None:
        self._package_map[pkg.name].append(pkg)
        if conflicts and pkg.installed:
            self.add_conflicts(pkg, conflicts)
        if pkg.provides:
            for prv in pkg.provides:
                if prv.version and prv.version_cmp != "=" and prv.version_cmp != "==":
                    print_error(f"Unexpected provides '{prv}' with version comparison "
                                f"operator '{prv.version_cmp}'")
                    continue
                provide_pkg = Package(prv.name, prv.arch or pkg.arch, prv.version, "",
                                      installed=pkg.installed, provided_by=pkg)
                self._package_map[provide_pkg.name].append(provide_pkg)

    def build_package_map(self, conflicts: ConflictMap,
                          resolve_pkgs: Iterable[PackageCondition]) -> CandidatePackages:
        resolved: CandidatePackages = []
        self._distro_pkgs.populate_primary_packages(self, conflicts, resolve_pkgs)
        # check for extra packages only if a given package is not found in the current package map
        if (remaining := self._check_packages_in_map(resolve_pkgs, resolved)) and \
                self._distro_pkgs.has_extra_packages():
            self._distro_pkgs.populate_extra_packages(self, conflicts, remaining)
            remaining = self._check_packages_in_map(remaining, resolved)
        if remaining:
            print_error(f"Packages [{', '.join([str(p) for p in remaining])}] not found")
            sys.exit(1)
        return resolved

    def lookup(self, pkg_name: str) -> Iterable[Package]:
        return self._package_map.get(pkg_name, ())

    def _transform_or_deps(self, pkg: Package, deps: OrPackageConditions,
                           dep_type: DependencyType) -> OrPackageConditions:
        return self._distro_pkgs.transform_or_package_conditions(pkg, deps, dep_type) \
            if not pkg.transformed and deps else deps

    def _transform_deps(self, pkg: Package, deps: PackageConditions,
                        dep_type: DependencyType) -> PackageConditions:
        return self._distro_pkgs.transform_package_conditions(pkg, deps, dep_type) \
            if not pkg.transformed and deps else deps

    def finalize_package_desc(self, pkg: Package) -> None:
        pkg.desc = self._distro_pkgs.transform_description(pkg.desc)

    def finalize_package_deps(self, pkg: Package) -> None:
        if not pkg.transformed:
            pkg.depends = self._transform_or_deps(pkg, pkg.depends, DependencyType.DEPENDS)
            pkg.recommends = self._transform_or_deps(pkg, pkg.recommends, DependencyType.RECOMMENDS)
            pkg.suggests = self._transform_or_deps(pkg, pkg.suggests, DependencyType.SUGGESTS)
            pkg.conflicts = self._transform_deps(pkg, pkg.conflicts, DependencyType.CONFLICTS)
            pkg.transformed = True

    def clear(self) -> None:
        self._package_map.clear()


class ResolvePackage:

    def __init__(self, pkg_map: PackageMap):
        self._package_map = pkg_map

    def has_conflict(self, pkg: Package, conflicts: ConflictMap) -> bool:
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
                if self._package_map.verify_package_condition(pkg, conflict):
                    print_warn(f"Skipping [{pkg}] that conflicts with [{conflict}]")
                    return True
        return False

    def _loop_package_deps(self, deps: OrDependencies, for_suggests: bool,
                           included_pkg_names: set[str], conflicts: ConflictMap,
                           dep_list: list[list[tuple[str, str, str, bool, bool]]]) -> None:
        for dep_alternates in deps:
            dep_alternate_list: list[tuple[str, str, str, bool, bool]] = []
            for dep in dep_alternates:
                has_installed = False
                for pkg in self._package_map.lookup(dep.name):
                    dep_pkg = pkg.provided_by if pkg.provided_by else pkg
                    # if any dependency among a set of alternatives is installed, then skip the set
                    if dep_pkg.installed:
                        # TODO: SW: it is possible that dep is a provided one with version that does
                        # not match dep_pkg, and there is another separate package that provides
                        # dep and does not conflict with installed dep_pkg; also arch check
                        if not has_installed:
                            has_installed = True
                            dep_alternate_list.clear()
                        self._package_map.finalize_package_desc(dep_pkg)
                        dep_alternate_list.append((dep_pkg.name, dep_pkg.version,
                                                   dep_pkg.desc, for_suggests, True))
                    elif not has_installed and self._package_map.verify_package_condition(
                        pkg, dep) and dep_pkg.name not in included_pkg_names \
                            and not self.has_conflict(pkg, conflicts):
                        self._package_map.finalize_package_desc(dep_pkg)
                        dep_alternate_list.append((dep_pkg.name, dep_pkg.version,
                                                   dep_pkg.desc, for_suggests, False))
                        included_pkg_names.add(dep_pkg.name)
            if dep_alternate_list:
                dep_list.append(dep_alternate_list)

    def select_packages(self, resolved: CandidatePackages, conflicts: ConflictMap) -> list[Package]:
        selected: list[Package] = []
        for pkg, candidates in resolved:
            preferred: Optional[Package] = None
            for candidate in candidates:
                # TODO: SW: add full conflict resolution based on depends that will select other
                # potential candidates after backtracking and even offer to uninstall
                if not self.has_conflict(candidate, conflicts):
                    candidate_pkg = candidate.provided_by if candidate.provided_by else candidate
                    if pkg.name == candidate_pkg.name:
                        preferred = candidate_pkg
                        break
                    if not preferred:
                        preferred = candidate_pkg
            if not preferred:
                print_error(f"No candidate found for {pkg} among "
                            f"[{', '.join(str(p) for p in candidates)}] due to conflicts")
                sys.exit(1)
            if pkg.name != preferred.name:
                print_color(f"Selected package {preferred} for {pkg}", fgcolor.cyan)
            selected.append(preferred)
        return selected

    def find_optional_deps(self, packages: list[Package], conflicts: ConflictMap,
                           include_suggests: bool) -> list[list[tuple[str, str, str, bool, bool]]]:
        all_recommends: OrDependencies = []
        all_suggests: OrDependencies = []
        for selected in packages:
            self._package_map.finalize_package_deps(selected)
            selected.installed = True  # mark to-be-installed packages as installed
            self._package_map.add_conflicts(selected, conflicts)
            if selected.recommends:
                all_recommends.extend(cast(OrDependencies, selected.recommends))
            if include_suggests and selected.suggests:
                all_suggests.extend(cast(OrDependencies, selected.suggests))
        included_pkg_names = set[str]()
        optional_deps: list[list[tuple[str, str, str, bool, bool]]] = []
        self._loop_package_deps(all_recommends, False, included_pkg_names, conflicts, optional_deps)
        if include_suggests:
            self._loop_package_deps(all_suggests, True, included_pkg_names, conflicts,
                                    optional_deps)
        return optional_deps

    def exec_cmdline(self, argv: list[str]) -> None:
        """
        Parse a list of arguments which are usually the command-line arguments of the calling
        script. Pass ["-h"]/["--help"] to see all the available arguments with help messages.

        :param argv: arguments to the function from the script command-line
        """
        args = parse_opt_deps_args(argv)

        # build the installed package map and the full package map
        conflicts = ConflictMap(list[PackageCondition])
        new_pkgs: list[str] = args.packages
        install_pkgs = [self._package_map.parse_package_condition(pkg) for pkg in new_pkgs]
        resolved_pkgs = self._package_map.build_package_map(conflicts, install_pkgs)

        # finally find and print the optional dependencies as expected by `ybox-pkg`
        selected_pkgs = self.select_packages(resolved_pkgs, conflicts)
        if optional_deps := self.find_optional_deps(selected_pkgs, conflicts, args.level > 1):
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

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_value, ex_traceback):  # type: ignore
        self._package_map.clear()
