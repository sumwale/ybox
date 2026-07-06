"""
Taken from apt_pkg-stubs/__init__.pyi distributed with the python3-apt deb package with updates
to fix flake8 and other errors. Also docstrings have been added using the documentation available
at https://apt-team.pages.debian.net/python-apt/library/apt_pkg.html and the classes have been
reworked as per the documentation provided there (new fields/methods, removed fields/methods,
entire new classes like `Group` etc).
"""

from __future__ import annotations

from typing import (Any, AnyStr, Iterable, Iterator, Literal, Mapping,
                    Protocol, TypeAlias, TypeVar, overload)

AcquireProgress: TypeAlias = Any
CdromProgress: TypeAlias = Any
InstallProgress: TypeAlias = Any
OpProgress: TypeAlias = Any


class FileLike(Protocol):
    def fileno(self) -> int:
        ...


class Cdrom:
    def add(self, progress: CdromProgress) -> bool:
        ...

    def ident(self, progress: CdromProgress) -> str:
        ...


@overload
def gettext(msg: str, domain: str) -> str:
    ...


@overload
def gettext(msg: str) -> str:
    ...


class Configuration(Mapping[str, str]):
    def find_file(self, key: str, default: str = "") -> str:
        ...

    def find_dir(self, key: str, default: str = "") -> str:
        ...

    def dump(self) -> str:
        ...

    def find(self, key: str, default: object = None) -> str:
        ...

    def find_b(self, key: str, default: bool = False) -> bool:
        ...

    def set(self, key: str, value: str) -> None:
        ...

    def value_list(self, key: str) -> list[str]:
        ...

    def clear(self, root: object = None) -> None:
        ...

    def __getitem__(self, key: str) -> str:
        ...

    def __iter__(self) -> Iterator[str]:
        ...

    def __len__(self) -> int:
        ...


config = Configuration()


def init_config() -> None:
    """Initialize the configuration of apt. This is needed for most operations."""


def init_system() -> None:
    """Initialize the system."""


def init() -> None:
    """
    A short cut to calling `init_config()` and `init_system()`. You can use this if you do not use
    the command line parsing facilities provided by `parse_commandline()`, otherwise call
    `init_config()`, parse the commandline afterwards and finally call `init_system()`.
    """


# FIXME: this is really a file-like object
def md5sum(o: Any) -> str:
    ...


# This is really a SystemError, but we don't want to expose that
class Error(Exception):
    """
    Exception class for most python-apt exceptions.

    This class replaces the use of `SystemError` in previous versions of python-apt. It inherits
    from `SystemError`, so make sure to catch this class first.
    """
    pass


class CacheMismatchError(Exception):
    """Raised when passing an object from a different cache to `apt_pkg.DepCache` methods"""
    pass


