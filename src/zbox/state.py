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


class ZboxStateManagement:
    """
    Maintain the state of all Zbox containers. This includes:

    1. The full configuration used for the creation of a container.
    2. The packages installed explicitly on each of the containers (though all
         packages may be visible on all containers having 'shared_root' as true)
    3. Cleanup state of containers removed explicitly or those that got stopped/removed.
    """

    def __init__(self, env: Environ):
        """
        Initialize connection to database and create tables+indexes if not present.

        :param env: the current Environ
        """
        self.__conn = sqlite3.connect(f"{env.data_dir}/state.db", timeout=30)
        # create the initial tables
        self.__conn.execute("CREATE TABLE IF NOT EXISTS containers (name TEXT PRIMARY KEY, "
                            "distribution TEXT, shared_root BOOLEAN, configuration TEXT)")
        self.__conn.execute("CREATE TABLE IF NOT EXISTS packages (name TEXT, container TEXT, "
                            "flags TEXT, PRIMARY KEY(name, container)) WITHOUT ROWID")
        self.__conn.execute("CREATE INDEX IF NOT EXISTS package_containers "
                            "ON packages(container)")
        self.__conn.create_function("REGEXP", 2, ZboxStateManagement.regexp)
        self.__conn.commit()

    @staticmethod
    def regexp(pattern: str, val: str) -> int:
        """callable for the user-defined SQL REGEXP function"""
        regex = re.compile(pattern)
        return 1 if regex.search(val) else 0

    def register_container(self, container_name: str, distribution: str, shared_root: bool,
                           parser: ConfigParser) -> None:
        """
        Register information of a zbox container including its name, distribution and configuration.

        :param container_name: name of the container
        :param distribution: the Linux distribution used when creating the container
        :param shared_root: whether 'shared_root' flag is enable for the container
                            (see 'shared_root' key in [base] section in the top-level basic.ini)
        :param parser: parser object for the configuration file used for creating the container
        """
        # build the ini string from parser
        with StringIO() as config:
            parser.write(config)
            config.flush()
            config_str = config.getvalue()
            self.__conn.execute("INSERT INTO containers VALUES (?, ?, ?, ?) ON CONFLICT(name) "
                                "DO UPDATE SET distribution=?, shared_root=?, configuration=?",
                                (container_name, distribution, shared_root, config_str,
                                 distribution, shared_root, config_str))
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
        with closing(self.__conn.cursor()) as cursor:
            cursor.execute("DELETE FROM containers WHERE name = ? RETURNING shared_root",
                           (container_name,))
            row = cursor.fetchone()
        with closing(self.__conn.cursor()) as cursor:
            # if the container has 'shared_root', then package will continue to exist, but we will
            # have to blank out the container name in case there is no other container that
            # references that package
            if row and bool(row[0]):
                # SQL below first finds the packages to be deleted due to the container, then
                # searches for packages that are only in the container and referenced by no other
                # (left outer join will have null values for rows missing from RHS).
                # Value is set to empty rather than null to avoid SQL null related weirdness.
                cursor.execute("""
                    UPDATE packages SET container = '' WHERE name IN (
                        SELECT d_pkgs.name FROM packages d_pkgs LEFT OUTER JOIN
                        (SELECT name FROM packages WHERE container <> ?) pkgs ON
                        (d_pkgs.name = pkgs.name) WHERE d_pkgs.container = ? AND pkgs.name IS NULL
                    )""", (container_name, container_name))
            else:
                # cleanup packages for the container in any case even if row was None
                cursor.execute("DELETE FROM packages WHERE container = ?", (container_name,))
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

    def register_packages(self, container_name: str, packages: list[str],
                          package_flags: str = "") -> None:
        """
        Register one or more packages as owned by a container. Any additional installation time
        flags for the packages may also be provided.

        :param container_name: name of the container
        :param packages: list of packages to be registered
        :param package_flags: additional flags for the above set of packages, if any
        """
        args = [(package, container_name, package_flags, package_flags) for package in packages]
        self.__conn.executemany("INSERT INTO packages VALUES (?, ?, ?) "
                                "ON CONFLICT(name, container) DO UPDATE SET flags=?", args)
        self.__conn.commit()

    def unregister_packages(self, container_name: str, packages: list[str]) -> None:
        """
        Unregister one or more packages for a given container.

        :param container_name: name of the container
        :param packages: list of packages to be unregistered
        """
        args = [(package, container_name) for package in packages]
        self.__conn.executemany("DELETE FROM packages WHERE name = ? AND container = ?", args)
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
        self.__conn.close()

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_value, ex_traceback):
        self.close()
