"""
Script to create a test database for migration tests for older versions of the product.

To use this script, checkout the older version of the product, then copy and run this
script from the top-level directory. Something like:

```
# for "v0.9.6" substitute the required version below
git clone -b v0.9.6 https://github.com/sumwale/ybox.git
cd ybox
/bin/rm -rf tests src/ybox/conf/profiles
/bin/cp -rf <latest ybox>/tests .
/bin/cp -rf <latest ybox>/src/ybox/conf/profiles src/ybox/conf/
PYTHONPATH=./src /usr/bin/python3 ./tests/create_migration_db.py \
    <latest ybox>/tests/resources/migration/
```
Then add the new version in the `@pytest.mark.parametrize` annotation of `test_migration`
in `test_state.py`
"""

import argparse
import gzip
import inspect
import os
import site
import tempfile
from configparser import ConfigParser
from itertools import chain
from uuid import uuid4

from unit.util import read_containers_and_packages

import ybox
from ybox.env import Environ
from ybox.print import print_warn
from ybox.state import YboxStateManagement


def create_temp_ybox_data_dir(temp_dir: str) -> str:
    """create temporary directory for the state database"""
    os.makedirs(f"{temp_dir}/share/ybox", mode=0o750)
    site.USER_BASE = None
    os.environ["PYTHONUSERBASE"] = temp_dir
    return temp_dir


def populate_db(temp_dir: str) -> None:
    """populate the state with some common data using `YboxStateManagement` API"""
    # pylint: disable=no-value-for-parameter
    env = Environ()
    # check for arguments to `register_package` that are not present in old versions
    register_pkg_params = inspect.signature(YboxStateManagement.register_package).parameters
    # load container and packages information from json files
    fetch_types = bool(register_pkg_params.get("copy_type"))
    # do not interpolate the data since environment can change between the one used to create
    # the database and the one used to run the tests
    active_containers, destroy_containers, container_pkgs = read_containers_and_packages(
        env, fetch_types=fetch_types, interpolate=False)
    with YboxStateManagement(env) as state:
        assert os.access(f"{temp_dir}/share/ybox/state.db", os.W_OK)
        for rt_info in chain(active_containers, destroy_containers.values()):
            container = rt_info.name
            # first register the container checking for new argument not present in old versions
            assert isinstance(rt_info.ini_config, ConfigParser)
            if inspect.signature(state.register_container).parameters.get("force_own_orphans"):
                state.register_container(
                    container_name=container, distribution=rt_info.distribution,
                    shared_root=rt_info.shared_root, parser=rt_info.ini_config,
                    force_own_orphans=True)
            else:
                state.register_container(
                    container_name=container, distribution=rt_info.distribution,
                    shared_root=rt_info.shared_root, parser=rt_info.ini_config)

            for pkg_details in container_pkgs[container]:
                pkg = pkg_details.name
                if fetch_types:
                    assert pkg_details.copy_type is not None
                    if register_pkg_params.get("app_flags"):
                        state.register_package(
                            container_name=container, package=pkg,
                            shared_root=rt_info.shared_root, local_copies=pkg_details.local_copies,
                            copy_type=pkg_details.copy_type, app_flags=pkg_details.app_flags,
                            dep_type=pkg_details.dep_type, dep_of=pkg_details.dep_of)
                    elif register_pkg_params.get("shared_root"):
                        state.register_package(
                            container_name=container, package=pkg,
                            shared_root=rt_info.shared_root, local_copies=pkg_details.local_copies,
                            copy_type=pkg_details.copy_type, dep_type=pkg_details.dep_type,
                            dep_of=pkg_details.dep_of)  # type: ignore
                    else:
                        state.register_package(
                            container_name=container, package=pkg,
                            local_copies=pkg_details.local_copies, copy_type=pkg_details.copy_type,
                            dep_type=pkg_details.dep_type,
                            dep_of=pkg_details.dep_of)  # type: ignore
                else:
                    state.register_package(
                        container_name=container, package=pkg, shared_root=rt_info.shared_root,
                        local_copies=pkg_details.local_copies)  # type: ignore

            if container in destroy_containers:
                state.unregister_container(container)


def copy_db_to_destination(temp_dir: str, dest_dir: str, force: bool) -> None:
    """copy the state database file to given destination and delete the temporary directory"""
    dest_dir = dest_dir.rstrip("/")
    os.makedirs(dest_dir, mode=0o750, exist_ok=True)
    try:
        version = ybox.__version__
    except AttributeError:
        # only 0.9.0 had version in pyproject.toml rather than in ybox.__version__
        version = "0.9.0"
    dest_state_db = f"{dest_dir}/{version}.db.gz"
    if not force and os.path.exists(dest_state_db):
        new_db = f"{dest_dir}/{uuid4()}.db.gz"
        print_warn(f"Destination file {dest_state_db} already exists, hence copying to {new_db}")
        dest_state_db = new_db
    # copy with compression
    block_size = 4 * 1024 * 1024
    with open(f"{temp_dir}/share/ybox/state.db", "rb") as db_in, gzip.open(
            dest_state_db, mode="wb", compresslevel=9) as gz_out:
        while data := db_in.read(block_size):
            gz_out.write(data)


def main() -> None:
    """main entrypoint of the script that parses arguments and creates the state database"""
    parser = argparse.ArgumentParser(
        description="create a sample state database and copy to the given destination")
    parser.add_argument("-f", "--force", action="store_true",
                        help="force overwrite the destination database file if it exists")
    parser.add_argument("destination", type=str,
                        help="destination directory where the state database has to be copied")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp_dir:
        create_temp_ybox_data_dir(temp_dir)
        populate_db(temp_dir)
        copy_db_to_destination(temp_dir, args.destination, args.force)


if __name__ == "__main__":
    main()