class Package:
    """
    Represent a package. A package is uniquely identified by its name and architecture and each
    package can have zero or more versions which can be accessed via the `version_list` property.
    Packages can be installed and removed by a `DepCache` object.

    Example:

    ```
    #!/usr/bin/python3

    # Example for packages. Print all essential and important packages.

    import apt_pkg

    def main():
        apt_pkg.init_config()
        apt_pkg.init_system()
        cache = apt_pkg.Cache()
        print("Essential packages:")
        for pkg in cache.packages:
            if pkg.essential:
                print(" ", pkg.name)
        print("Important packages:")
        for pkg in cache.packages:
            if pkg.important:
                print(" ", pkg.name)

    if __name__ == "__main__":
        main()
    ```

    Attributes:
        name (str): This is the name of the package.
        version_list (list): A list of `Version` objects for all versions of this package available
            in the cache, ordered highest to lowest.
        architecture (str): The architecture of the package, eg. amd64 or all.
        id (int): The ID of the package. This can be used to store information about the package.
            The ID is an int value.
        current_ver (Version): The version currently installed as a `Version` object, or `None`
            if the package is not installed.
        essential (bool): Whether the package has the `Essential` flag set; that is, whether it
            has a field `Essential: yes` in its record.
        important (bool): Whether the package has the (obsolete) `Important` flag set; that is,
            whether it has a field `Important: yes` in its record.
        current_state (int): The current state of the package (unpacked, installed, etc).
        inst_state (int): The state the currently installed version is in. This is normally
            `apt_pkg.INSTSTATE_OK`, unless the installation failed.
        selected_state (int): The state we want it to be, ie. if you mark a package for
            installation, this is `apt_pkg.SELSTATE_INSTALL`.
        has_versions (bool): A boolean value determining whether the list available via the
            attribute `version_list` has at least one element. This value may be used in
            combination with has_provides to check whether a package is virtual; that is, it has
            no versions and is provided at least once:
            ```
            pkg.has_provides and not pkg.has_versions
            ```
        has_provides (bool): A boolean value determining whether the list available via the
            attribute `provides_list` has at least one element. This value may be used in
            combination with `has_versions` to check whether a package is virtual; that is,
            it has no versions and is provided at least once:
            ```
            pkg.has_provides and not pkg.has_versions
            ```
        provides_list (list): A list of all package versions providing this package. Each element
            of the list is a triplet, where the first element is the name of the provided package,
            the second element the provided version (empty string), and the third element the
            version providing this package as a `Version` object.
        rev_depends_list (DependencyList): An iterator of `Dependency` objects for dependencies on
            this package. The returned iterator is implemented by the class `DependencyList`.
    """

    class DependencyList:
        """
        A simple list-like type for representing multiple dependency objects in an efficient manner;
        without having to generate all `Dependency` objects in advance.
        """

        def __getitem__(self, index: int) -> Dependency:
            """Return the item at the position index in the list."""

        def __len__(self) -> int:
            """
            The length of the list. This method should not be used directly, instead Python's
            built-in function `len()` should be used.
            """

    name: str
    version_list: list[Version]
    architecture: str
    id: int
    current_ver: Version
    essential: bool
    important: bool
    current_state: int
    inst_state: int
    selected_state: int
    has_versions: bool
    has_provides: bool
    provides_list: list[tuple[str, str, Version]]
    rev_depends_list: DependencyList

    def get_fullname(self, pretty: bool = False) -> str:
        """
        Get the full name of the package, including the architecture. If `pretty` is True,
        the architecture is omitted for native packages, that is, an amd64 `apt` package
        on an amd64 system would give `apt`.
        """


class Group:
    """
    Added in version 0.8.0.

    A collection of packages in which all packages have the same name. Groups are used in multi-arch
    environments, where two or more packages have the same name, but different architectures.
    """

    def __init__(self, cache: Cache, name: str) -> None:
        """"""

    def __getitem__(self, index: int) -> Package:
        """
        Get the package at the given index in the group.

        NOTE
        ====

        Groups are internally implemented using a linked list. The object keeps a pointer to the
        current object and the first object, so access to the first element, or accesses in order
        have a complexity of O(1). Random-access complexity is ranges from O(1) to O(n).
        """

    def find_package(self, architecture: str) -> Package:
        """
        Find a `Package` with the groups name and the architecture given in the argument
        `architecture`. If no such package exists, return `None`.
        """

    def find_preferred_package(self, prefer_nonvirtual: bool = True) -> Package:
        """
        Find the preferred `Package`. This is the package of the native architecture (specified in
        `APT::Architecture`) if available, or the package from the first foreign architecture.
        If no package could be found, return `None`.

        If `prefer_nonvirtual` is True, the preferred package will be a non-virtual package,
        if one exists.
        """


class Dependency:
    comp_type: str
    comp_type_deb: str
    target_pkg: Package
    target_ver: str
    dep_type_untranslated: str

    def all_targets(self) -> list[Version]:
        ...


class PackageFile:
    architecture: str
    archive: str
    codename: str
    component: str
    filename: str
    id: int
    index_type: str
    label: str
    not_automatic: bool
    not_source: bool
    origin: str
    site: str
    size: int
    version: str


