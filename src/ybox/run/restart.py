"""
Code for the `ybox-restart` script that is used to restart an active or stopped ybox container.
"""

import argparse
import sys
import time

from ybox.cmd import (check_active_ybox, check_ybox_state, get_docker_command,
                      run_command)
from ybox.print import fgcolor, print_color


def main() -> None:
    """main function for `ybox-restart` script"""
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    """
    Main entrypoint of `ybox-restart` that takes a list of arguments which are usually the
    command-line arguments of the `main()` function. Pass ["-h"]/["--help"] to see all the
    available arguments with help message for each.

    :param argv: arguments to the function (main function passes `sys.argv[1:]`)
    """
    args = parse_args(argv)
    docker_cmd = get_docker_command(args, "-d")
    container_name = args.container_name

    if check_active_ybox(docker_cmd, container_name):
        print_color(f"Stopping ybox container '{container_name}'", fg=fgcolor.cyan)
        run_command([docker_cmd, "container", "stop", container_name], error_msg="container stop")
        time.sleep(2)

    check_ybox_state(docker_cmd, container_name, ["exited", "stopped"], exit_on_error=True,
                     cnt_state_msg=" stopped")

    print_color(f"Starting ybox container '{container_name}'", fg=fgcolor.cyan)
    run_command([docker_cmd, "container", "start", container_name], error_msg="container start")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse command-line arguments for the program and return the result :class:`argparse.Namespace`.

    :param argv: the list of arguments to be parsed
    :return: the result of parsing using the `argparse` library as a :class:`argparse.Namespace`
    """
    parser = argparse.ArgumentParser(description="Restart a ybox container or start a stopped one")
    parser.add_argument("-d", "--docker-path", type=str,
                        help="path of docker/podman if not in /usr/bin")
    parser.add_argument("container_name", type=str, help="name of the ybox")
    return parser.parse_args(argv)
