"""
Update some or all packages on a running zbox container.
"""

import argparse
from configparser import SectionProxy

from zbox.cmd import PkgMgr, run_command
from zbox.config import StaticConfiguration
from zbox.print import print_warn
from zbox.state import RuntimeConfiguration, ZboxStateManagement
from zbox.util import get_other_shared_containers


def update_package(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                   conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                   state: ZboxStateManagement) -> int:
    """
    Update the mentioned package installed in a container which can include packages not managed
    by `zbox-pkg`, as well as those installed by other containers if the container shares the
    same root directory with other containers.

    When no package name is provided, then the entire installation is updated. Like above, it will
    end up updating all the containers sharing the same root directory, if any. Note that
    some rolling distributions like Arch Linux recommend always doing a full installation upgrade
    rather than individual packages.

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `pkgmgr` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the docker/podman executable to use
    :param conf: the `StaticConfiguration` of the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of the `ZboxStateManagement` class having the state of all zboxes

    :return: integer exit status of install command where 0 represents success
    """
    quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value] if args.quiet else ""
    packages: list[str] = args.packages
    if packages:
        update_meta_cmd = pkgmgr[PkgMgr.UPDATE_META.value]
        update_pkgs_cmd = pkgmgr[PkgMgr.UPDATE.value].format(quiet=quiet_flag)
        update_cmd = f"{{ {update_meta_cmd}; }} && {{ {update_pkgs_cmd} {' '.join(packages)}; }}"
    else:
        update_cmd = pkgmgr[PkgMgr.UPDATE_ALL.value].format(quiet=quiet_flag)
    if shared_containers := get_other_shared_containers(conf.box_name, runtime_conf.shared_root,
                                                        state):
        # show all the containers sharing the same shared root
        print_warn("The operation will also update packages in other containers having the same "
                   f"shared root directory: {', '.join(shared_containers)}")
    return int(run_command([docker_cmd, "exec", "-it", conf.box_name, "/bin/bash", "-c",
                            update_cmd], exit_on_error=False, error_msg="updating packages"))