class ProblemResolver:
    """
    `ProblemResolver` objects take care of resolving problems with dependencies. They mark packages
    for installation/removal and try to satisfy all dependencies.
    """

    def __init__(self, cache: DepCache) -> None:
        """
        The constructor takes a single argument of the type `apt_pkg.DepCache` to determine the
        cache that shall be manipulated in order to resolve the problems.
        """

    def clear(self, pkg: Package) -> None:
        """
        Revert the action of calling `protect()` or `remove()` on a package, resetting it to the
        default state.
        """

    def install_protect(self) -> None:
        """Mark all protected packages for installation."""

    def protect(self, pkg: Package) -> None:
        """Mark the package given by `pkg` as protected; that is, its state will not be changed."""

    def remove(self, pkg: Package) -> None:
        """Mark the package given by `pkg` for removal in the resolver."""

    def resolve(self, fix_broken: bool = True) -> bool:
        """
        Try to intelligently resolve problems by installing and removing packages. If `fix_broken`
        is True, apt will try to repair broken dependencies of installed packages.
        """

    def resolve_by_keep(self) -> bool:
        """Try to resolve the problems without installing or removing packages."""

    def keep_phased_updates(self) -> bool:
        """
        Hold back upgrades to phased versions of already installed packages, unless they are
        security updates.
        """


CURSTATE_CONFIG_FILES: int
INSTSTATE_REINSTREQ: int
INSTSTATE_HOLD_REINSTREQ: int


class HashString:
    def __init__(self, type: str, hash: str | None = None) -> None:
        ...

    def verify_file(self, filename: str) -> bool:
        ...

    hashtype: str
    hashvalue: str
    usable: bool


class HashStringList:
    def append(self, object: HashString) -> None:
        ...

    def find(self, type: str = "") -> HashString:
        ...

    def verify_file(self, filename: str) -> bool:
        ...

    file_size: int
    usable: bool


class Hashes:
    def __init__(self, object: bytes | FileLike | int) -> None:
        ...
    hashes: HashStringList


class Description:
    file_list: list[tuple[PackageFile, int]]


class Version:
    """
    The version object contains all information related to a specific package version.

    Attributes:
        hash (int): An integer hash value used for the internal storage.
        file_list (list): A list of (`PackageFile`, int: index) tuples for all `Package` files
            containing this version of the package.
        installed_size (int): The size of the package (in kilobytes), when unpacked on the disk.
        arch (str): The architecture of the package, eg. amd64 or all.
        downloadable (bool): Whether this package can be downloaded from a remote site.
        id (int): A numeric identifier which uniquely identifies this version in all versions
            in the cache.
        depends_list_str (dict): A dictionary of dependencies. The key specifies the type of the
            dependency (`Depends`, `Recommends`, etc.). The value is a list, containing items which
            refer to the or-groups of dependencies. Each of these or-groups is itself a list,
            containing tuples like (`pkgname`, `version`, `relation`) for each or-choice.

            An example return value for a package with a `Depends: python (>= 2.4)` would be:
            ```
            {'Depends': [
                            [
                            ('python', '2.4', '>=')
                            ]
                        ]
            }
            ```
            The same for a dependency on A (>= 1) | B (>= 2):
            ```
            {'Depends': [
                            [
                                ('A', '1', '>='),
                                ('B', '2', '>='),
                            ]
                        ]
            }
            ```
            The comparison operators are not the Debian ones, but the standard comparison operators
            as used in languages such as C and Python. This means that `>` means "larger than" and
            `<` means "less than".
        depends_list (dict): This is basically the same as `depends_list_str`, but instead of the
            (`pkgname`, `version`, `relation`) tuples, it returns `Dependency` objects, which can
            assist you with useful functions.
        multi_arch (int): 
    """
    ver_str: str
    hash: int
    file_list: list[tuple[PackageFile, int]]
    translated_description: Description
    installed_size: int
    size: int
    arch: str
    downloadable: bool
    is_security_update: bool
    id: int
    section: str
    priority: int
    priority_str: str
    provides_list: list[tuple[str, str, str]]
    depends_list_str: dict[str, list[list[tuple[str, str, str]]]]
    depends_list: dict[str, list[list[Dependency]]]
    parent_pkg: Package
    multi_arch: int
    MULTI_ARCH_ALL: int
    MULTI_ARCH_ALLOWED: int
    MULTI_ARCH_ALL_ALLOWED: int
    MULTI_ARCH_ALL_FOREIGN: int
    MULTI_ARCH_FOREIGN: int
    MULTI_ARCH_NO: int
    MULTI_ARCH_NONE: int
    MULTI_ARCH_SAME: int


