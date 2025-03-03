"""
Code for the `ybox-cmd` script that is used to execute programs in an active ybox container.
"""

import argparse
import sys

from ybox.cmd import parser_version_check, run_command
from ybox.env import get_docker_command


def main() -> None:
    """main function for `ybox-cmd` script"""
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    """
    Main entrypoint of `ybox-cmd` that takes a list of arguments which are usually the
    command-line arguments of the `main()` function. Pass ["-h"]/["--help"] to see all the
    available arguments with help message for each.

    :param argv: arguments to the function (main function passes `sys.argv[1:]`)
    """
    args = parse_args(argv)
    docker_cmd = get_docker_command()
    container_name = args.container_name

    docker_args = [docker_cmd, "exec"]
    if not args.skip_terminal:
        docker_args.append("-it")
    docker_args.append(container_name)
    if isinstance(args.command, str):
        docker_args.append(args.command)
    else:
        docker_args.extend(args.command)
    run_command(docker_args, error_msg=f"{args.command} execution on '{container_name}'")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse command-line arguments for the program and return the result :class:`argparse.Namespace`.

    :param argv: the list of arguments to be parsed
    :return: the result of parsing using the `argparse` library as a :class:`argparse.Namespace`
    """
    parser = argparse.ArgumentParser(description="Run a command on an active ybox container")
    parser.add_argument("-s", "--skip-terminal", action="store_true",
                        help="skip interactive pseudo-terminal for the command "
                             "(i.e. skip -it options to podman/docker)")
    parser.add_argument("container_name", type=str, help="name of the active ybox")
    parser.add_argument("command", nargs="*", default="/bin/bash",
                        help="run the given command (default is /bin/bash)")
    parser_version_check(parser, argv)
    return parser.parse_args(argv)
