"""Unit tests for `ybox/env.py`"""

import getpass
import os
import pwd
import re
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from ybox.env import Environ, NotSupportedError, get_docker_command


@pytest.fixture(name="g_env", scope="module")
def create_env() -> Environ:
    """create an instance of :class:`Environ` used by the tests"""
    return Environ()


def test_home_dirs(g_env: Environ):
    """check home and target container user home directories"""
    target_home = f"/home/{getpass.getuser()}" if g_env.uses_podman else "/root"
    assert g_env.home == os.environ["HOME"]
    assert g_env.target_user == (getpass.getuser() if g_env.uses_podman else "root")
    assert os.environ["TARGET_HOME"] == target_home
    assert g_env.target_home == target_home
    # change $HOME for Environ and check again
    new_home = f"/test-env/{getpass.getuser()}"
    env = Environ(home_dir=new_home)
    assert g_env.home != new_home
    assert env.home == new_home
    assert os.environ["TARGET_HOME"] == target_home
    assert env.target_home == target_home


def test_data_dirs(g_env: Environ):
    """check ybox data directory for the host user and container user"""
    data_dir = f"{g_env.home}/.local/share/ybox"
    target_home = f"/home/{getpass.getuser()}" if g_env.uses_podman else "/root"
    target_data_dir = f"{target_home}/.local/share/ybox"
    assert g_env.data_dir == data_dir
    assert g_env.target_data_dir == target_data_dir


def test_other_vars(g_env: Environ):
    """check other misc variables set in `Environ`"""
    assert g_env.systemd_user_conf_dir() == str(Path(os.environ["HOME"],
                                                     ".config", "systemd", "user"))
    try:
        rt_dir = os.environ["XDG_RUNTIME_DIR"]
    except KeyError:
        rt_dir = ""
    user_base = f"{os.environ['HOME']}/.local"
    assert g_env.xdg_rt_dir == rt_dir
    target_uid = pwd.getpwnam(getpass.getuser()).pw_uid if g_env.uses_podman else 0
    assert g_env.target_user == pwd.getpwuid(target_uid).pw_name
    assert g_env.target_xdg_rt_dir == f"/run/user/{target_uid}"
    assert g_env.user_base == user_base
    assert g_env.user_applications_dir == f"{user_base}/share/applications"
    assert g_env.user_executables_dir == f"{user_base}/bin"


def test_now(g_env: Environ):
    """check the `Environ.now` property and $NOW environment variable"""
    env = Environ()
    now = datetime.now()
    assert os.environ["NOW"] == str(env.now)
    assert now >= env.now > g_env.now
    assert env.now + timedelta(milliseconds=10) >= now


def test_get_docker_command(g_env: Environ):
    """check `Environ.get_docker_command` function"""
    docker_cmd = get_docker_command()
    assert docker_cmd is not None
    assert re.match(r"/usr/bin/(podman|docker)", docker_cmd)
    assert os.access(docker_cmd, os.X_OK)
    assert docker_cmd == g_env.docker_cmd
    assert g_env.uses_podman == ("podman" in docker_cmd)
    # try with explicit environment variable
    current_ybox_manager = os.environ.get("YBOX_CONTAINER_MANAGER")
    os.environ["YBOX_CONTAINER_MANAGER"] = "/bin/true"
    try:
        docker_cmd = get_docker_command()
        assert docker_cmd == "/bin/true"
        # creating Environ should fail when checking for rootless docker
        pytest.raises(NotSupportedError, Environ)
        # try with explicit environment variable for a non-existent program or a non-executable
        os.environ["YBOX_CONTAINER_MANAGER"] = "/non-existent"
        pytest.raises(PermissionError, get_docker_command)
        os.environ["YBOX_CONTAINER_MANAGER"] = "/etc/passwd"
        pytest.raises(PermissionError, get_docker_command)

        del os.environ["YBOX_CONTAINER_MANAGER"]

        # mock for different podman/docker executables including none available
        def os_access(prog: str, mode: int) -> bool:
            return prog == check_prog and mode == os.X_OK

        def subproc_out(cmd: list[str]) -> bytes:
            if "podman" in cmd[0]:
                return b"podman x.x"
            if len(cmd) == 3 and cmd[1] == "context" and cmd[2] == "show":
                return b"rootless"
            return b"docker x.x"
        with patch("ybox.env.os.access", side_effect=os_access), \
                patch("ybox.env.subprocess.check_output", side_effect=subproc_out):
            check_prog = "/usr/bin/podman"
            assert get_docker_command() == check_prog
            env = Environ()
            assert env.docker_cmd == check_prog
            assert env.target_user == getpass.getuser()

            check_prog = "/usr/bin/docker"
            assert get_docker_command() == check_prog
            env = Environ()
            assert env.docker_cmd == check_prog
            assert env.target_user == "root"

            check_prog = "/bin/true"
            pytest.raises(FileNotFoundError, get_docker_command)
            pytest.raises(FileNotFoundError, Environ)
    finally:
        if current_ybox_manager:
            os.environ["YBOX_CONTAINER_MANAGER"] = current_ybox_manager
        else:
            os.environ.pop("YBOX_CONTAINER_MANAGER", None)