class PackageRecords:
    homepage: str
    short_desc: str
    long_desc: str
    source_pkg: str
    source_ver: str
    record: str
    filename: str
    md5_hash: str
    sha1_hash: str
    sha256_hash: str
    hashes: HashStringList

    def __init__(self, cache: Cache) -> None:
        ...

    def lookup(self, packagefile: tuple[PackageFile, int], index: int = 0) -> bool:
        ...


T = TypeVar("T")


class TagSection(Mapping[str, AnyStr]):
    @overload
    def __new__(cls, str: str | bytes) -> TagSection[str]:
        ...

    @overload
    def __new__(
        cls, str: str | bytes, bytes: Literal[True]
    ) -> TagSection[bytes]:
        ...

    @overload
    def __new__(
        cls, str: str | bytes, bytes: Literal[False]
    ) -> TagSection[str]:
        ...

    def __getitem__(self, key: str) -> AnyStr:
        ...

    def get(self, key: str, default: object | None = None) -> AnyStr:
        ...

    def find(self, key: str, default: object | None = None) -> AnyStr:
        ...

    def find_raw(self, key: str, default: object | None = None) -> AnyStr:
        ...

    def __contains__(self, key: object) -> bool:
        ...

    def __len__(self) -> int:
        ...

    def __iter__(self) -> Iterator[str]:
        ...


class TagFile(Iterator[TagSection[AnyStr]]):
    @overload
    def __new__(cls, file: object) -> TagFile[str]:
        ...

    @overload
    def __new__(cls, file: object, bytes: Literal[True]) -> TagFile[bytes]:
        ...

    @overload
    def __new__(cls, file: object, bytes: Literal[False]) -> TagFile[str]:
        ...

    def __iter__(self) -> Iterator[TagSection[AnyStr]]:
        ...

    def __enter__(self: T) -> T:
        ...

    def __exit__(self, typ: object, value: object, traceback: object) -> None:
        ...

    def __next__(self) -> TagSection[AnyStr]:
        ...


def version_compare(a: str, b: str) -> int:
    ...


def get_lock(file: str, errors: bool = False) -> int:
    ...


def pkgsystem_lock() -> None:
    ...


def pkgsystem_unlock() -> None:
    ...


def read_config_file(configuration: Configuration, path: str) -> None:
    ...


def read_config_dir(configuration: Configuration, path: str) -> None:
    ...


def pkgsystem_lock_inner() -> None:
    ...


def pkgsystem_unlock_inner() -> None:
    ...


def pkgsystem_is_locked() -> bool:
    ...


SELSTATE_HOLD: int


class AcquireWorker:
    current_item: AcquireItemDesc
    current_size: int
    total_size: int
    status: str


class AcquireItem:
    active_subprocess: str
    complete: bool
    desc_uri: str
    destfile: str
    error_text: str
    filesize: int
    id: int
    is_trusted: bool
    local: bool
    mode: str
    partialsize: int
    status: int

    STAT_IDLE: int
    STAT_FETCHING: int
    STAT_DONE: int
    STAT_ERROR: int
    STAT_AUTH_ERROR: int
    STAT_TRANSIENT_NETWORK_ERROR: int


