"""
Classes and methods for bookkeeping the state of zbox containers including the packages
installed on each container explicitly.
"""
import re
import sqlite3
from configparser import ConfigParser
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
        self.__conn = sqlite3.connect(f"{env.data_dir}/state.db", timeout=60)
        # create the initial tables
        try:
            self.__conn.execute("create table containers (name text primary key, "
                                "distribution text, configuration text)")
            self.__conn.execute("create table packages (name text, container text, "
                                "flags text, primary key(name, container))")
            self.__conn.commit()
        except sqlite3.DatabaseError as ex:
            if not re.search("table.*already exists", str(ex), re.IGNORECASE):
                raise

    def add_container(self, container_name: str, distribution: str, parser: ConfigParser) -> None:
        # build the ini string from parser
        with StringIO() as config_str:
            parser.write(config_str)
            config_str.flush()
            self.__conn.execute("insert into containers values (?, ?, ?)",
                                (container_name, distribution, config_str.getvalue()))
            self.__conn.commit()

    def get_container_configuration(self, container_name: str) -> Optional[Tuple[str, str]]:
        cursor = self.__conn.execute("select distribution, configuration from containers "
                                     "where name = ?", (container_name,))
        results = cursor.fetchone()
        cursor.close()
        return (str(results[0]), str(results[1])) if results else None

    def remove_container(self, container_name: str) -> int:
        # build the ini string from parser
        cursor = self.__conn.execute("delete from containers where name = ?", (container_name,))
        self.__conn.commit()
        rowcount = cursor.rowcount
        cursor.close()
        return rowcount

    def close(self) -> None:
        self.__conn.close()

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_value, ex_traceback):
        self.close()
