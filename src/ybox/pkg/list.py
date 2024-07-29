"""
List packages or package files on an active ybox container.
"""

import argparse
import sys
from configparser import SectionProxy

from ybox.cmd import PkgMgr, run_command
from ybox.config import StaticConfiguration
from ybox.print import print_warn
from ybox.state import RuntimeConfiguration, YboxStateManagement


def list_packages(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                  conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                  state: YboxStateManagement) -> int:
    """
    List packages installed in a container including those not managed by `ybox-pkg`, if required.
    Some package details can also be listed like the version and whether a package has been
    installed as a dependency or is a top-level package.

    When multiple containers share the same root directory, then listing all packages will include
    those installed from other containers, if any.

    :param args: arguments having all attributes passed by the user
    :param pkgmgr: the `pkgmgr` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the docker/podman executable to use
    :param conf: the `StaticConfiguration` of the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of the `YboxStateManagement` class having the state of all yboxes

    :return: integer exit status of list packages command where 0 represents success
    """
    plain_sep = f"'{args.plain_separator}'" if args.plain_separator else "''"
    if args.os_pkgs:
        # package list and details will all be fetched using distribution's package manager
        if args.verbose:
            list_cmd = pkgmgr[PkgMgr.LIST_ALL_LONG.value] if args.all else pkgmgr[
                PkgMgr.LIST_LONG.value]
        else:
            list_cmd = pkgmgr[PkgMgr.LIST_ALL.value] if args.all else pkgmgr[PkgMgr.LIST.value]
        list_cmd = list_cmd.format(packages="", plain_separator=plain_sep)
        if shared_containers := state.get_other_shared_containers(conf.box_name,
                                                                  runtime_conf.shared_root):
            print_warn("Package listing will include packages from other containers sharing the "
                       f"same root directory: {', '.join(shared_containers)}", file=sys.stderr)
    else:
        # package list will be fetched from the state database while the details, if required,
        # will be fetched using the distribution's package manager
        dependency_type = ".*" if args.all else ""
        packages = " ".join(state.get_packages(conf.box_name, dependency_type=dependency_type))
        if not packages:
            return 0
        # TODO: optional dependencies from state database should also be shown since those
        # can be different from the package manager; the main formatting code of list_fmt*.py
        # modules should be moved to the common portion rather than being distribution specific
        list_cmd = pkgmgr[PkgMgr.LIST_ALL_LONG.value] if args.verbose else pkgmgr[
            PkgMgr.LIST_ALL.value]
        list_cmd = list_cmd.format(packages=packages, plain_separator=plain_sep)
    docker_args = [docker_cmd, "exec"]
    if sys.stdout.isatty():  # don't act as a terminal if it is being redirected
        docker_args.append("-it")
    docker_args.extend([conf.box_name, "/bin/bash", "-c", list_cmd])
    return int(run_command(docker_args, exit_on_error=False, error_msg="listing packages"))


# noinspection PyUnusedLocal
def list_files(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
               conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
               state: YboxStateManagement) -> int:
    # pylint: disable=unused-argument
    """
    List the files of a package installed in a container including those not managed by `ybox-pkg`.

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `pkgmgr` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the docker/podman executable to use
    :param conf: the `StaticConfiguration` of the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of the `YboxStateManagement` class having the state of all yboxes

    :return: integer exit status of list package files command where 0 represents success
    """
    package: str = args.package
    list_cmd = pkgmgr[PkgMgr.LIST_FILES.value]
    docker_args = [docker_cmd, "exec"]
    if sys.stdout.isatty():  # don't act as a terminal if it is being redirected
        docker_args.append("-it")
    docker_args.extend([conf.box_name, "/bin/bash", "-c", list_cmd.format(package=package)])
    return int(run_command(docker_args, exit_on_error=False,
                           error_msg=f"listing files of '{package}'"))