class AcquireItemDesc:
    description: str
    owner: AcquireItem
    shortdesc: str
    uri: str


class Acquire:
    fetch_needed: int
    items: list[AcquireItem]
    partial_present: int
    total_needed: int
    workers: list[AcquireWorker]
    RESULT_CANCELLED: int
    RESULT_FAILED: int
    RESULT_CONTINUE: int

    def __init__(self, progress: AcquireProgress | None = None) -> None:
        ...

    def run(self) -> int:
        ...

    def shutdown(self) -> None:
        ...

    def get_lock(self, path: str) -> None:
        ...


class AcquireFile(AcquireItem):
    def __init__(
        self,
        owner: Acquire,
        uri: str,
        hash: HashStringList | str | None,
        size: int = 0,
        descr: str = "",
        short_descr: str = "",
        destdir: str = "",
        destfile: str = "",
    ) -> None:
        ...


class IndexFile:
    def archive_uri(self, path: str) -> str:
        ...
    describe: str
    exists: bool
    has_packages: bool
    is_trusted: bool
    label: str
    size: int


class SourceRecordFiles:
    hashes: HashStringList
    path: str
    size: int
    type: str


class SourceRecords:
    def lookup(self, name: str) -> bool:
        ...

    def restart(self) -> None:
        ...

    def step(self) -> bool:
        ...
    binaries: list[str]
    version: str
    files: list[SourceRecordFiles]
    index: IndexFile
    package: str
    section: str


class ActionGroup:
    """
    `ActionGroup()` objects make operations on the cache faster by delaying certain cleanup
    operations until the action group is released.

    An action group is also a context manager and therefore supports the with statement.
    But because it becomes active as soon as it is created, you should not create an
    `ActionGroup()` object before entering the with statement. Thus, you should always
    use the following form:

    ```
    with apt_pkg.ActionGroup(depcache):
    ...
    ```

    For code which has to run on Python versions prior to 2.5, you can also use the
    traditional way:

    ```
    actiongroup = apt_pkg.ActionGroup(depcache)
    ...
    actiongroup.release()
    ```

    In addition to the methods required to implement the context manager interface,
    `ActionGroup` objects provide the `release()` method.
    """

    def __init__(self, depcache: DepCache) -> None:
        """
        Create a new `ActionGroup()` object for the `DepCache` object given by the parameter
        `depcache`.
        """

    def release(self) -> None:
        """Release the `ActionGroup`. This will reactive the collection of package garbage."""


class MetaIndex:
    dist: str
    index_files: list[IndexFile]
    is_trusted: bool
    uri: str


class SourceList:
    list: list[MetaIndex]

    def read_main_list(self) -> None:
        ...

    def find_index(self, pf: PackageFile) -> IndexFile:
        ...


class PackageManager:
    """
    Abstraction of a package manager. This object takes care of retrieving packages, ordering the
    installation, and calling the package manager to do the actual installation.

    Attributes:
        RESULT_COMPLETED (int): A constant for checking whether the result of the call to
            `do_install()` has completed.
        RESULT_FAILED (int): A constant for checking whether the result of the call to
            `do_install()` has failed.
        RESULT_INCOMPLETE (int): A constant for checking whether the result of the call to
            `do_install()` is incomplete.
    """
    RESULT_COMPLETED: int
    RESULT_FAILED: int
    RESULT_INCOMPLETE: int

    def __init__(self, depcache: DepCache) -> None:
        """This constructor initializes the `PackageManager` given a `DepCache` `depcache`."""

    def get_archives(
        self, fetcher: Acquire, list: SourceList, recs: PackageRecords
    ) -> bool:
        """
        Add all packages marked for installation (or upgrade, anything which needs a download) to
        the `Acquire` object referenced by fetcher.

        The parameter `list` specifies a `SourceList` object which is used to retrieve the
        information about the archive URI for the packages which will be fetched.

        The parameter `records` takes a `PackageRecords` object which will be used to look up the
        file name of the package.
        """

    def do_install(self, status_fd: int) -> int:
        """
        Install the packages and return one of the class constants `RESULT_COMPLETED`,
        `RESULT_FAILED`, `RESULT_INCOMPLETE`. The argument `status_fd` can be used to specify
        a file descriptor that APT will write status information on (see README.progress-reporting
           in the apt source code for information on what will be written there).
        """

    def fix_missing(self) -> bool:
        """Fix the installation if a package could not be downloaded."""


