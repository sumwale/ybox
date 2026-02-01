"""
Pyalpm is a Python module that provides native bindings libalpm to interact with Arch Linux
package databases.
"""

from __future__ import annotations

from typing import Optional

__all__: list[str] = ['DB', 'Handle', 'LOG_DEBUG', 'LOG_ERROR', 'LOG_FUNCTION',
                      'LOG_WARNING', 'PKG_REASON_DEPEND', 'PKG_REASON_EXPLICIT',
                      'Package', 'SIG_DATABASE', 'SIG_DATABASE_MARGINAL_OK',
                      'SIG_DATABASE_OPTIONAL', 'SIG_DATABASE_UNKNOWN_OK', 'SIG_PACKAGE',
                      'SIG_PACKAGE_MARGINAL_OK', 'SIG_PACKAGE_OPTIONAL', 'SIG_PACKAGE_UNKNOWN_OK',
                      'Transaction', 'alpmversion', 'error', 'find_grp_pkgs',
                      'find_satisfier', 'sync_newversion', 'vercmp', 'version']


class Handle:
    """
    Handles are objects that provide access to pacman databases and transactions.
    """

    def __init__(self, rootpath: str, dbpath: str) -> None:
        """
        A handle object is initialized with a root path (i.e. where do packages get
          installed) and a dbpath (i.e., where is the database information located).

        Parameters:
            rootpath (str): the root path where the packages will get installed (normally
                should be `/`)
            dbpath (str): the path where the database information is located (normally
                should be `/var/lib/pacman`)
        """

    def get_localdb(self) -> DB:
        """
        Return a reference to the local database object.

        Returns:
            DB: an alpm database `DB` object for the localdb
        """

    def get_syncdbs(self) -> list[DB]:
        """
        Return a list of references to the sync databases currently registered.

        Returns:
            list: list of alpm database `DB` objects for the currently registered sync databases
        """

    def register_syncdb(self, name: str, flags: int) -> DB:
        """
        Registers a new sync database with the given name.

        Parameters:
            name (str): the name of the database to register (e.g. `core`)
            flags (int): an integer constant representing the type of access (i.e. an
                `SIG_DATABASE*` constant as exported in the parent module)
        Returns:
            DB: the newly registered database as `DB` object on success
        """

    def set_pkgreason(self, package: Package, reason: int) -> None:
        """
        Sets the reason for this package's installation (e.g. explicit or as a dependency).

        Parameters:
            package (Package): the package to be marked
            reason (int): `PKG_REASON_EXPLICIT` (0) for explicitly requrested by a user
                or `PKG_REASON_DEPEND` (1) for as dependency of another package
        """

    def add_cachedir(self, path: str) -> None:
        """
        Adds a cache directory.

        Parameters:
            path (str): the path to the cache directory to add
        """

    def add_ignoregrp(self, groupname: str) -> None:
        """
        Add a group to be ignored.

        Parameters:
            groupname (str): the group name to ignore
        """

    def add_ignorepkg(self, pkgname: str) -> None:
        """
        Add a package to be ignored.

        Parameters:
            pkgname (str): the package name to ignore
        """

    def add_noextract(self, pkgname: str) -> None:
        """
        Add a noextract package.

        Parameters:
            pkgname (str): the package name to noextract
        """

    def add_noupgrade(self, pkgname: str) -> None:
        """
        Add a noupgrade package.

        Parameters:
            pkgname (str): the package name to noextract
        """

    def remove_cachedir(self, path: str) -> None:
        """
        Removes a cache directory.

        Parameters:
            path (str): the path to the cache directory to remove
        """

    def remove_ignoregrp(self, groupname: str) -> None:
        """
        Remove an ignore group.

        Parameters:
            groupname (str): the group name to be removed
        """

    def remove_ignorepkg(self, pkgname: str) -> None:
        """
        Remove an ignore package.

        Parameters:
            pkgname (str): the package name to be removed
        """

    def remove_noextract(self, pkgname: str) -> None:
        """
        Remove a noextract package.

        Parameters:
            pkgname (str): the package name to be removed
        """

    def remove_noupgrade(self, pkgname: str) -> None:
        """
        Remove a noupgrade package.

        Parameters:
            pkgname (str): the package name to be removed
        """

    def load_pkg(self, path: str, check_sig: bool) -> Package:
        """
        Loads package information from a tarball.

        Parameters:
            path (str): path of the tarball
            check_sig (bool): True to check the package signature
        Returns:
            Package: a reference to the `Package` object if successful
        """

    def init_transaction(self, nodeps: bool, force: bool, nosave: bool, nodepversion: bool,
                         cascade: bool, recurse: bool, dbonly: bool, alldeps: bool,
                         downloadonly: bool, noscriptlet: bool, noconflicts: bool, needed: bool,
                         allexplicit: bool, unneeded: bool, recurseall: bool,
                         nolock: bool) -> Transaction:
        """
        Initializes a transaction.

        Parameters:
            nodeps (bool): skip dependency checks
            force (bool): overwrite existing packages (deprecated)
            nosave (bool): do not save .pacsave files
            nodepversion (bool): undocumented
            cascade (bool): remove all dependent packages
            recurse (bool): remove also explicitly installed unneeded dependent packages
            dbonly (bool): only remove database entry, do not remove files
            alldeps (bool): mark packages as non-explicitly installed
            downloadonly (bool): download pakcages but do not install/upgrade anything
            noscriptlet (bool): do not execute the install scriptlet of one exists
            noconflicts (bool): ignore conflicts
            needed (bool): do not reinstall the targets that are already up-to-date
            allexplicit (bool): undocmented
            unneeded (bool): remove also explicitly unneeded deps
            recurseall (bool): undocumented
            nolock (bool): do not lock the database
        Returns:
            a `Transaction` object on success
        """


