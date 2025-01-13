"""Helper class to run tests on all supported distributions"""

import os
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from configparser import ConfigParser
from dataclasses import dataclass
from importlib.resources import files
from typing import Callable, Optional, Union, cast
from uuid import uuid4

import pytest

from ybox.config import Consts, StaticConfiguration
from ybox.env import Environ, PathName
from ybox.print import print_error
from ybox.util import EnvInterpolation, config_reader


@dataclass(frozen=True)
class DistributionHelper:
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

    _resources_dir = f"{os.path.dirname(__file__)}/../resources"
    _home = os.environ["HOME"]
    _shared_roots = f"{_home}/.local/share/ybox/YBOX_TEST_SHARED_ROOTS"
    _env = None
    _docker_cmd = ""
    _helpers: list[DistributionHelper] = []

    @pytest.fixture(autouse=True)
    def distro_setup(self):
        """distribution setup executed before and after each test method in the class"""
        os.environ["YBOX_TESTING"] = "1"
        try:
            os.mkdir(f"{self._home}/Downloads", mode=0o755)
        except FileExistsError:
            pass
        try:
            os.mkdir(f"{self._home}/Documents", mode=0o755)
        except FileExistsError:
            pass
        self._env = Environ()
        self._docker_cmd = self._env.docker_cmd
        with files("ybox").joinpath("conf/distros/supported.list").open(
                "r", encoding="utf-8") as supp_fd:
            self._helpers = [DistributionHelper.create(distro)
                             for distro in supp_fd.read().splitlines()]

        yield

        del os.environ["YBOX_TESTING"]

    @property
    def env(self) -> Environ:
        """the `Environ` object being used in the tests"""
        return cast(Environ, self._env)

    def cleanup(self, helper: DistributionHelper) -> None:
        """
        Completely remove the ybox container and its image and delete the local directories
        mapped to the home and data directories inside the container.
        """
        subprocess.run([self._docker_cmd, "container", "stop", helper.box_name],
                       stderr=subprocess.DEVNULL, check=False)
        subprocess.run([self._docker_cmd, "container", "rm", helper.box_name],
                       stderr=subprocess.DEVNULL, check=False)
        subprocess.run([self._docker_cmd, "image", "rm", helper.box_image],
                       stderr=subprocess.DEVNULL, check=False)
        subprocess.run([self._docker_cmd, "image", "prune", "-f"], check=False)
        shutil.rmtree(helper.box_home, ignore_errors=True)
        shutil.rmtree(f"{self._home}/.local/share/ybox/{helper.box_name}",
                      ignore_errors=True)
        shutil.rmtree(self._shared_roots, ignore_errors=True)

    def for_all_distros(self, test_func: Callable[[DistributionHelper], None]) -> None:
        """execute a given zero argument function for all supported distributions"""
        failure: Optional[BaseException] = None
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(test_func, helper): helper for helper in self._helpers}
            for future in as_completed(futures):
                helper = futures[future]
                try:
                    future.result()
                except BaseException as e:  # pylint: disable=broad-exception-caught # noqa: B036
                    failure = future.exception() or e
                    print_error(f"Error running '{test_func.__qualname__}' for container "
                                f"'{helper.box_name}': {failure}")
                finally:
                    self.cleanup(helper)
        if failure:
            raise failure

    def run_on_container(self, cmd: Union[str, list[str]], helper: DistributionHelper,
                         capture_output: bool = True) -> subprocess.CompletedProcess[bytes]:
        """
        Run a command on the container using podman/docker exec and return the
        :class:`subprocess.CompletedProcess` from the result of :func:`subprocess.run`.
        """
        docker_args = [self._docker_cmd, "exec", helper.box_name]
        if isinstance(cmd, str):
            docker_args.extend(cmd.split())
        else:
            docker_args.extend(cmd)
        return subprocess.run(docker_args, capture_output=capture_output, check=False)

    def distribution_config(self, config_file: PathName,
                            helper: DistributionHelper) -> ConfigParser:
        """read and parse a distribution configuration returning a `ConfigParser` object"""
        # instance of StaticConfiguration only required to set up the environment variables
        conf = StaticConfiguration(self.env, helper.distribution, helper.box_name)
        env_interpolation = EnvInterpolation(conf.env, [])
        return config_reader(config_file, env_interpolation)
