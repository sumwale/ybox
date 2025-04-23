"""Unit tests for `ybox/config.py`"""

import os
from pathlib import Path

import pytest

from ybox.config import Consts
from ybox.config import StaticConfiguration as static_conf
from ybox.env import Environ

_TEST_DISTRIBUTION = "ybox-distro"
_TEST_CONTAINER = "ybox-test"


@pytest.fixture(name="env")
def create_env() -> Environ:
    """create an instance of :class:`Environ` used by the tests"""
    return Environ()


@pytest.fixture(name="config")
def create_config(env: Environ) -> static_conf:
    """create an instance of :class:`StaticConfiguration` used by the tests"""
    return static_conf(env, _TEST_DISTRIBUTION, _TEST_CONTAINER)


def test_static_conf_init(env: Environ, config: static_conf):
    """test environment setup in initialization of :class:`StaticConfiguration`"""
    assert config.env == env
    assert config.distribution == _TEST_DISTRIBUTION
    assert config.box_name == _TEST_CONTAINER
    assert os.environ["YBOX_DISTRIBUTION_NAME"] == _TEST_DISTRIBUTION
    assert os.environ["YBOX_CONTAINER_NAME"] == _TEST_CONTAINER
    assert os.environ["YBOX_CONTAINER_DIR"] == f"{env.data_dir}/{_TEST_CONTAINER}"
    assert os.environ["YBOX_TARGET_SCRIPTS_DIR"] == "/usr/local/ybox"


def test_distribution_config():
    """tests for :func:`StaticConfiguration.distribution_config`"""
    expected = f"distros/{_TEST_DISTRIBUTION}/distro.ini"
    assert static_conf.distribution_config(_TEST_DISTRIBUTION) == expected
    config_file = "ybox-distro.ini"
    expected = f"distros/{_TEST_DISTRIBUTION}/{config_file}"
    assert static_conf.distribution_config(_TEST_DISTRIBUTION, config_file) == expected


def test_box_image(config: static_conf):
    """tests for :func:`StaticConfiguration.box_image`"""
    assert config.box_image(False) == \
        f"{Consts.image_prefix()}/{_TEST_DISTRIBUTION}/{_TEST_CONTAINER}"
    assert config.box_image(True) == f"{Consts.shared_image_prefix()}/{_TEST_DISTRIBUTION}"


def test_pager(env: Environ, config: static_conf):
    """test the `pager` property of :class:`StaticConfiguration` with and without $YBOX_PAGER"""
    assert config.pager == Consts.default_pager()
    # check pager with YBOX_PAGER environment variable set
    os.environ["YBOX_PAGER"] = "/usr/bin/most"
    try:
        config = static_conf(env, _TEST_DISTRIBUTION, _TEST_CONTAINER)
        assert config.pager == "/usr/bin/most"
    finally:
        del os.environ["YBOX_PAGER"]


def test_properties(env: Environ, config: static_conf):
    """test various properties of :class:`StaticConfiguration` (except `pager`)"""
    assert config.env == env
    assert config.distribution == _TEST_DISTRIBUTION
    assert config.box_name == _TEST_CONTAINER
    assert config.localtime == os.readlink("/etc/localtime")
    assert config.timezone == Path("/etc/timezone").read_text(encoding="utf-8").rstrip()
    assert config.configs_dir == f"{env.data_dir}/{_TEST_CONTAINER}/configs"
    assert config.target_configs_dir == f"{env.target_data_dir}/{_TEST_CONTAINER}/configs"
    assert config.scripts_dir == f"{env.data_dir}/{_TEST_CONTAINER}/ybox-scripts"
    assert config.target_scripts_dir == "/usr/local/ybox"
    assert config.status_file == f"{env.data_dir}/{_TEST_CONTAINER}/status"
    assert config.config_list == f"{env.data_dir}/{_TEST_CONTAINER}/ybox-scripts/config.list"
    assert config.app_list == f"{env.data_dir}/{_TEST_CONTAINER}/ybox-scripts/app.list"
    assert config.startup_list == f"{env.data_dir}/{_TEST_CONTAINER}/ybox-scripts/startup.list"


def test_consts():
    """check the constants defined in :class:`Consts`"""
    assert Consts.image_prefix() == "ybox-local"
    assert Consts.shared_image_prefix() == "ybox-shared-local"
    assert Consts.default_directory_mode() == 0o750
    assert Consts.entrypoint_base() == "entrypoint-base.sh"
    assert Consts.entrypoint_cp() == "entrypoint-cp.sh"
    assert Consts.entrypoint() == "entrypoint.sh"
    expected_scripts = ("entrypoint-base.sh", "entrypoint-cp.sh", "entrypoint.sh",
                        "entrypoint-common.sh", "entrypoint-root.sh", "entrypoint-user.sh",
                        "prime-run", "run-in-dir", "run-user-bash-cmd")
    assert Consts.resource_scripts() == expected_scripts
    assert Consts.shared_root_mount_dir() == "/ybox-root"
    assert Consts.status_target_file() == "/usr/local/ybox-status"
    assert Consts.entrypoint_init_done_file() == "ybox-init.done"
    assert Consts.container_desktop_dirs() == ("/usr/share/applications",)
    expected_icon_dirs = (
        "/usr/share/icons/hicolor/scalable/.*", "/usr/share/icons/hicolor/([1-9]+)x.*",
        "/usr/share/icons/hicolor/symbolic/.*", "/usr/share/icons", "/usr/share/pixmaps")
    assert Consts.container_icon_dirs() == expected_icon_dirs
    expected_exec_dirs = ("/usr/bin", "/bin", "/usr/sbin", "/sbin",
                          "/usr/local/bin", "/usr/local/sbin")
    assert Consts.container_bin_dirs() == expected_exec_dirs
    for man_dir in ("/usr/share/man", "/usr/man", "/usr/local/share/man", "/usr/local/man"):
        for sub_dir in (f"man{idx}" for idx in range(10)):
            assert Consts.container_man_dir_pattern().match(f"{man_dir}/{sub_dir}")
            assert Consts.container_man_dir_pattern().match(f"{man_dir}/{sub_dir}type")
            assert Consts.container_man_dir_pattern().match(f"{man_dir}/cs/{sub_dir}")
            assert Consts.container_man_dir_pattern().match(f"{man_dir}/de/{sub_dir}")
            assert Consts.container_man_dir_pattern().match(f"{man_dir}/zh_TW/{sub_dir}")
    assert Consts.sys_bin_dirs() == expected_exec_dirs
    assert Consts.nvidia_target_base_dir() == "/usr/local/nvidia"
    assert Consts.nvidia_setup_script() == "nvidia-setup.sh"
    assert Consts.default_pager() == "/usr/bin/less -RLFXK"
    assert Consts.default_field_separator() == "::::"
    assert Consts.default_key_server() == "hkps://keys.openpgp.org"


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
