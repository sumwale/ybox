"""Unit tests for `ybox/state.py`"""

import gzip
import json
import os
import re
import shutil
import site
import stat
from collections import defaultdict
from configparser import ConfigParser
from io import StringIO
from itertools import chain
from pathlib import Path
from sqlite3 import DatabaseError
from typing import Any, Iterable
from uuid import uuid4

import pytest
from unit.util import (RESOURCES_DIR, ContainerDetails, PackageDetails,
                       read_containers_and_packages)

from ybox.config import Consts
from ybox.env import Environ
from ybox.state import RuntimeConfiguration, YboxStateManagement

_USER_BASE = f"/tmp/ybox-test-local-{uuid4()}"


@pytest.fixture(name="g_env", scope="module")
def create_env():
    """create an instance of :class:`Environ` used by the tests"""
    # use a custom PYTHONUSERBASE so that database and other files do not overwrite user's location
    site.USER_BASE = None
    os.makedirs(_USER_BASE)
    os.environ["PYTHONUSERBASE"] = _USER_BASE
    yield Environ()

    del os.environ["PYTHONUSERBASE"]
    shutil.rmtree(_USER_BASE)
    site.USER_BASE = None


def clear_database(state: YboxStateManagement) -> None:
    """clear all objects in the `state` database"""
    for cnt in state.get_containers(include_destroyed=True):
        conf = state.get_container_configuration(cnt)
        assert conf is not None
        assert conf.name == cnt
        cnt_or_shared_root = conf.shared_root or cnt
        for repo_info in state.get_repositories(cnt_or_shared_root):
            assert state.unregister_repository(repo_info[0], cnt_or_shared_root) is not None
        for pkg in state.get_packages(cnt):
            state.unregister_package(cnt, pkg, conf.shared_root)
        state.unregister_container(cnt)


@pytest.fixture(name="state")
def create_state(g_env: Environ):
    """Fixture to create an instance of YboxStateManagement."""
    with YboxStateManagement(g_env) as state:
        yield state
        # clean slate at the end of a test
        clear_database(state)


@pytest.fixture(name="container_details", scope="module")
def read_container_details(g_env: Environ) -> ContainerDetails:
    """
    Read container and package details from the test json files and return as `ContainerDetails`.
    """
    return read_containers_and_packages(g_env, fetch_types=True, interpolate=True)


def test_initialization(g_env: Environ, state: YboxStateManagement):
    """test the initialization of :class:`YboxStateManagement`"""
    assert isinstance(state, YboxStateManagement)
    assert g_env.data_dir == f"{_USER_BASE}/share/ybox"
    assert stat.S_IMODE(os.stat(g_env.data_dir).st_mode) == Consts.default_directory_mode()
    assert os.access(f"{g_env.data_dir}/state.db", os.R_OK)
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


@pytest.mark.parametrize(
    "old_version", ["0.9.0", "0.9.1", "0.9.2", "0.9.5", "0.9.6", "0.9.7", "0.9.10"])
def test_migration(g_env: Environ, old_version: str):
    """
    Test migration of state database from older product version to current.
    See file comments in `tests/create_migration_db.py` for an example of how to add a new version.
    """
    # copy old version to the one that will be used by default in the test
    os.makedirs(g_env.data_dir, mode=0o750, exist_ok=True)
    state_db = f"{g_env.data_dir}/state.db"
    Path(state_db).unlink(missing_ok=True)
    # copy with decompression
    block_size = 1024 * 1024
    with gzip.open(f"{RESOURCES_DIR}/migration/{old_version}.db.gz",
                   mode="rb") as gz_in, open(state_db, "wb") as db_out:
        while data := gz_in.read(block_size):
            db_out.write(data)
    # load container and packages data without interpolation like in create_migration_db.py
    active_containers, destroy_containers, container_pkgs = read_containers_and_packages(
        g_env, fetch_types=True, interpolate=False)
    with YboxStateManagement(g_env) as state:
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
        clear_database(state)


def register_containers_and_packages(state: YboxStateManagement,
                                     containers: Iterable[RuntimeConfiguration],
                                     container_pkgs: dict[str, list[PackageDetails]]) -> None:
    """
    Register containers in the `state` database and then register packages against the containers.

    :param state: instance of `YboxStateManagement` having the state database
    :param containers: an `Iterable` of `RuntimeConfiguration` for each container to be registered
    :param container_pkgs: a dictionary of container name to the list of `PackageDetails` for each
                           package to be registered for the container
    """
    for cnt in containers:
        assert isinstance(cnt.ini_config, ConfigParser)
        assert state.register_container(cnt.name, cnt.distribution, cnt.shared_root,
                                        cnt.ini_config, force_own_orphans=False) == {}
        for pkg in container_pkgs.get(cnt.name, []):
            assert pkg.copy_type is not None
            for local_copy in pkg.local_copies:
                if os.access(os.path.dirname(local_copy), os.W_OK):
                    Path(local_copy).touch(mode=0o750, exist_ok=True)
            state.register_package(cnt.name, pkg.name, pkg.local_copies, pkg.copy_type,
                                   pkg.app_flags, pkg.shared_root, pkg.dep_type, pkg.dep_of)


