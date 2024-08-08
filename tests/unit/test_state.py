"""
Unit tests for `ybox/state.py`

General guideline: use mock **only if absolutely necessary** (e.g. for unexpected error
    conditions that are difficult to simulate in tests or will cause other trouble).
  Database used is sqlite, but that is an internal detail and could potentially change
  so mocking sqlite3 objects is a really bad idea. Just test for public API of `ybox.state`.
"""

import gzip
import os
import shutil
import site
import stat
from configparser import ConfigParser
from io import StringIO
from itertools import chain
from pathlib import Path
from typing import Iterable
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from unit.util import read_containers_and_packages

from ybox.config import Consts
from ybox.env import Environ
from ybox.state import CopyType, RuntimeConfiguration, YboxStateManagement

_USER_BASE = f"/tmp/ybox-test-local-{uuid4()}"
_USER_DATA_DIR = f"{_USER_BASE}/share/ybox"


@pytest.fixture(name="env")
def create_env():
    """create an instance of :class:`Environ` used by the tests"""
    # use a custom PYTHONUSERBASE so that database and other files do not overwrite user's location
    site.USER_BASE = None
    os.makedirs(_USER_BASE)
    os.environ["PYTHONUSERBASE"] = _USER_BASE
    yield Environ()

    del os.environ["PYTHONUSERBASE"]
    shutil.rmtree(_USER_BASE)


@pytest.fixture(name="state")
def create_state(env: Environ):
    """Fixture to create an instance of YboxStateManagement."""
    with YboxStateManagement(env) as ybox:
        yield ybox


def test_initialization(env: Environ, state: YboxStateManagement):
    """test the initialization of :class:`YboxStateManagement`"""
    assert isinstance(state, YboxStateManagement)
    assert env.data_dir == _USER_DATA_DIR
    assert stat.S_IMODE(os.stat(env.data_dir).st_mode) == Consts.default_directory_mode()
    assert os.access(f"{_USER_DATA_DIR}/state.db", os.R_OK)
    # check empty state
    container = "ybox-container"
    shared_root = "/non-existent"
    assert state.get_containers() == []
    assert state.get_container_configuration(container) is None
    assert state.get_other_shared_containers(container, shared_root) == []
    assert state.get_other_shared_containers(container, "") == []
    assert state.get_repositories(container) == []
    assert state.get_repositories(shared_root) == []
    assert state.get_repositories("") == []
    assert state.get_packages(container) == []


@pytest.mark.parametrize("old_version", ["0.9.0", "0.9.1", "0.9.2", "0.9.5", "0.9.6"])
def test_migration(env: Environ, old_version: str):
    """
    Test migration of state database from older product version to current.
    See file comments in `tests/create_migration_db.py` for an example of how to add a new version.
    """
    # copy old version to the one that will be used by default in the test
    os.makedirs(_USER_DATA_DIR, mode=0o750)
    state_db = f"{_USER_DATA_DIR}/state.db"
    Path(state_db).unlink(missing_ok=True)
    # copy with decompression
    block_size = 4 * 1024 * 1024
    with gzip.open(f"{os.path.dirname(__file__)}/../resources/migration/{old_version}.db.gz",
                   mode="rb") as gz_in, open(state_db, "wb") as db_out:
        while data := gz_in.read(block_size):
            db_out.write(data)
    # load container and packages data
    active_containers, destroy_containers, container_pkgs = read_containers_and_packages(
        env, fetch_types=True, interpolate=False)
    with YboxStateManagement(env) as state:
        assert os.access(state_db, os.W_OK)
        # check expected state for test data files
        assert state.get_containers() == sorted([c.name for c in active_containers])
        for rt_info in active_containers:
            name = rt_info.name
            shared_root = rt_info.shared_root
            assert isinstance(rt_info.ini_config, ConfigParser)
            with StringIO() as config:
                rt_info.ini_config.write(config)
                config.flush()
                profile_str = config.getvalue()
            assert state.get_container_configuration(name) == RuntimeConfiguration(
                name, rt_info.distribution, shared_root, profile_str)
            assert state.get_other_shared_containers(name, shared_root) == \
                sorted([cnt.name for cnt in active_containers
                        if shared_root and cnt.name != name and shared_root == cnt.shared_root])
            assert state.get_repositories(name) == []
            assert state.get_repositories(shared_root) == []
            assert state.get_packages(name) == [pkg.name for pkg in container_pkgs[name]]
        for name, rt_info in destroy_containers.items():
            shared_root = rt_info.shared_root
            assert state.get_container_configuration(name) is None
            assert state.get_other_shared_containers(name, shared_root) == \
                sorted([cnt.name for cnt in active_containers
                        if shared_root and cnt.name != name and shared_root == cnt.shared_root])
            assert state.get_repositories(name) == []
            assert state.get_repositories(shared_root) == []
            assert state.get_packages(name) == []


