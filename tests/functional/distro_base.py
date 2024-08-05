"""Helper class to run tests on all supported distributions"""

import argparse
import configparser
import os
import shutil
import subprocess
from dataclasses import dataclass
from importlib.resources import files
from typing import Callable, Optional, Union
from uuid import uuid4

import pytest

from ybox.cmd import get_docker_command
from ybox.config import Consts, StaticConfiguration
from ybox.env import Environ, PathName
from ybox.util import EnvInterpolation, config_reader


@dataclass(frozen=True)
class _DistributionHelper:
    """
    Encapsulates some details of distribution including its name, home directory to use etc.

    Attributes:
        distribution: name of the distribution
        box_name: name of the ybox container
        box_home: path of directory on the host system mapped to home directory in the container
        box_image: name of the image used for the container
    """
    distribution: str
    box_name: str
    box_home: str
    box_image: str

    @classmethod
    def create(cls, distribution: str):
        """static _DistributionHelper object creation helper method"""
        uuid = uuid4()
        box_name = f"ybox-test-{uuid}"
        return cls(distribution, box_name, f"/tmp/ybox-test-home-{uuid}",
                   f"{Consts.image_prefix()}/{distribution}/{box_name}")


class DistributionBase:
    """base class to help execute tests on multiple distributions"""

    _resources_dir = f"{os.path.dirname(__file__)}/resources"
    _home = os.environ["HOME"]
    _docker_cmd = ""
    _helpers: list[_DistributionHelper] = []
    _helper: Optional[_DistributionHelper] = None

    @pytest.fixture(autouse=True)
    def distro_setup(self):
        """distribution setup executed before and after each test method in the class"""
        os.environ["YBOX_TESTING"] = "1"
        if not os.path.exists(f"{self._home}/Downloads"):
            os.mkdir(f"{self._home}/Downloads", mode=0o755)
        args_parser = argparse.ArgumentParser()
        args_parser.add_argument("-d", "--docker-path")
        args = args_parser.parse_args([])
        self._docker_cmd = get_docker_command(args, "-d")
        with files("ybox").joinpath("conf/distros/supported.list").open(
                "r", encoding="utf-8") as supp_fd:
            self._helpers = [_DistributionHelper.create(distro)
                             for distro in supp_fd.read().splitlines()]

        yield

        del os.environ["YBOX_TESTING"]
        # cleanup executed after each test method in the class
        if self._helper:
            self.cleanup()

    @property
    def distribution(self) -> str:
        """name of the distribution"""
        return self._helper.distribution if self._helper else ""

    @property
    def box_name(self) -> str:
        """name of the ybox container"""
        return self._helper.box_name if self._helper else ""

    @property
    def box_home(self) -> str:
        """path of directory on the host system mapped to home directory in the container"""
        return self._helper.box_home if self._helper else ""

    @property
    def box_image(self) -> str:
        """name of the image used for the container"""
        return self._helper.box_image if self._helper else ""

    def cleanup(self) -> None:
        """
        Completely remove the ybox container and its image and delete the local directories
        mapped to the home and data directories inside the container.
        """
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

    def for_all_distros(self, test_func: Callable[[], None]) -> None:
        """execute a given zero argument function for all supported distributions"""
        for helper in self._helpers:
            self._helper = helper
            try:
                test_func()
            finally:
                self.cleanup()
                self._helper = None

    def run_on_container(self, cmd: Union[str, list[str]],
                         capture_output: bool = True) -> subprocess.CompletedProcess[bytes]:
        """
        Run a command on the container using docker/podman exec and return the
        :class:`subprocess.CompletedProcess` from the result of :func:`subprocess.run`.
        """
        docker_args = [self._docker_cmd, "exec", "-it", self.box_name]
        if isinstance(cmd, str):
            docker_args.extend(cmd.split())
        else:
            docker_args.extend(cmd)
        return subprocess.run(docker_args, capture_output=capture_output, check=False)

    def distribution_config(self, config_file: PathName) -> configparser.ConfigParser:
        """read and parse a distribution configuration returning a `ConfigParser` object"""
        # instance of StaticConfiguration only required to set up the environment variables
        conf = StaticConfiguration(Environ(), self.distribution, self.box_name)
        env_interpolation = EnvInterpolation(conf.env, [])
        return config_reader(config_file, env_interpolation)
