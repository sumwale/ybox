"""Test basic creation and destroy of ybox containers."""
import argparse
import getpass
import os
import shutil
import subprocess
import unittest
from typing import Union
from uuid import uuid4

from ybox.cmd import get_docker_command
from ybox.config import Consts
from ybox.print import print_info, print_error
from ybox.run.create import main_argv as ybox_create
from ybox.run.destroy import main_argv as ybox_destroy


class TestCreateDestroy(unittest.TestCase):
    """check for basic create and destroy of ybox containers"""

    def setUp(self) -> None:
        self._resources_dir = f"{os.path.dirname(__file__)}/resources"
        self._home = os.environ["HOME"]
        self._distribution = "arch"
        uuid = uuid4()
        self._box_name = f"ybox-test-{uuid}"
        self._box_image = f"{Consts.image_prefix()}/{self._distribution}/{self._box_name}"
        self._box_home = f"/tmp/ybox-test-home-{uuid}"
        if not os.path.exists(f"{self._home}/Downloads"):
            os.mkdir(f"{self._home}/Downloads", mode=0o755)
        args_parser = argparse.ArgumentParser()
        args_parser.add_argument("-d", "--docker-path")
        args = args_parser.parse_args([])
        self._docker_cmd = get_docker_command(args, "-d")

    def tearDown(self) -> None:
        subprocess.run([self._docker_cmd, "container", "stop", self._box_name],
                       stderr=subprocess.DEVNULL, check=False)
        subprocess.run([self._docker_cmd, "container", "rm", self._box_name],
                       stderr=subprocess.DEVNULL, check=False)
        subprocess.run([self._docker_cmd, "image", "rm", self._box_image],
                       stderr=subprocess.DEVNULL, check=False)
        subprocess.run([self._docker_cmd, "image", "prune", "-f"], check=False)
        shutil.rmtree(self._box_home, ignore_errors=True)
        shutil.rmtree(f"{self._home}/.local/share/ybox/{self._box_name}",
                      ignore_errors=True)

    def test_create_no_shared(self) -> None:
        distro_config = f"{self._resources_dir}/{self._distribution}_distro_minimal.ini"
        box_config = f"{self._resources_dir}/basic_no_shared.ini"
        os.environ["YBOX_TEST_HOME"] = self._box_home
        try:
            ybox_create(
                ["-n", self._box_name, "-C", distro_config, "-q", self._distribution, box_config])
            # basic checks for directories
            self.assertTrue(os.access(self._box_home, os.W_OK))
            self.assertFalse(os.path.exists(
                f"{self._home}/.local/share/ybox/SHARED_ROOTS/{self._distribution}"))
            # run a command on the container
            result = self._run_on_container("whoami")
            self._check_output(result, getpass.getuser())
            # install a package on the container and check that it works
            self.assertEqual(0, self._run_on_container("paru --noconfirm -S libtree",
                                                       capture_output=False).returncode)
            # pipe output to remove colors
            result = self._run_on_container(["/bin/sh", "-c", "libtree /usr/bin/pwd | /bin/cat"])
            self._check_output(result, "/usr/bin/pwd")
        finally:
            ybox_destroy([self._box_name])
            result = subprocess.run([self._docker_cmd, "ps", "-aqf", f"name={self._box_name}"],
                                    capture_output=True, check=False)
            self.assertEqual(0, result.returncode)
            self.assertFalse(result.stdout.decode("utf-8").strip())
            result = subprocess.run([self._docker_cmd, "image", "rm", self._box_image],
                                    check=False)
            self.assertEqual(0, result.returncode)

    def _run_on_container(self, cmd: Union[str, list[str]],
                          capture_output: bool = True) -> subprocess.CompletedProcess[bytes]:
        docker_args = [self._docker_cmd, "exec", "-it", self._box_name]
        if isinstance(cmd, str):
            docker_args.extend(cmd.split())
        else:
            docker_args.extend(cmd)
        return subprocess.run(docker_args, capture_output=capture_output, check=False)

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