def check_containers(state: YboxStateManagement,
                     containers: Iterable[RuntimeConfiguration]) -> None:
    """
    Assert that the current set of registered containers matches the given containers.

    :param state: instance of `YboxStateManagement` having the state database
    :param containers: an `Iterable` of `RuntimeConfiguration` for each container that should have
                       already been registered (should have no duplicates)
    """
    assert state.get_containers() == sorted([c.name for c in containers])


def check_container_details(state: YboxStateManagement,
                            containers: Iterable[RuntimeConfiguration],
                            avail_containers: list[RuntimeConfiguration],
                            container_pkgs: dict[str, list[PackageDetails]],
                            destroyed: bool) -> None:
    """
    Check installed packages and other shared containers for the given containers.

    :param state: instance of `YboxStateManagement` having the state database
    :param containers: an `Iterable` of `RuntimeConfiguration` for each container to be checked
    :param avail_containers: a list of `RuntimeConfiguration` of all registered containers
    :param container_pkgs: a dictionary of container name to the list of `PackageDetails` for each
                           package that have been registered for the container
    :param destroyed: if True, then the `containers` have been destroyed (i.e. unregistered)
                      and the method will check for absence of those containers
    """
    for cnt in containers:
        assert state.get_packages(cnt.name) == \
            ([] if destroyed else [pkg.name for pkg in container_pkgs.get(cnt.name, [])])
        assert state.get_other_shared_containers(cnt.name, cnt.shared_root) == \
            sorted([c.name for c in avail_containers if c.shared_root and cnt.name != c.name and
                    cnt.shared_root == c.shared_root])
        assert state.get_repositories(cnt.name) == []
        assert state.get_repositories(cnt.shared_root) == []


def test_register_unregister_container(state: YboxStateManagement,
                                       container_details: ContainerDetails):
    """test registration and unregistration of containers"""
    active_containers, destroy_containers, _ = container_details
    all_containers = list(chain(active_containers, destroy_containers.values()))
    for cnt in all_containers:
        assert isinstance(cnt.ini_config, ConfigParser)
        assert state.register_container(cnt.name, cnt.distribution, cnt.shared_root,
                                        cnt.ini_config, force_own_orphans=False) == {}
        with StringIO() as config:
            cnt.ini_config.write(config)
            config.flush()
            profile_str = config.getvalue()
        assert state.get_container_configuration(cnt.name) == RuntimeConfiguration(
            cnt.name, cnt.distribution, cnt.shared_root, profile_str)
    check_containers(state, all_containers)
    for name in destroy_containers:
        assert state.unregister_container(name) is True
    check_containers(state, active_containers)
    for cnt in active_containers:
        assert state.unregister_container(cnt.name) is True
    assert state.get_containers() == []


def test_register_container_and_packages(state: YboxStateManagement,
                                         container_details: ContainerDetails):
    """
    Test the registration of containers with packages with the following cases:
      * register some containers and packages for each, and check the results
      * unregister some containers and register again with some profile changes such that the new
        container is still "equivalent" to previous one, then orphaned packages should
        automatically get assigned to the new container (and check for the same)
      * unregister some containers and register again with some profile changes such that the new
        container is not "equivalent" to the previous one, then orphaned packages should remain
        as before
      * try the previous step again with `force_own_orphans` parameter as `True` in registration
        that should reassign all the orphaned packages to the new container
    """
    # register the containers and packages, then destroy the ones marked for "destroy"

    active_containers, destroy_containers, container_pkgs = container_details
    all_containers = list(chain(active_containers, destroy_containers.values()))
    register_containers_and_packages(state, all_containers, container_pkgs)
    check_containers(state, all_containers)
    check_container_details(state, all_containers, all_containers, container_pkgs, destroyed=False)
    # unregister the containers marked for destroy, then register again with some profile changes
    # which should not affect equivalence of containers so packages should get automatically
    # assigned to the new containers (for shared_root case)
    for cnt in destroy_containers.values():
        assert state.unregister_container(cnt.name) is True
        check_container_details(state, (cnt,), all_containers, container_pkgs, destroyed=True)
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
            check_container_details(state, (cnt,), all_containers, container_pkgs, destroyed=False)
        else:
            register_containers_and_packages(state, (cnt,), container_pkgs)
    # unregister the containers marked for destroy, then register again with some profile changes
    # which will affect equivalence of containers so packages should remain as orphans, then
    # re-register with "force_own_orphans=True" which should remove the orphans
    for cnt in destroy_containers.values():
        assert state.unregister_container(cnt.name) is True
        check_container_details(state, (cnt,), all_containers, container_pkgs, destroyed=True)
        config = cnt.ini_config
        assert isinstance(config, ConfigParser)
        config["base"]["x11"] = "false"
        if cnt.shared_root:
            assert state.register_container(cnt.name, cnt.distribution, cnt.shared_root,
                                            config, force_own_orphans=False) == {}
            pkgs_orig = container_pkgs[cnt.name]
            container_pkgs[cnt.name] = []
            check_container_details(state, (cnt,), all_containers, container_pkgs, destroyed=False)
            assert state.unregister_container(cnt.name) is True
            check_container_details(state, (cnt,), all_containers, container_pkgs, destroyed=True)
            container_pkgs[cnt.name] = pkgs_orig
            expected_packages = {pkg.name: (pkg.copy_type, pkg.app_flags) for pkg in pkgs_orig}
            assert state.register_container(cnt.name, cnt.distribution, cnt.shared_root,
                                            config, force_own_orphans=True) == expected_packages
            check_container_details(state, (cnt,), all_containers, container_pkgs, destroyed=False)
        else:
            register_containers_and_packages(state, (cnt,), container_pkgs)

    check_containers(state, all_containers)
    check_container_details(state, all_containers, all_containers, container_pkgs, destroyed=False)


