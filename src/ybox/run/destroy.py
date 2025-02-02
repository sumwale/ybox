"""
Code for the `ybox-destroy` script that is used to destroy an active or stopped ybox container.
"""

import argparse
import sys

from ybox.cmd import check_ybox_exists, run_command
from ybox.env import Environ
from ybox.print import (fgcolor, print_color, print_error, print_notice,
                        print_warn)
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

    check_ybox_exists(docker_cmd, container_name, exit_on_error=True)
    print_color(f"Stopping ybox container '{container_name}'", fg=fgcolor.cyan)
    # continue even if this fails since the container may already be in stopped state
    run_command([docker_cmd, "container", "stop", container_name],
                exit_on_error=False, error_msg=f"stopping '{container_name}'")

    print_warn(f"Removing ybox container '{container_name}'")
    rm_args = [docker_cmd, "container", "rm"]
    if args.force:
        rm_args.append("--force")
    rm_args.append(container_name)
    run_command(rm_args, error_msg=f"removing '{container_name}'")

    # check and remove any dangling container references in state database
    valid_containers = set(get_all_containers(docker_cmd))

    # remove the state from the database
    print_warn(f"Clearing ybox state for '{container_name}'")
    with YboxStateManagement(env) as state:
        if not state.unregister_container(container_name):
            print_error(f"No entry found for '{container_name}' in the state database")
            sys.exit(1)
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
    parser.add_argument("container_name", type=str, help="name of the active ybox")
    return parser.parse_args(argv)


def get_all_containers(docker_cmd: str) -> list[str]:
    """
    Get all the valid containers as known to the container manager.

    :param docker_cmd: the podman/docker executable to use
    :return: list of valid container names
    """
    result = run_command([docker_cmd, "container", "ls", "--all", "--format={{ .Names }}"],
                         capture_output=True, exit_on_error=False, error_msg="listing containers")
    return [] if isinstance(result, int) else result.splitlines()


def remove_orphans_from_db(valid_containers: set[str], state: YboxStateManagement) -> None:
    """
    Unregister orphan container entries from the state database.

    :param valid_containers: set of valid container names from :func:`get_all_containers`
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    """
    orphans = set(state.get_containers()) - valid_containers
    if orphans:
        print_notice(f"Removing orphan container entries from database: {', '.join(orphans)}")
        for orphan in orphans:
            state.unregister_container(orphan)