class Cache:
    """
    A Cache object represents the cache used by APT which contains information about packages.
    The object itself provides no means to modify the cache or the installed packages, see the
    classes DepCache and PackageManager for such functionality.

    NOTE
    ====

    The cache supports colon-separated name:architecture pairs. For normal architectures,
    they are equal to a (name, architecture) tuple. For the "any" architecture behavior is
    different, as "name:any" is equivalent to ("name:any", "any"). This is done so that "name:any"
    matches all packages with that name which have Multi-Arch: allowed set.

    Attributes:
        depends_count (int): The total number of dependencies stored in the cache.
        file_list (list[PackageFile]): A list of all `PackageFile` objects stored in the cache.
        group_count (int): The number of groups in the cache.
        groups (GroupList): A sequence of Group objects, implemented as a GroupList object.
        is_multi_arch (bool): An attribute determining whether the cache supports multi-arch.
        package_count (int): The total number of packages available in the cache. This value is
            equal to the length of the list provided by the packages attribute.
        package_file_count (int): The total number of Packages files available (the Packages files
            listing the packages). This is the same as the length of the list in the attribute
            `file_list`.
        packages (PackageList): A sequence of Package objects, implemented as a PackageList object.
        provides_count (int): The number of provided packages.
        ver_file_count (int): The number of (Version, PackageFile) relations stored in the cache.
        version_count (int): The number of package versions available in the cache.
    """

    depends_count: int
    file_list: list[PackageFile]
    group_count: int
    groups: GroupList
    is_multi_arch: bool
    package_count: int
    package_file_count: int
    packages: PackageList
    provides_count: int
    ver_file_count: int
    version_count: int

    class GroupList(Iterable[Group]):
        """
        A simple sequence-like object which only provides a length and an implementation of
        `__getitem__` for accessing groups at a certain index. Apart from being iterable,
        it can be used in the following ways:

        list[index]:
            Get the `Group` object for the group at the position given by index in the `GroupList`.

        len(list):
            Return the length of the `GroupList` object list.
        """

        def __getitem__(self, index: int) -> Group:
            """Return the `Group` at the given index."""

    class PackageList(Iterable[Package]):
        """
        A simple sequence - like object which only provides a length and an implementation of
        `__getitem__` for accessing packages at a certain index. Apart from being iterable, it can
        be used in the following ways:

        list[index]:
            Get the Package object for the package at the position given by index in the
            `PackageList` list.

        len(list):
             Return the length of the `PackageList` object list.
         """

        def __getitem__(self, index: int) -> Package:
            """Return the `Package` at the given index."""

    def __init__(self, progress: OpProgress | None = None) -> None:
        """
        The constructor takes an optional argument which must be a subclass of
        `apt.progress.base.OpProgress`. This object will then be used to display information during
        the cache opening process (or possible creation of the cache). It may also be `None`,
        in which case no progress will be emitted. If not given, progress will be printed to
        standard output.
        """

    def __contains__(self, name: str | tuple[str, str]) -> Package:
        """
        If the given `name` is a string, then check whether a package with the name given by `name`
        exists in the cache for the native architecture. If `name` includes a colon, the part after
        the colon is used as the architecture.

        If the argument is a `tuple` having both `name` and `architecture`, check whether a package
        with the given name and architecture exists in the cache.
        """

    def __getitem__(self, name: str | tuple[str, str]) -> Package:
        """
        Return the `Package()` object for the package name given by `name` when it is a string.
        If `name` includes a colon, the part after the colon is used as the architecture.

        If both `name` and `architecture` are provided as a `tuple`, then return the `Package()`
        object for the package with the given name and architecture.
        """

    def __len__(self) -> int:
        ...

    def update(
        self, progress: AcquireProgress, sources: SourceList, pulse_interval: int
    ) -> int:
        """
        Update the index files used by the cache. A call to this method does not affect the current
        `Cache` object, instead a new one should be created in order to use the changed index files.

        The parameter progress takes an `apt.progress.base.AcquireProgress` object which will
        display the progress of fetching the index files. The parameter sources takes a `SourceList`
        object which lists the sources. The parameter progress takes an integer describing the
        interval (in microseconds) in which the `pulse()` method of the progress object
        will be called.
        """


