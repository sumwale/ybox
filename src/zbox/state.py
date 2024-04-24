"""
Classes and methods for bookkeeping the state of zbox containers including the packages
installed on each container explicitly.
"""

import re
import sqlite3
from configparser import ConfigParser
from contextlib import closing
from io import StringIO
from typing import Optional, Tuple

from .env import Environ
from .util import print_error


class ZboxStateManagement:
    """
    Maintain the state of all Zbox containers. This includes:

    1. The full configuration used for the creation of a container.
    2. The packages installed explicitly on each of the containers (though all
         packages may be visible on all containers having 'shared_root' as true)
    3. Cleanup state of containers removed explicitly or those that got stopped/removed.

    Expected usage is using a `with` statement to ensure proper cleanup other the database
    may be left in a locked state.
    """

    def __init__(self, env: Environ):
        """
        Initialize connection to database and create tables+indexes if not present.

        :param env: the current Environ
        """
        # explicitly control transaction begin (in exclusive mode) since we need SERIALIZABLE
        # isolation level while sqlite3 module will not start transactions before reads
        self.__conn = sqlite3.connect(f"{env.data_dir}/state.db", timeout=60,
                                      isolation_level=None)
        # create the initial tables
        self.__begin_transaction()
        self.__conn.execute("CREATE TABLE IF NOT EXISTS containers (name TEXT PRIMARY KEY, "
                            "  distribution TEXT, shared_root TEXT, configuration TEXT)")
        self.__conn.execute("CREATE TABLE IF NOT EXISTS packages (name TEXT, container TEXT, "
                            "  shared_root TEXT, local_copies TEXT, type TEXT, "
                            "  PRIMARY KEY(name, container)) WITHOUT ROWID")
        self.__conn.execute("CREATE INDEX IF NOT EXISTS package_containers "
                            "ON packages(container)")
        self.__conn.create_function("REGEXP", 2, ZboxStateManagement.regexp)
        self.__conn.commit()

    def __begin_transaction(self) -> None:
        """begin an EXCLUSIVE transaction to ensure atomicity of a group of reads and writes"""
        self.__conn.execute("BEGIN EXCLUSIVE TRANSACTION")

    @staticmethod
    def regexp(pattern: str, val: str) -> int:
        """callable for the user-defined SQL REGEXP function"""
        return 1 if re.search(pattern, val) else 0

    def register_container(self, container_name: str, distribution: str, shared_root: str,
                           parser: ConfigParser) -> None:
        """
        Register information of a zbox container including its name, distribution and
        configuration.

        :param container_name: name of the container
        :param distribution: the Linux distribution used when creating the container
        :param shared_root: the local shared root directory if 'shared_root' flag is enabled for
                            the container (see 'shared_root' key in [base] section in basic.ini)
        :param parser: parser object for the configuration file used for creating the container
        """
        # build the ini string from parser
        with StringIO() as config:
            parser.write(config)
            config.flush()
            config_str = config.getvalue()
            # if the zbox container has been destroyed from outside zbox tools, then there may
            # be a conflict in the insert, so first unregister the container for full cleanup
            self.__begin_transaction()
            self.__unregister_container(container_name, commit=False)
            self.__conn.execute("INSERT INTO containers VALUES (?, ?, ?, ?)",
                                (container_name, distribution, shared_root, config_str))
            self.__conn.commit()

    def unregister_container(self, container_name: str) -> bool:
        """
        Unregister information of a zbox container. This also clears any registered packages
        for the container if 'shared_root' is false for the container. However, if 'shared_root'
        is true for the container, its packages are marked as "zombie" (i.e. its owner is empty)
        if no other container refers to them. This is because the packages will still be visible
        in all other containers having 'shared_root' as true.

        :param container_name: name of the container
        :return: true if container was found in the database and removed
        """
        self.__begin_transaction()
        return self.__unregister_container(container_name, commit=True)

    def __unregister_container(self, container_name: str, commit: bool) -> bool:
        """
        The real workhorse of `unregister_container`

        :param container_name: name of the container
        :return: true if container was found in the database and removed
        """
        with closing(self.__conn.cursor()) as cursor:
            cursor.execute("DELETE FROM containers WHERE name = ? RETURNING shared_root",
                           (container_name,))
            row = cursor.fetchone()
        with closing(self.__conn.cursor()) as cursor:
            # if the container has 'shared_root', then package will continue to exist, but we will
            # have to blank out the container name in case there is no other container that
            # references that package
            if row and str(row[0]):
                # SQL below first finds the packages to be deleted due to the container, then
                # searches for packages that are only in the container and referenced by no other
                # with same shared_root (left outer join will have null values for rows missing
                #   from RHS). Value is set to empty rather than null to avoid SQL null weirdness.
                cursor.execute("""
                    UPDATE packages SET container = '' WHERE name IN (
                      SELECT d_pkgs.name FROM packages d_pkgs LEFT OUTER JOIN
                      (SELECT name, shared_root FROM packages WHERE shared_root <> "" AND
                       container <> ?) pkgs
                      ON (d_pkgs.name = pkgs.name AND d_pkgs.shared_root = pkgs.shared_root)
                      WHERE d_pkgs.container = ? AND pkgs.name IS NULL
                    )""", (container_name, container_name))
            # delete packages for the container in any case even for shared root since there
            # may be packages that are not orphans
            cursor.execute("DELETE FROM packages WHERE container = ?", (container_name,))
            if commit:
                self.__conn.commit()
            return row is not None

    def get_container_configuration(self, container_name: str) -> Optional[Tuple[str, str]]:
        """
        Get the INI configuration file contents for the container.

        :param container_name: name of the container
        :return: configuration of the container in INI format
        """
        with closing(self.__conn.execute("SELECT distribution, configuration FROM containers "
                                         "WHERE name = ?", (container_name,))) as cursor:
            row = cursor.fetchone()
            return (str(row[0]), str(row[1])) if row else None

    def register_package(self, container_name: str, package: str, shared_root: str,
                         local_copies: list[str], package_type: str = "") -> None:
        """
        Register a package as being owned by a container.

        :param container_name: name of the container
        :param package: the package to be registered
        :param shared_root: the local shared root directory if 'shared_root' flag is enabled
                            for the container
        :param local_copies: map of package name to list of locally copied files (typically
                             desktop files and binary executables that invoke container ones)
        :param package_type: additional type information for the above package, if any
        """

        if not package:
            print_error("Empty package provided to register_package!")
            return

        args = (package, container_name, shared_root, ";".join(local_copies), package_type)
        self.__begin_transaction()
        # first delete any old entry for the package+container
        self.__conn.execute("DELETE FROM packages WHERE name = ? and container = ?",
                            (package, container_name))
        self.__conn.execute("INSERT INTO packages VALUES (?, ?, ?, ?, ?)", args)
        # find the orphan packages with the same shared_root and delete them
        if shared_root:
            self.__conn.execute("DELETE FROM packages WHERE name = ? AND container = '' AND "
                                "shared_root = ?", (package, shared_root))
        self.__conn.commit()

    @staticmethod
    def optional_package_type(package: str) -> str:
        """get the package type value to use for an optional dependency"""
        return f"optional({package})"

    def unregister_package(self, container_name: str, package: str,
                           shared_root: str) -> None:
        """
        Unregister a package for a given container.

        :param container_name: name of the container
        :param package: the package to be unregistered
        :param shared_root: the local shared root directory if 'shared_root' flag is enabled
                            for the container
        """
        self.__begin_transaction()
        # The shared root ones of a distribution all need to disappear (including orphans)
        # regardless of container if this container is on the same shared root.
        if shared_root:
            self.__conn.execute("DELETE FROM packages WHERE name = ? AND shared_root = ?",
                                (package, shared_root))
        else:
            self.__conn.execute("DELETE FROM packages WHERE name = ? AND container = ?",
                                (package, container_name))
        self.__conn.commit()

    def get_packages(self, container_name: Optional[str] = None, regex: str = ".*") -> list[str]:
        """
        Get the list of registered packages. This can be filtered for a specific container
        and/or using a (python) regular expression pattern.

        :param container_name: optional name of the container to filter packages
        :param regex: regular expression pattern to match against package names
        :return: list of registered packages matching the given criteria
        """
        predicate = ""
        args: list[str] = []
        if container_name:
            predicate = "container = ? AND "
            args = [container_name]
        if regex == ".*":
            predicate += "1=1"
        else:
            predicate += "name REGEXP ?"
            args.append(regex)
        with closing(self.__conn.cursor()) as cursor:
            cursor.execute(
                f"SELECT DISTINCT(name) FROM packages WHERE {predicate} ORDER BY name ASC", args)
            return [row[0] for row in cursor.fetchall()]

    def close(self) -> None:
        """Close the underlying connection to the database."""
        self.__conn.rollback()  # rollback any pending transactions
        self.__conn.close()

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_value, ex_traceback):
        try:
            if ex_type:
                self.__conn.rollback()
            else:
                self.__conn.commit()
        finally:
            self.__conn.close()
