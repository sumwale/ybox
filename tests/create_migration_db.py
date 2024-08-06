"""
Script to create a test database for migration and other tests for older versions of the product.

To use this script, checkout the older version of the product, then copy and run this script from
the top-level directory. Something like:

```
git checkout v0.9.6
/bin/cp -rf <current ybox>/tests .
/bin/cp -rf <current ybox>/conf/profiles src/ybox/conf/ .
PYTHONPATH=./src /usr/bin/python3 ./tests/create_migration_db.py \
    <current ybox>/tests/resources/migration/ -f
```
Then add the new version in the `@pytest.mark.parametrize` annotation of `test_migration`
in `test_state.py`
"""

import argparse
import gzip
import inspect
import json
import operator
import os
import site
import tempfile
from functools import reduce
from importlib.resources import files
from typing import Any
from uuid import uuid4

import ybox
import ybox.state as y_state
from ybox.env import Environ
from ybox.print import print_warn
from ybox.state import YboxStateManagement
from ybox.util import config_reader


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
    resources_dir = f"{os.path.dirname(__file__)}/resources/migration"
    # load container information from json file
    with open(f"{resources_dir}/containers.json", encoding="utf-8") as containers_fd:
        containers: dict[str, dict[str, Any]] = json.load(containers_fd)
    with YboxStateManagement(env) as state:
        assert os.access(f"{temp_dir}/share/ybox/state.db", os.W_OK)
        for c_idx, (container, container_info) in enumerate(containers.items()):
            distribution = container_info["distribution"]
            shared_root = container_info["shared_root"]
            profile = files("ybox").joinpath("conf").joinpath(container_info["profile"])
            # don't use EnvInterpolation since it can change as per the test environment
            parsed_profile = config_reader(conf_file=profile, interpolation=None)
            if shared_root:
                # old versions used hard-coded ".../ROOTS/..." for shared_root so use the same
                parsed_profile["base"]["shared_root"] = shared_root
            else:
                del parsed_profile["base"]["shared_root"]
            # first register the container checking for new argument not present in old versions
            if inspect.signature(state.register_container).parameters.get("force_own_orphans"):
                state.register_container(container_name=container, distribution=distribution,
                                         shared_root=shared_root, parser=parsed_profile,
                                         force_own_orphans=True)
            else:
                state.register_container(container_name=container, distribution=distribution,
                                         shared_root=shared_root, parser=parsed_profile)

            # then register packages checking for arguments that are not present in old versions
            register_pkg_params = inspect.signature(state.register_package).parameters
            # load package information from json file
            with open(f"{resources_dir}/pkgs.json", encoding="utf-8") as pkgs_fd:
                pkgs_json: dict[str, dict[str, Any]] = json.load(pkgs_fd)
            for pkg, pkg_info in pkgs_json.items():
                # register packages in all containers only if "repeat" is true
                if c_idx != 0 and not pkg_info["repeat"]:
                    continue
                local_copies = pkg_info["local_copies"]
                if register_pkg_params.get("copy_type"):
                    copy_type = reduce(operator.ior,
                                       [y_state.CopyType[c] for c in pkg_info["copy_type"]],
                                       y_state.CopyType(0))
                    dep_type = pkg_info.get("dep_type")
                    dep_type = y_state.DependencyType[dep_type] if dep_type else None
                    dep_of = pkg_info["dep_of"]
                    if register_pkg_params.get("app_flags"):
                        state.register_package(
                            container_name=container, package=pkg, shared_root=shared_root,
                            local_copies=local_copies, copy_type=copy_type,
                            app_flags=pkg_info["app_flags"], dep_type=dep_type, dep_of=dep_of)
                    elif register_pkg_params.get("shared_root"):
                        state.register_package(
                            container_name=container, package=pkg, shared_root=shared_root,
                            local_copies=local_copies, copy_type=copy_type, dep_type=dep_type,
                            dep_of=dep_of)  # type: ignore
                    else:
                        state.register_package(
                            container_name=container, package=pkg, local_copies=local_copies,
                            copy_type=copy_type, dep_type=dep_type, dep_of=dep_of)  # type: ignore
                else:
                    state.register_package(
                        container_name=container, package=pkg, shared_root=shared_root,
                        local_copies=local_copies)  # type: ignore

            if container_info["destroyed"]:
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