class DB:
    """
    A libalpm `DB` object that represents a pacman database. It represents a collection of packages.
    A database can be accessed by means of a `Handle` object, and can be used to query for packages.

    Attributes:
        name (str): The name of this database (for example, `core`)
        servers (list): A list of servers from where this database was fetched
        pkgcache (list): A list of references to the packages in this database
        grpcache (list): A list of tuples of the form:
        ```
        [
           ( 'GROUPNAME', [package-list] ),
           ( 'GROUPNAME2', [...]),
           ...
        ]
        ```
    """

    name: str
    servers: list[str]
    pkgcache: list[Package]
    grpcache: list[tuple[str, list[Package]]]

    def get_pkg(self, name: str) -> Optional[Package]:
        """
        Retrieves a package instance with the name `name`.

        Parameters:
            name (str): The name of the package (e.g., `coreutils`)
        Returns:
            Package: a reference to the `Package` object with the given name
                or None if it doesn't exist
        """

    def read_grp(self, group: str) -> Optional[tuple[str, list[Package]]]:
        """
        Retrieves the list of packages that belong to the group by the name passed.

        Parameters:
            group (str): The name of the group (e.g., `base`)
        Returns:
            tuple: tuple of group name and a list of `Package` objects of the packages
                that belong to that group or None if the group is not found
        """

    def search(self, *args: str) -> list[Package]:
        """
        Search this database for packages with the name matching the query patterns.

        Parameters:
            *args (str): variable number of regexp patterns (strings) to search
        Returns:
            list: a list of `Package` objects matching the query patterns by name
        """

    def update(self, force: bool) -> bool:
        """
        Attempts to update the sync database (i.e. `alpm_db_update`).

        Parameters:
            force (bool): if the database should be updated even if it’s up-to-date
        Returns:
            bool: True if the update was successful, or raises an error in case of a failure
        """


