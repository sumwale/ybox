"""
Code for the `ybox-control` script that is used to start/stop/restart a ybox container.
"""

import argparse
import sys
import time

from ybox.cmd import (check_active_ybox, get_ybox_state, parser_version_check,
                      run_command)
from ybox.config import StaticConfiguration
from ybox.env import Environ, get_docker_command
from ybox.print import fgcolor, print_color, print_error
from ybox.util import wait_for_ybox_container

# TODO: SW: add backup/restore of the running image with the option to backup $HOME of the
# container user, and shared root warning if it is being used


def main() -> None:
    """main function for `ybox-control` script"""
    main_argv(sys.argv[1:])


def start_container(docker_cmd: str, args: argparse.Namespace):
    """
    Start an existing ybox container.

    :param docker_cmd: the podman/docker executable to use
    :param args: arguments having all attributes passed by the user
    """
    container_name = args.container
    if status := get_ybox_state(docker_cmd, container_name, (), exit_on_error=False):
        if status[0] == "running":
            print_color(f"ybox container '{container_name}' already active", fg=fgcolor.cyan)
        else:
            print_color(f"Starting ybox container '{container_name}'", fg=fgcolor.cyan)
            run_command([docker_cmd, "container", "start", container_name],
                        error_msg="container start")
            conf = StaticConfiguration(Environ(docker_cmd), status[1], container_name)
            wait_for_ybox_container(docker_cmd, conf, args.timeout)
    else:
        print_error(f"No ybox container '{container_name}' found")
        sys.exit(1)


def stop_container(docker_cmd: str, args: argparse.Namespace):
    """
    Stop an active ybox container.

    :param docker_cmd: the podman/docker executable to use
    :param args: arguments having all attributes passed by the user
    """
    _stop_container(docker_cmd, args.container, args.timeout,
                    fail_on_error=not args.ignore_stopped)


def _stop_container(docker_cmd: str, container_name: str, timeout: int,
                    fail_on_error: bool):
    """
    Stop an active ybox container.

    :param docker_cmd: the podman/docker executable to use
    :param container_name: name of the container
    :param timeout: seconds to wait for container to stop before killing the container
    :param fail_on_error: if True then show error message on failure to stop else ignore
    """
    if check_active_ybox(docker_cmd, container_name):
        print_color(f"Stopping ybox container '{container_name}'", fg=fgcolor.cyan)
        run_command([docker_cmd, "container", "stop", "-t", str(timeout), container_name],
                    error_msg="container stop")
        for _ in range(timeout * 2):
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


def restart_container(docker_cmd: str, args: argparse.Namespace):
    """
    Restart an existing ybox container.

    :param docker_cmd: the podman/docker executable to use
    :param args: arguments having all attributes passed by the user
    """
    _stop_container(docker_cmd, args.container, timeout=int(args.timeout / 2), fail_on_error=False)
    start_container(docker_cmd, args)


def show_container_status(docker_cmd: str, args: argparse.Namespace) -> None:
    """
    Show container status which will be a string like running/exited.

    :param docker_cmd: the podman/docker executable to use
    :param args: arguments having all attributes passed by the user
    """
    container_name = args.container
    if status := get_ybox_state(docker_cmd, container_name, (), exit_on_error=False):
        print(status[0])
    else:
        print_error(f"No ybox container '{container_name}' found")


def wait_for_container_stop(docker_cmd: str, args: argparse.Namespace) -> None:
    """
    Wait for an active container to stop.

    :param docker_cmd: the podman/docker executable to use
    :param args: arguments having all attributes passed by the user
    """
    while check_active_ybox(docker_cmd, args.container):
        time.sleep(2)


def main_argv(argv: list[str]) -> None:
    """
    Main entrypoint of `ybox-control` that takes a list of arguments which are usually the
    command-line arguments of the `main()` function. Pass ["-h"]/["--help"] to see all the
    available arguments with help message for each.

    :param argv: arguments to the function (main function passes `sys.argv[1:]`)
    """
    args = parse_args(argv)
    docker_cmd = get_docker_command()
    args.func(docker_cmd, args)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse command-line arguments for the program and return the result :class:`argparse.Namespace`.

    :param argv: the list of arguments to be parsed
    :return: the result of parsing using the `argparse` library as a :class:`argparse.Namespace`
    """
    parser = argparse.ArgumentParser(description="control ybox containers")
    operations = parser.add_subparsers(title="Operations", required=True, metavar="OPERATION",
                                       help="DESCRIPTION")

    start = operations.add_parser("start", help="start a ybox container")
    _add_subparser_args(start, 60, "time in seconds to wait for a container to start")
    start.set_defaults(func=start_container)

    stop = operations.add_parser("stop", help="stop a ybox container")
    _add_subparser_args(stop, 10,
                        "time in seconds to wait for a container to stop before killing it")
    stop.add_argument("-I", "--ignore-stopped", action="store_true",
                      help="don't fail on an already stopped container")
    stop.set_defaults(func=stop_container)

    restart = operations.add_parser("restart", help="restart a ybox container")
    _add_subparser_args(restart, 60, "time in seconds to wait for a container to restart")
    restart.set_defaults(func=restart_container)

    status = operations.add_parser("status", help="show status of a ybox container")
    _add_subparser_args(status, 0, "")
    status.set_defaults(func=show_container_status)

    wait = operations.add_parser("wait", help="wait for an active ybox container to stop")
    _add_subparser_args(wait, 0, "")
    wait.set_defaults(func=wait_for_container_stop)

    parser_version_check(parser, argv)
    return parser.parse_args(argv)


def _add_subparser_args(subparser: argparse.ArgumentParser, timeout_default: int,
                        timeout_help: str) -> None:
    """
    Add arguments for the sub-operation of the ybox-control command.

    :param subparser: the :class:`argparse.ArgumentParser` object for the sub-command
    :param timeout_default: default value for the -t/--timeout argument, or 0 to skip the argument
    :param timeout_help: help string for the -t/--timeout argument
    """
    if timeout_default != 0:
        subparser.add_argument("-t", "--timeout", type=int, default=timeout_default,
                               help=timeout_help)
    subparser.add_argument("container", help="name of the ybox")