class DepCache:
    """
    A DepCache object provides access to more information about the objects made available by the
    `Cache` object as well as means to mark packages for removal and installation, among other
    actions.

    Objects of this type provide several methods. Most of those methods are safe to use and should
    never raise any exception (all those methods for requesting state information or marking
    changes). If a method is expected to raise an exception, it will be stated in the description.

    Attributes:
        broken_count (int): number of packages which are broken
        inst_count (int): number of packages marked for installation
        del_count (int): number of packages which should be removed
        keep_count (int): number of packages marked as keep
        usr_size (int): The size required for the changes on the filesystem. If you install
            packages, this is positive, if you remove them its negative.
        deb_size (int): The size of the packages which are needed for the changes to be applied.
        policy (Policy): The underlying `Policy` object used by the `DepCache` to select
            candidate versions.
    """
    broken_count: int
    inst_count: int
    del_count: int
    keep_count: int
    usr_size: int
    deb_size: int
    policy: Policy

    def __init__(self, cache: Cache) -> None:
        """
        The constructor takes a single argument which specifies the `Cache` object the new object
        shall be related to. While it is theoretically possible to create multiple `DepCache`
        objects for the same cache, they will not be independent from each other since they all
        access the same underlying C++ object.

        If an object of a different cache is passed, `CacheMismatchError` is raised.
        """

    def init(self, progress: OpProgress | None = None) -> None:
        """
        Initialize the `DepCache`. This is done automatically when the cache is opened, but
        sometimes it may be useful to reinitialize the `DepCache`. Like the constructor of `Cache`,
        this function takes a single `apt.progress.base.OpProgress` object to display progress
        information.
        """

    def get_candidate_ver(self, pkg: Package) -> Version | None:
        """
        Return the candidate version for the package given by the parameter pkg as a `Version`
        object. The default candidate for a package is the version with the highest pin, although
        a different one may be set using `set_candidate_ver()`. If no candidate can be found,
        return `None` instead.
        """

    def set_candidate_ver(self, pkg: Package, ver: Version) -> bool:
        """
        Set the candidate version of the package given by the `Package` object pkg to the version
        given by the Version object version and return True. If odd things happen, this function
        may raise a `SystemError` exception, but this should not happen in normal usage.
        See `get_candidate_ver()` for a way to retrieve the candidate version of a package.
        """

    def marked_install(self, pkg: Package) -> bool:
        """Return True if the package is marked for install."""

    def marked_upgrade(self, pkg: Package) -> bool:
        """Return True if the package is marked for upgrade."""

    def marked_keep(self, pkg: Package) -> bool:
        """Return True if the package is marked for keep."""

    def marked_downgrade(self, pkg: Package) -> bool:
        """Return True if the package should be downgraded."""

    def marked_delete(self, pkg: Package) -> bool:
        """Return True if the package is marked for delete."""

    def marked_reinstall(self, pkg: Package) -> bool:
        """Return True if the package should be reinstalled."""

    def is_upgradable(self, pkg: Package) -> bool:
        """
        Return True if the package is upgradable, the package can then be marked for upgrade by
        calling the method `mark_install()`.
        """

    def is_garbage(self, pkg: Package) -> bool:
        """
        Return True if the package is garbage, that is, if it was automatically installed and no
        longer referenced by other packages.
        """

    def is_auto_installed(self, pkg: Package) -> bool:
        """
        Return True if the package is automatically installed, that is, as a dependency of another
        package.
        """

    def is_inst_broken(self, pkg: Package) -> bool:
        """
        Return True if the package is broken on the current install. This takes changes which have
        not been marked not into account.
        """

    def is_now_broken(self, pkg: Package) -> bool:
        """
        Return True if the package is now broken, that is, if the package is broken if the marked
        changes are applied.
        """

    def mark_keep(self, pkg: Package) -> None:
        """Mark the `Package` `pkg` for keep."""

    def mark_install(
        self, pkg: Package, auto_inst: bool = True, from_user: bool = True
    ) -> None:
        """
        Mark the `Package` `pkg` for install, and, if `auto_inst` is True, its dependencies as well.
        If `from_user` is True, the package will not be marked as automatically installed.
        """

    def set_reinstall(self, pkg: Package) -> None:
        """Set if the `Package` `pkg` should be reinstalled."""

    def mark_delete(self, pkg: Package, purge: bool = False) -> None:
        """
        Mark the `Package` `pkg` for delete. If `purge` is True, the configuration files will
        be removed as well.
        """

    def mark_auto(self, pkg: Package, auto: bool) -> None:
        """Mark the `Package` `pkg` as automatically installed."""

    def commit(
        self, acquire_progress: AcquireProgress, install_progress: InstallProgress
    ) -> None:
        """
        Commit all marked changes, while reporting the progress of fetching packages via the
        `apt.progress.base.AcquireProgress` object given by `acquire_progress` and reporting the
        installation of the package using the apt.progress.base.InstallProgress object given by
        `install_progress`.

        If this fails, an exception of the type `SystemError` will be raised.
        """

    def upgrade(self, dist_upgrade: bool = True) -> bool:
        """
        Mark the packages for upgrade under the same conditions apt-get does. If dist_upgrade is
        True, also allow packages to be upgraded if they require installation/removal of other
        packages; just like `apt-get dist-upgrade`.

        Despite returning a boolean value, this raises `SystemError` and does not return False
        if an error occurred.
        """

    def fix_broken(self) -> bool:
        """
        Try to fix all broken packages in the cache and return True in case of success. If an
        error occurred, a SystemError exception is raised.
        """

    def read_pinfile(self, file: str) -> bool:
        """
        A proxy function which calls the method `Policy.read_pinfile()` of the `Policy` object
        used by this object. This method raises a `SystemError` exception if the file could
        not be parsed.
        """

    def phasing_applied(self, pkg: Package) -> bool:
        """Return True if the package update is being phased."""


