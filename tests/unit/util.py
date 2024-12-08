"""some common utility functions and classes for unit and functional tests"""

import json
import operator
import os
from dataclasses import dataclass
from functools import reduce
from importlib.resources import files
from itertools import chain
from typing import Any, Optional

import ybox.state as y_state
from ybox.env import Environ
from ybox.state import RuntimeConfiguration
from ybox.util import EnvInterpolation, config_reader

RESOURCES_DIR = f"{os.path.dirname(__file__)}/../resources"


@dataclass(frozen=True)
class PackageDetails:
    """holds the fields read from test json file required for package registration in the state"""
    name: str
    shared_root: str
    local_copies: list[str]
    copy_type: Optional[Any]  # this is `CopyType` when filled
    app_flags: dict[str, str]
    dep_type: Optional[Any]  # this is `DependencyType` when filled
    dep_of: str


# short name for return type of `read_containers_and_packages`
ContainerDetails = tuple[list[RuntimeConfiguration], dict[str, RuntimeConfiguration],
                         dict[str, list[PackageDetails]]]


def read_containers_and_packages(env: Environ, fetch_types: bool,
                                 interpolate: bool) -> ContainerDetails:
    """
    Read and parse container and package specification from the test json files.
    See `tests/resources/containers.json` and `tests/resources/packages.json` for the expected
    json structure.

    :param env: an instance of the current :class:`Environ`
    :param fetch_types: if True then the `copy_type`, `app_flags`, `dep_type` and `dep_info` fields
                        of :class:`PackageDetails` are filled in, else they are None/empty
    :param interpolate: if True then apply :class:`EnvInterpolation` to the container profile else
                        skip any interpolation (latter used for migration to test matching values
                          from old product state database)
    :return: a tuple of (list of :class:`RuntimeConfiguration` of active containers,
               map of name to :class:`RuntimeConfiguration` of containers to be destroyed,
               map of containers to their :class:`PackageDetails`)
    """
    with open(f"{RESOURCES_DIR}/containers.json", "r", encoding="utf-8") as containers_fd:
        containers: dict[str, dict[str, Any]] = json.load(containers_fd)
    with open(f"{RESOURCES_DIR}/packages.json", "r", encoding="utf-8") as pkgs_fd:
        pkgs: dict[str, dict[str, Any]] = json.load(pkgs_fd)

    def build_runtime_config(name: str, info: dict[str, Any]) -> RuntimeConfiguration:
        shared_root = info["shared_root"]
        if interpolate:
            shared_root = os.path.expandvars(shared_root)
        profile = files("ybox").joinpath("conf").joinpath(info["profile"])
        # don't use EnvInterpolation since it can change as per the test environment
        interpolation = EnvInterpolation(env, ["configs"]) if interpolate else None
        parsed_profile = config_reader(conf_file=profile, interpolation=interpolation)
        if shared_root:
            # old versions used hard-coded ".../ROOTS/..." for shared_root so use the same
            parsed_profile["base"]["shared_root"] = shared_root
        else:
            del parsed_profile["base"]["shared_root"]

        return RuntimeConfiguration(name, info["distribution"], shared_root, parsed_profile)

    active_containers = [build_runtime_config(c, info) for c, info in containers.items()
                         if not info["destroy"]]
    destroy_containers = {c: build_runtime_config(c, info) for c, info in containers.items()
                          if info["destroy"]}
    # Create a mapping of container to the corresponding packages installed on it.
    # Note: the `CopyType`` and `DependencyType`` classes are deliberately not imported directly
    # and instead imported on demand from the `state` module only if `fetch_types` is True
    # so that this function works with older product versions where these two classes were absent.
    if fetch_types:
        def get_copy_type(names: list[str]) -> y_state.CopyType:
            """given a list of `CopyType` names, convert to a single `CopyType` by ORing"""
            return reduce(operator.ior, [y_state.CopyType[c] for c in names], y_state.CopyType(0))

        def build_package_details(pkg: str, pkg_info: dict[str, Any],
                                  shared_root: str) -> PackageDetails:
            """build the :class:`PackageDetails` given the json specification for the package"""
            dep_type = pkg_info.get("dep_type")
            dep_type = y_state.DependencyType[dep_type] if dep_type else None
            return PackageDetails(pkg, shared_root, pkg_info["local_copies"],
                                  get_copy_type(pkg_info["copy_type"]), pkg_info["app_flags"],
                                  dep_type, pkg_info["dep_of"])
    else:
        def build_package_details(pkg: str, pkg_info: dict[str, Any],
                                  shared_root: str) -> PackageDetails:
            """
            build the :class:`PackageDetails` given the json specification for the package
            for old product versions skipping copy_type, app_flags, dep_type, dep_of fields
            """
            return PackageDetails(pkg, shared_root, pkg_info["local_copies"], None, {}, None, "")

    # register packages in the provided list of containers
    container_pkgs = {c.name: sorted([build_package_details(pkg, pkg_info, c.shared_root)
                                      for pkg, pkg_info in pkgs.items()
                                      if c.name in pkg_info["containers"]], key=lambda p: p.name)
                      for c in chain(active_containers, destroy_containers.values())}

    return active_containers, destroy_containers, container_pkgs