def test_unregister_package(state: YboxStateManagement, container_details: ContainerDetails):
    """test unregistration of packages"""
    active_containers, destroy_containers, container_pkgs = container_details
    all_containers = list(chain(active_containers, destroy_containers.values()))
    register_containers_and_packages(state, all_containers, container_pkgs)
    check_containers(state, all_containers)
    check_container_details(state, all_containers, all_containers, container_pkgs, destroyed=False)
    for name in destroy_containers:
        assert state.unregister_container(name) is True
    # check containers and their packages for both the registered containers and unregistered ones
    check_container_details(state, active_containers, active_containers,
                            container_pkgs, destroyed=False)
    check_container_details(state, destroy_containers.values(),
                            active_containers, container_pkgs, destroyed=True)
    for cnt in active_containers:
        # unregister the packages one at a time and check
        pkgs: list[PackageDetails] = list(container_pkgs[cnt.name])  # make a copy of the list
        while pkgs:
            pkg, *pkgs = pkgs
            orphan_deps = {p.name: p.dep_type for p in pkgs if p.dep_of == pkg.name}
            assert state.unregister_package(cnt.name, pkg.name, pkg.shared_root) == orphan_deps
            assert pkg.name not in state.get_packages(cnt.name)
        assert state.get_packages(cnt.name) == []
    check_container_details(state, active_containers, active_containers, {}, destroyed=False)


def test_fetch_packages(state: YboxStateManagement, container_details: ContainerDetails):
    """check the registered packages using `get_packages` and `check_packages` APIs"""
    active_containers, destroy_containers, container_pkgs = container_details
    all_containers = list(chain(active_containers, destroy_containers.values()))
    register_containers_and_packages(state, all_containers, container_pkgs)
    all_pkgs = {p.name: p.dep_type for pl in container_pkgs.values() for p in pl}
    assert state.get_packages("") == sorted(all_pkgs)
    re_pats = (r".+m.*", r"^[fh].*$")
    for pat in re_pats:
        assert state.get_packages("", pat) == sorted(
            [pkg for pkg in all_pkgs if re.fullmatch(pat, pkg)])
        assert state.get_packages("", pat, "") == sorted(
            [pkg for pkg, dep_tp in all_pkgs.items() if re.fullmatch(pat, pkg) and not dep_tp])
        assert state.get_packages("", pat, "optional") == sorted(
            [pkg for pkg, dep_tp in all_pkgs.items()
             if re.fullmatch(pat, pkg) and dep_tp and dep_tp == "optional"])
    for cnt in all_containers:
        cnt_pkgs = container_pkgs[cnt.name]
        assert state.get_packages(cnt.name) == sorted([p.name for p in cnt_pkgs])
        assert set(state.check_packages(cnt.name, all_pkgs.keys())) == {p.name for p in cnt_pkgs}
        assert state.check_packages(cnt.name, []) == []
        for pat in re_pats:
            assert state.get_packages(cnt.name, pat, "") == sorted(
                [p.name for p in cnt_pkgs if re.fullmatch(pat, p.name) and not p.dep_type])
            assert state.get_packages(cnt.name, pat, "optional") == sorted(
                [p.name for p in cnt_pkgs
                 if re.fullmatch(pat, p.name) and p.dep_type and p.dep_type.value == "optional"])


