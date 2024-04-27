import argparse
from configparser import SectionProxy

from zbox.config import StaticConfiguration
from zbox.state import RuntimeConfiguration, ZboxStateManagement
from zbox.util import PkgMgr, run_command


def list_packages(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                  conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                  state: ZboxStateManagement) -> int:
    """
    List packages installed in a container including those not managed by `zbox-pkg`, if required.
    Some package details can also be listed like the version and whether a package has been
    installed as a dependency or is a top-level package.

    When multiple containers share the same root directory, then listing all packages will include
    those installed from other containers, if any.

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `pkgmgr` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the docker/podman executable to use
    :param conf: the `StaticConfiguration` of the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of the `ZboxStateManagement` class having the state of all zboxes

    :return: integer exit status of install command where 0 represents success
    """
    # TODO: honor --verbose
    if args.all:
        # package list and details will all be fetched using distribution's package manager
        list_cmd = pkgmgr[PkgMgr.LIST.value] if args.explicit else pkgmgr[PkgMgr.LIST_ALL.value]
    else:
        # package list will be fetched from the state database while the details, if required,
        # will be fetched using the distribution's package manager
        package_type = "" if args.explicit else "%"
        packages = " ".join(state.get_packages(conf.box_name, package_type=package_type))
        if not packages:
            return 0
        list_cmd = f"{pkgmgr[PkgMgr.LIST_ALL.value]} {packages}"
    return int(run_command([docker_cmd, "exec", "-it", conf.box_name, "/bin/bash", "-c",
                            list_cmd], exit_on_error=False, error_msg="listing packages"))
