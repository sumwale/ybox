"""Test basic creation and destroy of ybox containers."""
import getpass
import os
import subprocess
import unittest
from pathlib import Path

from distro_base import DistributionBase
from ybox.cmd import PkgMgr
from ybox.print import print_info, print_error
from ybox.run.create import main_argv as ybox_create
from ybox.run.destroy import main_argv as ybox_destroy


class TestCreateDestroy(DistributionBase):
    """check for basic create and destroy of ybox containers"""

    def test_create_no_shared(self) -> None:
        self.for_all_distros(self.create_no_shared)

    def create_no_shared(self) -> None:
        print(f"Running create_no_shared for Linux distribution '{self._distribution}'")
        distro_config_file = f"{self._resources_dir}/distro_minimal.ini"
        box_config = f"{self._resources_dir}/basic_no_shared.ini"
        os.environ["YBOX_TEST_HOME"] = self._box_home
        ybox_create(
            ["-n", self._box_name, "-C", distro_config_file, "-q", self._distribution, box_config])
        # basic checks for directories
        self.assertTrue(os.access(self._box_home, os.W_OK))
        self.assertFalse(os.path.exists(
            f"{self._home}/.local/share/ybox/SHARED_ROOTS/{self._distribution}"))
        # run a command on the container
        result = self.run_on_container("whoami")
        self._check_output(result, getpass.getuser())
        # install a package on the container and check that it works
        distro_config = self.distribution_config(Path(distro_config_file))
        pkgmgr = distro_config["pkgmgr"]
        quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value]
        install_cmd = pkgmgr[PkgMgr.INSTALL.value].format(quiet=quiet_flag, opt_dep="")
        self.assertEqual(0, self.run_on_container(["/bin/bash", "-c", f"{install_cmd} libtree"],
                                                  capture_output=False).returncode)
        # pipe output to remove colors
        result = self.run_on_container(["/bin/bash", "-c", "libtree /usr/bin/pwd | /bin/cat"])
        self._check_output(result, "/usr/bin/pwd")
        ybox_destroy([self._box_name])
        result = subprocess.run([self._docker_cmd, "ps", "-aqf", f"name={self._box_name}"],
                                capture_output=True, check=False)
        self.assertEqual(0, result.returncode)
        self.assertFalse(result.stdout.decode("utf-8").strip())
        result = subprocess.run([self._docker_cmd, "image", "rm", self._box_image],
                                check=False)
        self.assertEqual(0, result.returncode)

    def _check_output(self, result: subprocess.CompletedProcess[bytes], expected: str) -> None:
        output = result.stdout.decode("utf-8").strip()
        if result.returncode != 0:
            if output:
                print_info(output)
            err = result.stderr.decode("utf-8").strip()
            if err:
                print_error(err)
            self.fail(f"Unexpected exit code {result.returncode}")
        self.assertEqual(expected, output)


if __name__ == '__main__':
    unittest.main()
