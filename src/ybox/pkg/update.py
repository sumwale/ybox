"""
Update some or all packages on an active ybox container.
"""

import argparse
from configparser import SectionProxy

from ybox.cmd import PkgMgr, build_shell_command, run_command
from ybox.config import StaticConfiguration
from ybox.print import print_warn
from ybox.state import RuntimeConfiguration, YboxStateManagement

# TODO: updating packages can lead to system libraries among others getting updated. At the very
#       least, the container may need to be restarted thereafter. All other containers on the same
#       shared root should also be restarted which can be an issue for the user. This is also
#       a problem when creating a new container on the same shared root since that too does update.
#       The biggest problem can be that even a new package install can end up updating shared libs.


def update_packages(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                    conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                    state: YboxStateManagement) -> int:
    """
    Update the mentioned package installed in a container which can include packages not managed
    by `ybox-pkg`, as well as those installed by other containers if the container shares the
    same root directory with other containers.

    When no package name is provided, then the entire installation is updated. Like above, it will
    end up updating all the containers sharing the same root directory, if any. Note that
    some rolling distributions like Arch Linux recommend always doing a full installation upgrade
    rather than individual packages.

    :param args: arguments having `packages` and all other attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :return: integer exit status of update command where 0 represents success
    """
    quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value] if args.quiet else ""
    packages: list[str] = args.packages
    if packages:
        update_meta_cmd = pkgmgr[PkgMgr.UPDATE_META.value]
        update_pkgs_cmd = pkgmgr[PkgMgr.UPDATE.value].format(quiet=quiet_flag,
                                                             packages=' '.join(packages))
        update_cmd = f"{{ {update_meta_cmd}; }} && {{ {update_pkgs_cmd}; }}"
    else:
        update_cmd = pkgmgr[PkgMgr.UPDATE_ALL.value].format(quiet=quiet_flag)
    if shared_containers := state.get_other_shared_containers(conf.box_name,
                                                              runtime_conf.shared_root):
        # show all the containers sharing the same shared root
        print_warn("The operation will also update packages in other containers having the same "
                   f"shared root directory: {', '.join(shared_containers)}")
    return int(run_command(build_shell_command(docker_cmd, conf.box_name, update_cmd),
                           exit_on_error=False, error_msg="updating packages"))
