"""
Code for the `ybox-cmd` script that is used to execute programs in an active ybox container.
"""

import argparse
import os
import sys

from ybox.cmd import parser_version_check, populate_exec_cmdline, run_command
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
    container_name = str(args.container_name)

    exec_cmd: list[str] = []
    needs_tty = not args.skip_terminal
    env = ()
    if args.env:
        env = list[str]([])
        for kv in args.env:
            env.append("-e")
            env.append(kv)
    populate_exec_cmdline(docker_cmd, container_name, "", needs_tty, needs_tty, env,
                          os.getcwd(), exec_cmd)
    if isinstance(args.command, str):
        exec_cmd.append(args.command)
    else:
        for cmd in args.command:
            exec_cmd.append(" ")
            exec_cmd.append(cmd)
    run_command(["/bin/sh", "-c", "".join(exec_cmd)],
                error_msg=f"{args.command} execution on '{container_name}'")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse command-line arguments for the program and return the result :class:`argparse.Namespace`.

    :param argv: the list of arguments to be parsed
    :return: the result of parsing using the `argparse` library as a :class:`argparse.Namespace`
    """
    parser = argparse.ArgumentParser(description="Run a command on an active ybox container")
    parser.add_argument("-e", "--env", action="append", type=str,
                        help="set environment variables for the command in the container; "
                             "the environment variable can be specified with a value in the form "
                             "VAR=VALUE or without =VALUE in which case the value of the variable "
                             "is passed through from the host environment (which will be unset if "
                             "unset in the host); this option can be repeated multiple times")
    parser.add_argument("-s", "--skip-terminal", action="store_true",
                        help="skip interactive pseudo-terminal for the command "
                             "(i.e. skip -it options to podman/docker)")
    parser.add_argument("container_name", type=str, help="name of the active ybox")
    parser.add_argument("command", nargs="*", default="/bin/bash",
                        help="run the given command (default is /bin/bash)")
    parser_version_check(parser, argv)
    return parser.parse_args(argv)
