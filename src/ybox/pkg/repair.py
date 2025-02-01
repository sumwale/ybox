"""
Try to repair packages and state after a failed package operation or an interrupt/kill.
"""

import argparse
import subprocess
import time
from configparser import SectionProxy

from ybox.cmd import (PkgMgr, build_shell_command, check_active_ybox,
                      run_command)
from ybox.config import StaticConfiguration
from ybox.print import (fgcolor, print_color, print_error, print_info,
                        print_warn)
from ybox.state import RuntimeConfiguration, YboxStateManagement

# TODO: SW: repair should work even if no containers are active (just remove the locks)
# Also, just checking lock file existing lock file existence is not enough (e.g. for dpkg/apt)
# and may need to check if they are locked by any process after kill so define this in distro.ini


def repair_package_state(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                         conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                         state: YboxStateManagement) -> int:
    """
    Try to repair packages and state after a failed package operation or an interrupt/kill
    or dangling package manager processes and/or locks.

    :param args: arguments having all attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :return: integer exit status of repair command where 0 represents success
    """
    quiet: bool = args.quiet
    quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value] if quiet else ""
    # find all the containers sharing the same shared root
    if runtime_conf.shared_root:
        containers = [c for c in state.get_containers(shared_root=runtime_conf.shared_root)
                      if check_active_ybox(docker_cmd, c)]
    else:
        containers = [conf.box_name]
    # first check for active package operations across all containers on the same shared root
    # and kill them
    if not _kill_processes(pkgmgr, docker_cmd, containers, quiet):
        return 1
    # remove any package manager related dangling locks
    _remove_locks(pkgmgr, docker_cmd, containers, quiet)

    # run package manager to repair any failed package operations
    repair_cmd = pkgmgr[PkgMgr.REPAIR.value]
    if args.extensive:
        resp = "y" if quiet else input("Repair thoroughly by reinstalling packages? (y/N) ")
        if resp.strip().lower() == "y":
            repair_cmd = pkgmgr[PkgMgr.REPAIR_ALL.value]
    if (code := int(run_command(build_shell_command(
            docker_cmd, conf.box_name, repair_cmd.format(quiet=quiet_flag)), exit_on_error=False,
            error_msg="repairing packages"))) != 0:
        return code

    # finally restart containers after user confirmation
    resp = "y" if quiet else input(f"Restart container(s) {containers}? (y/N) ")
    if resp.strip().lower() == "y":
        for container in containers:
            print_color(f"Restarting ybox container '{container}'", fg=fgcolor.cyan)
            if run_command([docker_cmd, "container", "stop", container],
                           exit_on_error=False, error_msg="container stop") == 0:
                time.sleep(2)
                run_command([docker_cmd, "container", "start", container],
                            exit_on_error=False, error_msg="container start")
    return 0


def _kill_processes(pkgmgr: SectionProxy, docker_cmd: str, containers: list[str],
                    quiet: bool) -> bool:
    """
    Kill any package manager related processes after user confirmation (if required).

    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param containers: list of affected containers having the same shared root
    :param quiet: if True then skip user confirmation before removing any lock files
    :return: true for success, else false in case of failure to kill one or more processes
    """
    processes_pattern = pkgmgr[PkgMgr.PROCESSES_PATTERN.value]
    for container in containers:
        print_info(
            f"Checking for active package manager related processes in container '{container}'")
        ps_result = run_command([docker_cmd, "exec", container, "/usr/bin/pgrep", "-fa",
                                 processes_pattern], capture_output=True, exit_on_error=False,
                                error_msg="SKIP")
        if isinstance(ps_result, int) or not (processes := ps_result.splitlines()):
            continue
        # confirm with user before killing those processes
        print_color("Following active package manager related processes were found in "
                    f"container '{container}':", fgcolor.cyan)
        for process in processes:
            pid, _, cmd = process.partition(" ")
            print(f"    [PID={pid}] {cmd}")
        resp = "y" if quiet else input("Kill the above processes? (y/N/space separated PIDs) ")
        resp = resp.strip().lower()
        if (not resp) or resp == "n":
            continue
        if resp == "y":
            pids = [process.partition(" ")[0] for process in processes]
        else:
            pids = resp.split()
        for sig in ("-INT", "-TERM", "-KILL"):
            print_warn(f"Sending {sig} signal to {' '.join(pids)} in container '{container}'")
            docker_args = [docker_cmd, "exec", container, "/usr/bin/sudo", "/bin/kill", sig]
            docker_args.extend(pids)
            subprocess.run(docker_args, check=False, stderr=subprocess.DEVNULL)
            time.sleep(2)
            # filter out only the processes that are still active
            check_res = run_command([docker_cmd, "exec", "/usr/bin/ps", "-o", "pid=", "-p",
                                     ",".join(pids)], capture_output=True, exit_on_error=False,
                                    error_msg="SKIP")
            if isinstance(check_res, int) or not (pids := check_res.split()):
                break
        if pids:
            print_error(f"Unable to kill {' '.join(pids)} in container '{container}'. You may "
                        "need to manually check inside with 'ybox-cmd' or restart the container")
            return False
    return True


def _remove_locks(pkgmgr: SectionProxy, docker_cmd: str, containers: list[str],
                  quiet: bool) -> None:
    """
    Remove any package manager related lock files after user confirmation (if required).

    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param containers: list of affected containers having the same shared root
    :param quiet: if True then skip user confirmation before removing any lock files
    """
    locks_pattern = pkgmgr[PkgMgr.LOCKS_PATTERN.value]
    ls_cmd = f"/bin/ls {locks_pattern.replace(',', ' ')} 2>/dev/null"
    for container in containers:
        print_info(f"Checking for lock files in container '{container}'")
        ls_result = subprocess.run(build_shell_command(docker_cmd, container, ls_cmd),
                                   check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        # confirm with user before removing locks
        if not (locks := ls_result.stdout.decode("utf-8").split()):
            continue
        print_color(f"Found existing lock file(s) {locks} in container '{container}'",
                    fgcolor.cyan)
        resp = "y" if quiet else input("Remove the above lock file(s)? (y/N) ")
        if resp.strip().lower() == "y":
            docker_args = [docker_cmd, "exec", container, "/usr/bin/sudo", "/bin/rm"]
            docker_args.extend(locks)
            run_command(docker_args, exit_on_error=False, error_msg="removing lock files")
