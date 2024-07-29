"""Tests for `ybox/env.py`"""

import getpass
import os
import unittest
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from ybox.env import Environ


class TestEnv(unittest.TestCase):
    """unit tests for the `ybox.env` module"""

    _target_home = f"/home/{getpass.getuser()}"
    _env = Environ()

    class NewHome:
        """context manager that sets up a $HOME different from that of current $HOME"""

        _old_home = os.environ["HOME"]

        def __enter__(self) -> str:
            new_home = f"/test-env/{getpass.getuser()}"
            os.environ["HOME"] = new_home
            return new_home

        def __exit__(self, ex_type, ex_val, ex_tb):  # type: ignore
            os.environ["HOME"] = self._old_home

    def test_home_dirs(self):
        """check home and target container user home directories"""
        self.assertEqual(os.environ["HOME"], self._env.home)
        self.assertEqual(self._target_home, os.environ["TARGET_HOME"])
        self.assertEqual(self._target_home, self._env.target_home)
        # change $HOME and check again
        with self.NewHome() as new_home:
            env = Environ()
            self.assertNotEqual(new_home, self._env.home)
            self.assertEqual(new_home, os.environ["HOME"])
            self.assertEqual(new_home, env.home)
            self.assertEqual(self._target_home, os.environ["TARGET_HOME"])
            self.assertEqual(self._target_home, env.target_home)

    def test_data_dirs(self):
        """check ybox data directory for the host user and container user"""
        data_dir = f"{self._env.home}/.local/share/ybox"
        target_data_dir = f"{self._target_home}/.local/share/ybox"
        self.assertEqual(data_dir, self._env.data_dir)
        self.assertEqual(target_data_dir, self._env.target_data_dir)

    def test_other_vars(self):
        """check other misc variables set in `Environ`"""
        try:
            rt_dir = os.environ["XDG_RUNTIME_DIR"]
        except KeyError:
            rt_dir = ""
        user_base = f"{os.environ['HOME']}/.local"
        self.assertEqual(rt_dir, self._env.xdg_rt_dir)
        self.assertEqual(f"{user_base}/share/applications", self._env.user_applications_dir)
        self.assertEqual(f"{user_base}/bin", self._env.user_executables_dir)
        self.assertEqual(f"{user_base}/share/man", self._env.user_man_dir)

    def test_now(self):
        """check the `Environ.now` property and $NOW environment variable"""
        env = Environ()
        now = datetime.now()
        self.assertEqual(str(env.now), os.environ["NOW"])
        self.assertGreater(now, self._env.now)
        self.assertGreater(env.now, self._env.now)
        self.assertGreaterEqual(now, env.now)
        self.assertAlmostEqual(now, env.now, delta=timedelta(milliseconds=1))

    def test_search_config(self):
        """check `Environ.search_config_path` function"""

        dir_mode = 0o750
        file_mode = 0o600
        config_dir = Path(os.environ['HOME'], ".config", "ybox")
        config_dir.mkdir(mode=dir_mode, parents=True, exist_ok=True)
        # create temporary file in $HOME/.config/ybox and check that it is picked
        uuid = uuid4()
        conf_file = f"test_search-{uuid}.config"
        conf_path = config_dir.joinpath(conf_file)
        conf_path.touch(mode=file_mode, exist_ok=True)
        # should fail when checking for only system configuration
        self.assertRaises(FileNotFoundError, self._env.search_config_path, conf_file,
                          only_sys_conf=True)
        try:
            self.assertEqual(conf_path, self._env.search_config_path(conf_file))
        finally:
            conf_path.unlink()
        self.assertRaises(FileNotFoundError, self._env.search_config_path, conf_file, quiet=True)
        # check for a standard config file in $HOME
        prof_file = f"profiles/test_search_config-{uuid}.ini"
        prof_path = config_dir.joinpath(prof_file)
        prof_path.parent.mkdir(mode=dir_mode, exist_ok=True)
        prof_path.touch(mode=file_mode, exist_ok=True)
        # should fail when checking for only system configuration
        self.assertRaises(FileNotFoundError, self._env.search_config_path, prof_file,
                          only_sys_conf=True, quiet=True)
        try:
            self.assertEqual(prof_path, self._env.search_config_path(prof_file))
        finally:
            prof_path.unlink()
        self.assertRaises(FileNotFoundError, self._env.search_config_path, prof_file, quiet=True)
        # $HOME should not be used when $YBOX_TESTING is set
        os.environ["YBOX_TESTING"] = "1"
        try:
            prof_path.touch(mode=file_mode, exist_ok=True)
            self.assertEqual(prof_path, self._env.search_config_path(prof_file))
            self.assertRaises(FileNotFoundError, self._env.search_config_path, prof_file,
                              only_sys_conf=True, quiet=True)
            env = Environ()
            self.assertRaises(FileNotFoundError, env.search_config_path, prof_file, quiet=True)
            self.assertRaises(FileNotFoundError, env.search_config_path, prof_file,
                              only_sys_conf=True, quiet=True)
        finally:
            del os.environ["YBOX_TESTING"]
            prof_path.unlink(missing_ok=True)
        # switch $HOME and search for config files which should be picked from package location
        with self.NewHome():
            env = Environ()
            supp_list = "distros/supported.list"
            self.assertEqual(files("ybox").joinpath(f"conf/{supp_list}"),
                             env.search_config_path(supp_list))
            basic_ini = "profiles/basic.ini"
            self.assertEqual(files("ybox").joinpath(f"conf/{basic_ini}"),
                             env.search_config_path(basic_ini))
            self.assertEqual(files("ybox").joinpath(f"conf/{basic_ini}"),
                             env.search_config_path(basic_ini, only_sys_conf=True))
            self.assertRaises(FileNotFoundError, env.search_config_path, "profiles/new.ini",
                              quiet=True)


if __name__ == '__main__':
    unittest.main()
