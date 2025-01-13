"""Test basic creation and destroy of ybox containers."""
import os
import subprocess
from pathlib import Path

import pytest
from functional.distro_base import DistributionBase, DistributionHelper

from ybox.cmd import PkgMgr
from ybox.config import Consts
from ybox.print import print_error, print_info
from ybox.run.create import main_argv as ybox_create
from ybox.run.destroy import main_argv as ybox_destroy


class TestCreateDestroy(DistributionBase):
    """check for basic create and destroy of ybox containers"""

    def test_create_no_shared(self):
        """test a basic container profile with no shared root for all supported distributions"""
        self.for_all_distros(self.create_no_shared)

    def create_no_shared(self, helper: DistributionHelper) -> None:
        """create a container using `distro_minimal.ini` profile having no shared root"""
        print(f"Running create_no_shared for Linux distribution '{helper.distribution}'")
        distro_config_file = f"{self._resources_dir}/distro_minimal.ini"
        box_config = f"{self._resources_dir}/basic_no_shared.ini"
        os.environ["YBOX_TEST_HOME"] = helper.box_home
        ybox_create(["-n", helper.box_name, "-C", distro_config_file,
                     "-q", helper.distribution, box_config])
        # basic checks for directories
        assert os.access(helper.box_home, os.W_OK)
        assert not os.path.exists(f"{self._shared_roots}/{helper.distribution}")
        # run a command on the container
        result = self.run_on_container("whoami", helper)
        _check_output(result, self.env.target_user)
        # install a package on the container and check that it works
        distro_config = self.distribution_config(Path(distro_config_file), helper)
        pkgmgr = distro_config["pkgmgr"]
        quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value]
        install_cmd = pkgmgr[PkgMgr.INSTALL.value].format(quiet=quiet_flag, opt_dep="")
        assert self.run_on_container(
            [f"/usr/local/bin/{Consts.run_user_bash_cmd()}", f"{install_cmd} jq"],
            helper, capture_output=False).returncode == 0
        # pipe output to remove colors
        result = self.run_on_container(
            ["/bin/bash", "-c", "echo '{\"one\": 1, \"two\": 2}' | jq '.[]'"], helper)
        _check_output(result, "1\n2")
        ybox_destroy([helper.box_name])
        result = subprocess.run([self._docker_cmd, "ps", "-aqf", f"name={helper.box_name}"],
                                capture_output=True, check=False)
        assert result.returncode == 0
        assert not result.stdout.decode("utf-8").strip()
        subprocess.run([self._docker_cmd, "image", "rm", helper.box_image], check=False)


def _check_output(result: subprocess.CompletedProcess[bytes], expected: str) -> None:
    """check output of `subprocess.run` against given expected string"""
    output = result.stdout.decode("utf-8").strip()
    if result.returncode != 0:
        if output:
            print_info(output)
        err = result.stderr.decode("utf-8").strip()
        if err:
            print_error(err)
        pytest.fail(f"Unexpected exit code {result.returncode}")
    assert output == expected


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
