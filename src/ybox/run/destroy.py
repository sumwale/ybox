"""
Code for the `ybox-destroy` script that is used to destroy an active or stopped ybox container.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ybox.cmd import (delete_container_directory, parser_version_check,
                      run_command)
from ybox.config import StaticConfiguration
from ybox.consts import Consts
from ybox.env import Environ
from ybox.pkg.inst import get_parsed_box_conf
from ybox.print import (fgcolor, print_color, print_error, print_notice,
                        print_warn)
from ybox.run.control import stop_container_impl
from ybox.state import YboxStateManagement


def main() -> None:
    """main function for `ybox-destroy` script"""
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    """
    Main entrypoint of `ybox-destroy` that takes a list of arguments which are usually the
    command-line arguments of the `main()` function. Pass ["-h"]/["--help"] to see all the
    available arguments with help message for each.

    :param argv: arguments to the function (main function passes `sys.argv[1:]`)
    """
    args = parse_args(argv)
    env = Environ()
    docker_cmd = env.docker_cmd
    container_name = args.container_name

    # check if there is a systemd service for the container
    ybox_svc_prefix = ybox_service_prefix(container_name)
    ybox_svc = f"{ybox_svc_prefix}.service"
    systemctl = check_systemd_service_present(ybox_svc)

    # service stop will both stop and remove the service, but user may have started the container
    # outside of the service, so check for running service first
    if systemctl and run_command([systemctl, "--user", "--quiet", "is-active", ybox_svc],
                                 exit_on_error=False, error_msg="SKIP") == 0:
        print_color(f"Stopping ybox service '{ybox_svc}'", fg=fgcolor.cyan)
        run_command([systemctl, "--user", "stop", ybox_svc],
                    exit_on_error=False, error_msg=f"stopping service '{ybox_svc}'")
    else:
        stop_container_impl(docker_cmd, container_name, 10, True, args.force, ignore_stopped=True)

    # remove shared TMPDIR if present
    tmpdir = f"/var/tmp/ybox.{container_name}"
    if os.path.isdir(tmpdir) and os.access(tmpdir, os.W_OK):
        shutil.rmtree(tmpdir)

    # remove systemd service file and reload daemon
    systemd_dir = env.systemd_user_conf_dir()
    if systemctl:
        print_color(f"Removing systemd service '{ybox_svc}' and reloading daemon", fg=fgcolor.cyan)
        run_command([systemctl, "--user", "disable", ybox_svc], exit_on_error=False)
        Path(systemd_dir, ybox_svc).unlink(missing_ok=True)
        run_command([systemctl, "--user", "daemon-reload"], exit_on_error=False)
    else:
        # remove the autostart file if present
        Path(f"{env.home}/.config/autostart/{ybox_svc_prefix}.desktop").unlink(missing_ok=True)
    # also try to delete the .env file from the old location
    Path(systemd_dir, f".{ybox_svc_prefix}.env").unlink(missing_ok=True)

    # check and remove any dangling container references in state database
    valid_containers = get_all_containers(docker_cmd, env)

    # remove the state from the database
    print_warn(f"Clearing ybox state for '{container_name}'")
    with YboxStateManagement(env) as state:
        state.begin_transaction()
        if (runtime_conf := state.get_container_configuration(container_name)) is None:
            print_error(f"No entry found for '{container_name}' in the state database")
            sys.exit(1)
        conf = StaticConfiguration(env, runtime_conf.distribution, container_name)
        # remove the container specific configuration directory
        shutil.rmtree(conf.container_config_dir, ignore_errors=True)
        if not args.keep_files:
            print_notice("Removing container configuration files and scripts")
            shutil.rmtree(conf.configs_dir, ignore_errors=True)
            shutil.rmtree(conf.scripts_dir, ignore_errors=True)
            Path(conf.status_file).unlink(missing_ok=True)
            if not runtime_conf.shared_root:
                # remove non-shared root directory
                unshared_root = conf.unshared_root()
                if os.path.isdir(unshared_root):
                    print_notice(f"Removing unshared root directory {unshared_root}")
                    delete_container_directory(unshared_root, env)
                # remove the container specific image
                container_image = conf.box_image(False)
                print_notice(f"Removing unshared container image {container_image}")
                run_command([docker_cmd, "image", "rm", container_image], exit_on_error=False,
                            error_msg="SKIP")
            # delete all container related files if required
            if args.delete_files:
                box_conf = get_parsed_box_conf(runtime_conf.ini_config)
                assert box_conf is not None
                home_dir = box_conf["base"]["home"]
                if os.path.isdir(home_dir):
                    print_notice(f"Removing home directory {home_dir}")
                    delete_container_directory(home_dir, env)
                container_dir = f"{env.data_dir}/{container_name}"
                print_notice(f"Removing container directory {container_dir}")
                delete_container_directory(container_dir, env)
            state.unregister_container(container_name)
            remove_orphans_from_db(valid_containers, state)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse command-line arguments for the program and return the result :class:`argparse.Namespace`.

    :param argv: the list of arguments to be parsed
    :return: the result of parsing using the `argparse` library as a :class:`argparse.Namespace`
    """
    parser = argparse.ArgumentParser(description="Stop and remove an active ybox container")
    parser.add_argument("-f", "--force", action="store_true",
                        help="force destroy the container using SIGKILL if required")
    parser.add_argument("-D", "--delete-files", action="store_true",
                        help="remove all files of the container including the home directory")
    parser.add_argument("-K", "--keep-files", action="store_true",
                        help="keep the files of the container including the storage location of a "
                        "non-shared root one, configs and scripts directories, non-shared image; "
                        "systemd/autostart service and env/args files are still deleted")
    parser.add_argument("container_name", type=str, help="name of the active ybox")
    parser_version_check(parser, argv)
    return parser.parse_args(argv)


