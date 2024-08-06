"""
Unit tests for `ybox/state.py`

General guideline: use mock **only if absolutely necessary** (e.g. for unexpected error
    conditions that are difficult to simulate in tests or will cause other trouble).
  Database used is sqlite, but that is an internal detail and could potentially change
  so mocking sqlite3 objects is a really bad idea. Just test for public API of `ybox.state`.
"""

import gzip
import json
import os
import shutil
import site
import stat
from configparser import ConfigParser
from importlib.resources import files
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ybox.config import Consts
from ybox.env import Environ
from ybox.state import CopyType, RuntimeConfiguration, YboxStateManagement
from ybox.util import config_reader

_USER_BASE = f"/tmp/ybox-test-local-{uuid4()}"
_USER_DATA_DIR = f"{_USER_BASE}/share/ybox"
_TEST_DISTRIBUTION = "ybox-distro"
_TEST_DISTRIBUTION2 = "ybox-distro2"
_TEST_CONTAINER = "ybox-test"
_TEST_CONTAINER2 = "ybox-test2"
_TEST_CONTAINER_ROOT = f"/tmp/ybox-test-root-{uuid4()}"

_resources_dir = f"{os.path.dirname(__file__)}/../resources/migration"


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
    assert state.get_containers() == []
    assert state.get_container_configuration(_TEST_CONTAINER) is None
    assert state.get_other_shared_containers(_TEST_CONTAINER, _TEST_CONTAINER_ROOT) == []
    assert state.get_repositories(_TEST_CONTAINER) == []
    assert state.get_repositories(_TEST_CONTAINER_ROOT) == []
    assert state.get_packages(_TEST_CONTAINER) == []


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
    with gzip.open(f"{_resources_dir}/{old_version}.db.gz", mode="rb") as gz_in, open(
            state_db, "wb") as db_out:
        while data := gz_in.read(block_size):
            db_out.write(data)
    # load container and packages data
    with open(f"{_resources_dir}/containers.json", "r", encoding="utf-8") as containers_fd:
        containers: dict[str, dict[str, Any]] = json.load(containers_fd)
    with open(f"{_resources_dir}/pkgs.json", "r", encoding="utf-8") as pkgs_fd:
        pkgs: dict[str, dict[str, Any]] = json.load(pkgs_fd)
    # create a mapping of container to the corresponding packages installed on it
    container_pkgs = {cnt: sorted([pkg for pkg, pkg_info in pkgs.items()
                                   if idx == 0 or pkg_info["repeat"]])
                      for idx, cnt in enumerate(containers)}
    with YboxStateManagement(env) as state:
        assert os.access(state_db, os.W_OK)
        # check expected state for test data files
        active_containers = sorted([name for name, info in containers.items()
                                    if not info["destroyed"]])
        destroyed_containers = [name for name, info in containers.items() if info["destroyed"]]
        assert state.get_containers() == active_containers
        for name in active_containers:
            info = containers[name]
            shared_root = info["shared_root"]
            profile = files("ybox").joinpath("conf").joinpath(info["profile"])
            parsed_profile = config_reader(profile, interpolation=None)
            if shared_root:
                parsed_profile["base"]["shared_root"] = shared_root
            else:
                del parsed_profile["base"]["shared_root"]
            with StringIO() as config:
                parsed_profile.write(config)
                config.flush()
                profile_str = config.getvalue()
            assert state.get_container_configuration(name) == RuntimeConfiguration(
                name, info["distribution"], shared_root, profile_str)
            assert state.get_other_shared_containers(name, shared_root) == \
                [c for c in active_containers
                 if shared_root and c != name and shared_root == containers[c]["shared_root"]]
            assert state.get_repositories(name) == []
            assert state.get_repositories(shared_root) == []
            assert state.get_packages(name) == container_pkgs.get(name)
        for name in destroyed_containers:
            shared_root = containers[name]["shared_root"]
            assert state.get_container_configuration(name) is None
            assert state.get_other_shared_containers(name, shared_root) == []
            assert state.get_repositories(name) == []
            assert state.get_repositories(shared_root) == []
            assert state.get_packages(name) == []


def test_register_container(state: YboxStateManagement):
    """test the registration of a new container"""
    mock_parser = MagicMock(spec=ConfigParser)
    shared_root = "/mock/shared_root"

    packages = state.register_container(
        _TEST_CONTAINER, _TEST_DISTRIBUTION, shared_root, mock_parser)

    assert packages == {}


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
