"""
Code for the `ybox-control` script that is used to start/stop/restart a ybox container.
"""

import argparse
import sys
import time

from ybox.cmd import check_active_ybox, get_ybox_state, run_command
from ybox.config import StaticConfiguration
from ybox.env import Environ, get_docker_command
from ybox.print import fgcolor, print_color, print_error
from ybox.util import wait_for_ybox_container


def main() -> None:
    """main function for `ybox-control` script"""
    main_argv(sys.argv[1:])


def start_container(docker_cmd: str, container_name: str):
    """
    Start an existing ybox container.

    :param docker_cmd: the podman/docker executable to use
    :param container_name: name of the container
    """
    if status := get_ybox_state(docker_cmd, container_name, (), exit_on_error=False):
        if status[0] == "running":
            print_color(f"Ybox container '{container_name}' already active", fg=fgcolor.cyan)
        else:
            print_color(f"Starting ybox container '{container_name}'", fg=fgcolor.cyan)
            run_command([docker_cmd, "container", "start", container_name],
                        error_msg="container start")
            conf = StaticConfiguration(Environ(docker_cmd), status[1], container_name)
            wait_for_ybox_container(docker_cmd, conf)
    else:
        print_error(f"No ybox container '{container_name}' found")
        sys.exit(1)


def stop_container(docker_cmd: str, container_name: str, fail_on_error: bool):
    """
    Stop a ybox container.

    :param docker_cmd: the podman/docker executable to use
    :param container_name: name of the container
    :param fail_on_error: if True then show error message on failure to stop else ignore
    """
    if check_active_ybox(docker_cmd, container_name):
        print_color(f"Stopping ybox container '{container_name}'", fg=fgcolor.cyan)
        run_command([docker_cmd, "container", "stop", container_name], error_msg="container stop")
        for _ in range(120):
            time.sleep(0.5)
            if get_ybox_state(docker_cmd, container_name, ("exited", "stopped"),
                              exit_on_error=False, state_msg=" stopped"):
                return
        print_error(f"Failed to stop ybox container '{container_name}'")
    elif fail_on_error:
        print_error(f"No active ybox container '{container_name}' found")
        sys.exit(1)
    else:
        print_color(f"No active ybox container '{container_name}' found", fg=fgcolor.cyan)


def main_argv(argv: list[str]) -> None:
    """
    Main entrypoint of `ybox-control` that takes a list of arguments which are usually the
    command-line arguments of the `main()` function. Pass ["-h"]/["--help"] to see all the
    available arguments with help message for each.

    :param argv: arguments to the function (main function passes `sys.argv[1:]`)
    """
    args = parse_args(argv)
    docker_cmd = get_docker_command()
    container_name = args.container_name
    if args.action == "start":
        start_container(docker_cmd, container_name)
    elif args.action == "stop":
        stop_container(docker_cmd, container_name, fail_on_error=True)
    elif args.action == "restart":
        stop_container(docker_cmd, container_name, fail_on_error=False)
        start_container(docker_cmd, container_name)
    elif args.action == "status":
        if status := get_ybox_state(docker_cmd, container_name, (), exit_on_error=False):
            print(status[0])
        else:
            print_error(f"No ybox container '{container_name}' found")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse command-line arguments for the program and return the result :class:`argparse.Namespace`.

    :param argv: the list of arguments to be parsed
    :return: the result of parsing using the `argparse` library as a :class:`argparse.Namespace`
    """
    parser = argparse.ArgumentParser(description="control ybox containers")
    parser.add_argument("action", choices=["start", "stop", "restart", "status"],
                        help="action to perform")
    parser.add_argument("container_name", help="name of the ybox")
    return parser.parse_args(argv)