def test_register_container(env: Environ, state: YboxStateManagement):
    """test the registration of new containers"""
    active_containers, destroy_containers, container_pkgs = read_containers_and_packages(
        env, fetch_types=True, interpolate=True)
    # register the containers and packages, then destroy the ones marked for "destroy"

    def register_containers_and_packages(containers: Iterable[RuntimeConfiguration]) -> None:
        for cnt in containers:
            assert isinstance(cnt.ini_config, ConfigParser)
            assert state.register_container(cnt.name, cnt.distribution, cnt.shared_root,
                                            cnt.ini_config, force_own_orphans=False) == {}
            for pkg in container_pkgs[cnt.name]:
                assert pkg.copy_type is not None
                state.register_package(cnt.name, pkg.name, pkg.local_copies, pkg.copy_type,
                                       pkg.app_flags, pkg.shared_root, pkg.dep_type, pkg.dep_of)
                if pkg.dep_type:
                    assert pkg.dep_of
                    state.register_dependency(cnt.name, pkg.dep_of, pkg.name, pkg.dep_type)

    def check_containers(containers: Iterable[RuntimeConfiguration]) -> None:
        assert state.get_containers() == sorted([c.name for c in containers])

    def check_container_details(containers: Iterable[RuntimeConfiguration],
                                destroyed: bool) -> None:
        for cnt in containers:
            assert state.get_packages(cnt.name) == \
                ([] if destroyed else [pkg.name for pkg in container_pkgs[cnt.name]])
            assert state.get_other_shared_containers(cnt.name, cnt.shared_root) == \
                ([] if destroyed else sorted(
                    [c.name for c in all_containers if c.shared_root and cnt.name != c.name and
                     cnt.shared_root == c.shared_root]))
            assert state.get_repositories(cnt.name) == []
            assert state.get_repositories(cnt.shared_root) == []

    all_containers = list(chain(active_containers, destroy_containers.values()))
    register_containers_and_packages(all_containers)
    check_containers(all_containers)
    check_container_details(all_containers, destroyed=False)
    # unregister the containers marked for destroy, then register again with some profile changes
    # which should not affect equivalence of containers so packages should get automatically
    # assigned to the new containers (for shared_root case)
    for cnt in destroy_containers.values():
        assert state.unregister_container(cnt.name)
        config = cnt.ini_config
        assert isinstance(config, ConfigParser)
        config["base"]["home"] = "/non-existent"
        config.remove_option("base", "log_opts")
        config.remove_section("env")
        if cnt.shared_root:
            expected_packages = {pkg.name: (pkg.copy_type, pkg.app_flags)
                                 for pkg in container_pkgs[cnt.name]}
            assert state.register_container(cnt.name, cnt.distribution, cnt.shared_root,
                                            config, force_own_orphans=False) == expected_packages
            check_container_details((cnt,), destroyed=False)
        else:
            register_containers_and_packages((cnt,))

    check_containers(all_containers)
    check_container_details(all_containers, destroyed=False)


def test_unregister_container(state: YboxStateManagement):
    """test unregisteration of a container"""
    mock_parser = MagicMock(spec=ConfigParser)
    container_name = "test_unregistered_container"
    distribution = "test_distro"
    shared_root = "/mock/shared_root"

    state.register_container(container_name, distribution, shared_root, mock_parser, False)
    result = state.unregister_container(container_name)

    assert result is True  # Container should be found and removed


def test_register_package(state: YboxStateManagement):
    """test registeration of a new package"""
    mock_parser = MagicMock(spec=ConfigParser)
    container_name = "test_container"
    package = "test_package"
    local_copies = ["local_copy_1", "local_copy_2"]
    copy_type = CopyType(0)  # Sample value
    app_flags: dict[str, str] = {}
    shared_root = "/mock/shared_root"

    state.register_container(container_name, "test_distro", shared_root, mock_parser, False)
    state.register_package(container_name, package, local_copies, copy_type,
                           app_flags, shared_root, None, "", False)

    # Check if the package is registered correctly
    packages = state.get_packages(container_name)
    assert package in packages


def test_unregister_package(state: YboxStateManagement):
    """test unregisteration of a package"""
    mock_parser = MagicMock(spec=ConfigParser)
    container_name = "test_container"
    package = "test_package"
    local_copies = ["local_copy_1", "local_copy_2"]
    copy_type = CopyType(0)
    app_flags: dict[str, str] = {}
    shared_root = "/mock/shared_root"

    state.register_container(container_name, "test_distro", shared_root, mock_parser, False)
    state.register_package(container_name, package, local_copies, copy_type,
                           app_flags, shared_root, None, "", False)

    # Unregister the package
    state.unregister_package(container_name, package, shared_root)
    assert package not in state.get_packages(container_name)


def test_transaction_commit(state: YboxStateManagement):
    """test explicit commit"""
    mock_parser = MagicMock(spec=ConfigParser)
    container_name = "test_container"
    state.begin_transaction()
    state.register_container(container_name, "test_distro",
                             "/mock/shared_root", mock_parser, False)
    state.commit()

    # Check if the container is registered
    containers = state.get_containers()
    assert container_name in containers


def test_transaction_rollback(state: YboxStateManagement):
    """test rollback on an exception"""
    mock_parser = MagicMock(spec=ConfigParser)
    container_name = "test_container"
    try:
        state.begin_transaction()
        state.register_container(container_name, "test_distro",
                                 "/mock/shared_root", mock_parser, False)
        raise NotImplementedError("Forced Exception")  # Simulating an error
    except NotImplementedError:
        pass
    finally:
        state.rollback()

    # Verify the container is not registered
    assert container_name not in state.get_containers()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