class Policy:
    def get_priority(self, pkg: PackageFile | Version) -> int:
        ...


class SystemLock:
    def __enter__(self) -> None:
        ...

    def __exit__(self, typ: object, value: object, traceback: object) -> None:
        ...


class FileLock:
    def __init__(self, path: str) -> None:
        ...

    def __enter__(self) -> None:
        ...

    def __exit__(self, typ: object, value: object, traceback: object) -> None:
        ...


def upstream_version(ver: str) -> str:
    ...


def get_architectures() -> list[str]:
    ...


def check_dep(pkg_ver: str, dep_op: str, dep_ver: str) -> bool:
    ...


def uri_to_filename(uri: str) -> str:
    ...


def str_to_time(rfc_time: str) -> int:
    ...


def time_to_str(time: int) -> str:
    ...


def size_to_str(size: float | int) -> str:
    ...


def open_maybe_clear_signed_file(file: str) -> int:
    ...


def parse_depends(
    s: str, strip_multi_arch: bool = True, architecture: str = ""
) -> list[list[tuple[str, str, str]]]:
    ...


def parse_src_depends(
    s: str, strip_multi_arch: bool = True, architecture: str = ""
) -> list[list[tuple[str, str, str]]]:
    ...


def string_to_bool(s: str) -> bool:
    ...