def test_search_config(g_env: Environ):
    """check `Environ.search_config_path` function"""

    dir_mode = 0o750
    file_mode = 0o600
    config_dir = Path(os.environ["HOME"], ".config", "ybox")
    config_dir.mkdir(mode=dir_mode, parents=True, exist_ok=True)
    # create temporary file in $HOME/.config/ybox and check that it is picked
    # then check the same for a temporary file in /tmp using absolute path
    uuid = uuid4()
    conf_file = f"test_search-{uuid}.config"
    for conf_path in (config_dir.joinpath(conf_file), Path("/tmp", conf_file)):
        conf_path.touch(mode=file_mode, exist_ok=True)
        try:
            # check absolute path for the /tmp file
            if conf_path.parent.name == "tmp":
                conf_file = str(conf_path)
                assert g_env.search_config_path(conf_file, only_sys_conf=True) == conf_path
                assert g_env.search_config_path(conf_file, only_sys_conf=False) == conf_path
            else:
                # should fail when checking for only system configuration
                pytest.raises(FileNotFoundError, g_env.search_config_path, conf_file,
                              only_sys_conf=True)
                assert g_env.search_config_path(conf_file) == conf_path
                assert g_env.search_config_path(conf_file, only_sys_conf=False) == conf_path
        finally:
            conf_path.unlink()
        pytest.raises(FileNotFoundError, g_env.search_config_path, conf_file, quiet=True)
    # check for a standard config file in $HOME
    prof_file = f"profiles/test_search_config-{uuid}.ini"
    prof_path = config_dir.joinpath(prof_file)
    prof_dir = prof_path.parent
    if not (prof_dir_exists := prof_dir.exists()):
        prof_dir.mkdir(mode=dir_mode)
    prof_path.touch(mode=file_mode, exist_ok=True)
    # should fail when checking for only system configuration
    pytest.raises(FileNotFoundError, g_env.search_config_path, prof_file, only_sys_conf=True,
                  quiet=True)
    try:
        assert g_env.search_config_path(prof_file) == prof_path
    finally:
        prof_path.unlink()
    pytest.raises(FileNotFoundError, g_env.search_config_path, prof_file, quiet=True)
    # $HOME should not be used when $YBOX_TESTING is set
    os.environ["YBOX_TESTING"] = "1"
    try:
        prof_path.touch(mode=file_mode, exist_ok=True)
        assert g_env.search_config_path(prof_file) == prof_path
        pytest.raises(FileNotFoundError, g_env.search_config_path, prof_file, only_sys_conf=True,
                      quiet=True)
        env = Environ()
        pytest.raises(FileNotFoundError, env.search_config_path, prof_file, quiet=True)
        pytest.raises(FileNotFoundError, env.search_config_path, prof_file, only_sys_conf=True,
                      quiet=True)
    finally:
        del os.environ["YBOX_TESTING"]
    try:
        # switch $HOME and search for config files which should be picked from package location
        env = Environ(home_dir=f"/test-env/{getpass.getuser()}")
        supp_list = "distros/supported.list"
        assert env.search_config_path(supp_list) == files("ybox").joinpath(f"conf/{supp_list}")
        basic_ini = "profiles/basic.ini"
        assert env.search_config_path(basic_ini) == files("ybox").joinpath(f"conf/{basic_ini}")
        assert env.search_config_path(basic_ini, only_sys_conf=True) == files("ybox").joinpath(
            f"conf/{basic_ini}")
        pytest.raises(FileNotFoundError, env.search_config_path, "profiles/new.ini", quiet=True)
        pytest.raises(FileNotFoundError, env.search_config_path, prof_file, quiet=True)
    finally:
        prof_path.unlink(missing_ok=True)
        if not prof_dir_exists:
            prof_dir.rmdir()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