class Package:
    """
    Represents a package in a database (represented by a `DB` object).

    Attributes:
        name (str): The name of the package
        version (str): The version of the package
        builddate (int): The date on which this package was built
        installdate (int): The date in which this package was installed (only in localdb)
        size (int): The archive size
        isize (int): The installed size
        files (list): A list of files in this package
        db (DB): A reference to the database this package belongs to
        has_scriptlet (bool): Whether this package has a scriptlet
        licenses (list): A list of licenses for this package
        desc (str): Package description
        depends (list): A list of dependencies for this package
        optdepends (list): A list of the optional dependencies for this package
        checkdepends (list): A list of the check dependencies for this package (syncdb only)
        makedepends (list): A list of the make dependencies for this package (syncdb only)
        replaces (list): A list of packages this package replaces
        provides (list): A list of strings of what this package provides
        conflicts (list): A list of packages this package conflicts with
        backup (list): A list of backup tuples (filename, md5sum)
        groups (list): The groups this package belongs to
        arch (str): The CPU architecture for this package
        packager (str): The packager for this package
        md5sum (str): The package md5sum as hexadecimal digits
        sha256sum (str): The package sha256sum as hexadecimal digits
        base64_sig (str): The package signature encoded as base64
        filename (str): The package filename
        url (str): The package URL
    """

    name: str
    version: str
    builddate: int
    installdate: int
    size: int
    isize: int
    files: list[str]
    db: DB
    has_scriptlet: bool
    licenses: list[str]
    desc: str
    depends: list[str]
    optdepends: list[str]
    checkdepends: list[str]
    makedepends: list[str]
    replaces: list[str]
    provides: list[str]
    conflicts: list[str]
    backup: list[tuple[str, str]]
    groups: list[str]
    arch: str
    packager: str
    md5sum: str
    sha256sum: str
    base64_sig: str
    filename: str
    url: str

    def compute_requiredby(self) -> list[str]:
        """
        Computes the list of packages that require this package.

        Returns:
            list of packages that require this package
        """

    def compute_optionalfor(self) -> list[str]:
        """
        Computes the list of packages that optionally require this package.

        Returns:
            list of packages that require this package optionally
        """


class Transaction:
    """
    Transactions permit easy manipulations of several packages at a time.
    """

    def prepare(self) -> None:
        """
        Preprare a transaction.
        """

    def commit(self) -> None:
        """
        Commit a transaction.
        """

    def interrupt(self) -> None:
        """
        Interrupt the transaction.
        """

    def release(self) -> None:
        """
        Release the transaction.
        """

    def add_pkg(self, package: Package) -> None:
        """
        Append a package to the transaction.

        Parameters:
            package (Package): the package to be added to the transaction
        """

    def remove_pkg(self, package: Package) -> None:
        """
        Append a package from the transaction.

        Parameters:
            package (Package): the package to be removed from the transaction
        """

    def sysupgrade(self, downgrade: bool) -> None:
        """
        Set the transaction to perform a system upgrade.

        Parameters:
          downgrade (bool): whether to enable downgrades in the transaction
        """


class error(Exception):
    """
    Exception raised when an error arises from libalpm.
    The args attribute will usually contain a tuple (error message, errno from libalpm, extra data).
    """


def version() -> str:
    """
    Returns pyaplm version.
    """


def alpmversion() -> str:
    """
    Returns alpm version.
    """


def vercmp(version1: str, version2: str) -> int:
    """
    Compares version strings. See `man vercmp` for details.

    Parameters:
        version1 (str): first version to be compared
        version2 (str): second version to be compared

    Returns:
        int: < 0 if version1 < version2, = 0 if version1 == version2, > 0 if version1 > version2
    """


def find_satisfier(packages: list[str], pkgname: str) -> Optional[Package]:
    """
    Finds a package satisfying a dependency constraint in a package list.

    Parameters:
        packages (list):
        pkgname (str):
    Returns:
        Package: a `Package` object satisfying the contraint or None
    """


def find_grp_pkgs(databases: list[DB], group: str) -> list[Package]:
    """
    Find packages from a given group across databases.

    Parameters:
        databases (list): list of databases
        group (str): name of the group
    Returns:
        list: a list of `Package` objects in the given group
    """


def sync_newversion(package: Package, databases: list[DB]) -> Optional[Package]:
    """
    Finds an available upgrade for a package in a list of databases.

    Parameters:
        package (Package): the package to check for an available upgrade
        databases (list): list of databases to search for an upgrade
    Returns:
        Package: an upgrade `Package` candidate or None
    """


LOG_DEBUG: int = 4
LOG_ERROR: int = 1
LOG_FUNCTION: int = 8
LOG_WARNING: int = 2
PKG_REASON_DEPEND: int = 1
PKG_REASON_EXPLICIT: int = 0
SIG_DATABASE: int = 1024
SIG_DATABASE_MARGINAL_OK: int = 4096
SIG_DATABASE_OPTIONAL: int = 2048
SIG_DATABASE_UNKNOWN_OK: int = 8192
SIG_PACKAGE: int = 1
SIG_PACKAGE_MARGINAL_OK: int = 4
SIG_PACKAGE_OPTIONAL: int = 2
SIG_PACKAGE_UNKNOWN_OK: int = 8