def test_repository(state: YboxStateManagement, container_details: ContainerDetails):
    """test registration and unregistration of repositories"""
    with open(f"{RESOURCES_DIR}/repos.json", "r", encoding="utf-8") as repos_fd:
        repos: dict[str, dict[str, Any]] = json.load(repos_fd)
    active_containers, destroy_containers, _ = container_details
    all_containers = {c.name: c for c in chain(active_containers, destroy_containers.values())}
    container_repos = defaultdict[str, dict[str, tuple[str, str, str, str, bool]]](
        dict[str, tuple[str, str, str, str, bool]])
    for name, info in repos.items():
        for cnt in info["containers"]:
            cnt_or_shared_root = all_containers[cnt].shared_root or cnt
            urls = ",".join(info["urls"])
            key = info["key"]
            options = info["options"]
            source_repo = info["with_source_repo"]
            cnt_repos = container_repos[cnt_or_shared_root]
            assert state.register_repository(name, cnt_or_shared_root, urls, key, options,
                                             source_repo, update=False) == (name not in cnt_repos)
            assert state.register_repository(name, cnt_or_shared_root, urls, key, options,
                                             source_repo, update=True)
            cnt_repos[name] = (name, urls, key, options, source_repo)
    for cnt in all_containers.values():
        if cnt.shared_root:
            assert state.get_repositories(cnt.name) == []
            assert state.get_repositories(cnt.shared_root) == sorted(
                container_repos[cnt.shared_root].values(), key=lambda t: t[0])
        else:
            assert state.get_repositories(cnt.name) == sorted(
                container_repos[cnt.name].values(), key=lambda t: t[0])
    for cnt, repo_map in container_repos.items():
        for repo in repo_map.values():
            assert state.unregister_repository(repo[0], cnt) == (repo[2], repo[4])
            assert state.unregister_repository(repo[0], cnt) is None
    for cnt in all_containers.values():
        cnt_or_shared_root = cnt.shared_root or cnt.name
        assert state.get_repositories(cnt_or_shared_root) == []


def test_transaction_commit(g_env: Environ, state: YboxStateManagement,
                            container_details: ContainerDetails):
    """test explicit transaction begin and commit"""
    active_containers, _, _ = container_details
    with YboxStateManagement(g_env, connect_timeout=2.0) as state2:
        # first check without explicit transaction
        for cnt in active_containers:
            assert isinstance(cnt.ini_config, ConfigParser)
            assert state.register_container(cnt.name, cnt.distribution, cnt.shared_root,
                                            cnt.ini_config, force_own_orphans=False) == {}
        # should be immediately visible in both sessions
        check_containers(state, active_containers)
        check_containers(state2, active_containers)
        for cnt in active_containers:
            assert state.unregister_container(cnt.name) is True
        assert state.get_containers() == []
        assert state2.get_containers() == []

        # now check with explicit transaction
        state.begin_transaction()
        for cnt in active_containers:
            assert isinstance(cnt.ini_config, ConfigParser)
            assert state.register_container(cnt.name, cnt.distribution, cnt.shared_root,
                                            cnt.ini_config, force_own_orphans=False) == {}
        check_containers(state, active_containers)
        # should fail with timeout in the other session due to EX lock
        pytest.raises(DatabaseError, state2.get_containers)
        state.commit()
        check_containers(state, active_containers)
        check_containers(state2, active_containers)


def test_transaction_rollback(g_env: Environ, container_details: ContainerDetails):
    """test explicit transaction begin and rollback on an exception or on explicit rollback"""
    active_containers, _, _ = container_details
    with YboxStateManagement(g_env, connect_timeout=2.0) as state:
        try:
            with YboxStateManagement(g_env) as state2:
                # check with explicit transaction and rollback
                state2.begin_transaction()
                for cnt in active_containers:
                    assert isinstance(cnt.ini_config, ConfigParser)
                    assert state2.register_container(cnt.name, cnt.distribution, cnt.shared_root,
                                                     cnt.ini_config, force_own_orphans=False) == {}
                check_containers(state2, active_containers)
                # should fail with timeout in the other session due to EX lock
                pytest.raises(DatabaseError, state.get_containers)
                state2.rollback()
                assert state.get_containers() == []
                assert state2.get_containers() == []
                # now check rollback with a forced exception
                state2.begin_transaction()
                for cnt in active_containers:
                    assert isinstance(cnt.ini_config, ConfigParser)
                    assert state2.register_container(cnt.name, cnt.distribution, cnt.shared_root,
                                                     cnt.ini_config, force_own_orphans=False) == {}
                raise RuntimeError("fail")
        except RuntimeError as err:
            assert str(err) == "fail"
        # verify that the containers are not registered due to implicit rollback
        assert state.get_containers() == []


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
