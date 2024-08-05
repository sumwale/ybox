"""Unit tests for `ybox/env.py`"""

import getpass
import os
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

import pytest

from ybox.env import Environ


@pytest.fixture(name="g_env", scope="module")
def create_env() -> Environ:
    """create an instance of :class:`Environ` used by the tests"""
    return Environ()


class NewHome:
    """context manager that sets up a $HOME different from that of current $HOME"""

    _old_home = os.environ["HOME"]

    def __enter__(self) -> str:
        new_home = f"/test-env/{getpass.getuser()}"
        os.environ["HOME"] = new_home
        return new_home

    def __exit__(self, ex_type, ex_val, ex_tb):  # type: ignore
        os.environ["HOME"] = self._old_home


def test_home_dirs(g_env: Environ):
    """check home and target container user home directories"""
    target_home = f"/home/{getpass.getuser()}"
    assert g_env.home == os.environ["HOME"]
    assert os.environ["TARGET_HOME"] == target_home
    assert g_env.target_home == target_home
    # change $HOME and check again
    with NewHome() as new_home:
        env = Environ()
        assert g_env.home != new_home
        assert os.environ["HOME"] == new_home
        assert env.home == new_home
        assert os.environ["TARGET_HOME"] == target_home
        assert env.target_home == target_home


def test_data_dirs(g_env: Environ):
    """check ybox data directory for the host user and container user"""
    data_dir = f"{g_env.home}/.local/share/ybox"
    target_home = f"/home/{getpass.getuser()}"
    target_data_dir = f"{target_home}/.local/share/ybox"
    assert g_env.data_dir == data_dir
    assert g_env.target_data_dir == target_data_dir


def test_other_vars(g_env: Environ):
    """check other misc variables set in `Environ`"""
    try:
        rt_dir = os.environ["XDG_RUNTIME_DIR"]
    except KeyError:
        rt_dir = ""
    user_base = f"{os.environ['HOME']}/.local"
    assert g_env.xdg_rt_dir == rt_dir
    assert g_env.user_applications_dir == f"{user_base}/share/applications"
    assert g_env.user_executables_dir == f"{user_base}/bin"
    assert g_env.user_man_dir == f"{user_base}/share/man"


def test_now(g_env: Environ):
    """check the `Environ.now` property and $NOW environment variable"""
    env = Environ()
    now = datetime.now()
    assert os.environ["NOW"] == str(env.now)
    assert now >= env.now > g_env.now
    assert env.now + timedelta(milliseconds=1) >= now


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
    prof_path.parent.mkdir(mode=dir_mode, exist_ok=True)
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
        prof_path.unlink(missing_ok=True)
    # switch $HOME and search for config files which should be picked from package location
    with NewHome():
        env = Environ()
        supp_list = "distros/supported.list"
        assert env.search_config_path(supp_list) == files("ybox").joinpath(f"conf/{supp_list}")
        basic_ini = "profiles/basic.ini"
        assert env.search_config_path(basic_ini) == files("ybox").joinpath(f"conf/{basic_ini}")
        assert env.search_config_path(basic_ini, only_sys_conf=True) == files("ybox").joinpath(
            f"conf/{basic_ini}")
        pytest.raises(FileNotFoundError, env.search_config_path, "profiles/new.ini", quiet=True)


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