def ybox_service_prefix(container_name: str) -> str:
    """service name prefix to be used by systemd/autostart for given ybox container name"""
    return container_name if container_name.startswith("ybox-") else f"ybox-{container_name}"


def check_systemd_service_present(user_svc: str) -> str:
    """
    Check if the given user systemd service is present and return the PATH of system installed
    `systemctl` tool if true, else return empty string.

    :param user_svc: name the user systemd service file
    :return: full path of `systemctl` if installed and user systemd service is available else empty
    """
    if (systemctl := shutil.which("systemctl", path=os.pathsep.join(Consts.sys_bin_dirs()))) and \
            subprocess.run([systemctl, "--user", "--quiet", "list-unit-files", user_svc],
                           check=False, capture_output=True).returncode == 0:
        return systemctl
    return ""


def get_all_containers(docker_cmd: str, env: Environ, only_unlaunched: bool = False) -> set[str]:
    """
    Get all the valid containers as known to the container manager.

    :param docker_cmd: the podman/docker executable to use
    :param env: an instance of the current :class:`Environ`
    :param only_unlaunched: if True then return only the containers that have not been launched yet
    :return: list of valid container names
    """
    result = run_command([docker_cmd, "container", "ls", "--all", "--format={{ .Names }}"],
                         capture_output=True, exit_on_error=False, error_msg="listing containers")
    if isinstance(result, int):
        return set[str]()
    # also add unlaunched containers using the configuration files
    launched = set(result.splitlines())
    containers_dir = Path(env.config_dir, Consts.containers_config_dir())
    if containers_dir.exists():
        defined = {d.name for d in containers_dir.iterdir()
                   if Path(d, Consts.container_args_file()).exists()}
        if only_unlaunched:
            return defined.difference(launched)
        launched.update(defined)
        return launched
    return set[str]() if only_unlaunched else launched


def remove_orphans_from_db(valid_containers: set[str], state: YboxStateManagement) -> None:
    """
    Unregister orphan container entries from the state database. This takes the output of
    :func:`get_all_containers` as argument and should be invoked inside `YboxStateManagement`
    context manager (i.e. with state database as locked), while the call to `get_all_containers`
    can be outside the lock.

    :param valid_containers: set of valid container names from :func:`get_all_containers`
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    """
    if not os.environ.get("YBOX_TESTING"):
        orphans = set(state.get_containers()) - valid_containers
        if orphans:
            print_notice(f"Removing orphan container entries from database: {', '.join(orphans)}")
            for orphan in orphans:
                state.unregister_container(orphan)
