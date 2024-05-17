"""Helper class to run tests on all supported distributions"""

import argparse
import configparser
import os
import shutil
import subprocess
import unittest
from importlib.resources import files
from typing import Optional, Union
from uuid import uuid4

from ybox.cmd import get_docker_command
from ybox.config import Consts
from ybox.config import StaticConfiguration
from ybox.env import Environ, PathName
from ybox.util import EnvInterpolation, config_reader


class _DistributionHelper:
    def __init__(self, distribution: str):
        self.distribution = distribution
        uuid = uuid4()
        self.box_name = f"ybox-test-{uuid}"
        self.box_home = f"/tmp/ybox-test-home-{uuid}"
        self.box_image = f"{Consts.image_prefix()}/{distribution}/{self.box_name}"


class DistributionBase(unittest.TestCase):

    def setUp(self) -> None:
        os.environ["YBOX_TESTING"] = "1"
        self._resources_dir = f"{os.path.dirname(__file__)}/resources"
        self._home = os.environ["HOME"]
        if not os.path.exists(f"{self._home}/Downloads"):
            os.mkdir(f"{self._home}/Downloads", mode=0o755)
        args_parser = argparse.ArgumentParser()
        args_parser.add_argument("-d", "--docker-path")
        args = args_parser.parse_args([])
        self._docker_cmd = get_docker_command(args, "-d")
        with files("ybox").joinpath("conf/distros/supported.list").open(
                "r", encoding="utf-8") as supp_fd:
            self._helpers = [_DistributionHelper(distro) for distro in supp_fd.read().splitlines()]
        self._helper: Optional[_DistributionHelper] = None

    def tearDown(self) -> None:
        if self._helper:
            self.cleanup()

    @property
    def distribution(self) -> str:
        return self._helper.distribution if self._helper else ""

    @property
    def box_name(self) -> str:
        return self._helper.box_name if self._helper else ""

    @property
    def box_home(self) -> str:
        return self._helper.box_home if self._helper else ""

    @property
    def box_image(self) -> str:
        return self._helper.box_image if self._helper else ""

    def cleanup(self) -> None:
        subprocess.run([self._docker_cmd, "container", "stop", self.box_name],
                       stderr=subprocess.DEVNULL, check=False)
        subprocess.run([self._docker_cmd, "container", "rm", self.box_name],
                       stderr=subprocess.DEVNULL, check=False)
        subprocess.run([self._docker_cmd, "image", "rm", self.box_image],
                       stderr=subprocess.DEVNULL, check=False)
        subprocess.run([self._docker_cmd, "image", "prune", "-f"], check=False)
        shutil.rmtree(self.box_home, ignore_errors=True)
        shutil.rmtree(f"{self._home}/.local/share/ybox/{self.box_name}",
                      ignore_errors=True)

    def for_all_distros(self, test_func) -> None:
        for self._helper in self._helpers:
            try:
                test_func()
            finally:
                self.cleanup()

    def run_on_container(self, cmd: Union[str, list[str]],
                         capture_output: bool = True) -> subprocess.CompletedProcess[bytes]:
        docker_args = [self._docker_cmd, "exec", "-it", self.box_name]
        if isinstance(cmd, str):
            docker_args.extend(cmd.split())
        else:
            docker_args.extend(cmd)
        return subprocess.run(docker_args, capture_output=capture_output, check=False)

    def distribution_config(self, config_file: PathName) -> configparser.ConfigParser:
        # instance of StaticConfiguration only required to set up the environment variables
        conf = StaticConfiguration(Environ(), self.distribution, self.box_name)
        env_interpolation = EnvInterpolation(conf.env, [])
        return config_reader(config_file, env_interpolation)
