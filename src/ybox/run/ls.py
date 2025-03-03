"""
Code for the `ybox-ls` script that is used to show the active or stopped ybox containers.
"""

import argparse
import sys

from ybox.cmd import YboxLabel, parser_version_check, run_command
from ybox.env import get_docker_command


def main() -> None:
    """main function for `ybox-ls` script"""
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    """
    Main entrypoint of `ybox-ls` that takes a list of arguments which are usually the
    command-line arguments of the `main()` function. Pass ["-h"]/["--help"] to see all the
    available arguments with help message for each.

    :param argv: arguments to the function (main function passes `sys.argv[1:]`)
    """
    args = parse_args(argv)
    docker_cmd = get_docker_command()

    docker_args = [docker_cmd, "container", "ls"]
    if args.all:
        docker_args.append("--all")
        docker_args.append(f"--filter=label={YboxLabel.CONTAINER_TYPE.value}")
    else:
        docker_args.append(f"--filter=label={YboxLabel.CONTAINER_PRIMARY.value}")
    if args.filter:
        for flt in args.filter:
            docker_args.append(f"--filter={flt}")
    if args.format:
        docker_args.append(f"--format={args.format}")
    if args.long_format:
        docker_args.append("--no-trunc")
    run_command(docker_args, error_msg="listing ybox containers")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse command-line arguments for the program and return the result :class:`argparse.Namespace`.

    :param argv: the list of arguments to be parsed
    :return: the result of parsing using the `argparse` library as a :class:`argparse.Namespace`
    """
    parser = argparse.ArgumentParser(description="List ybox containers")
    parser.add_argument("-a", "--all", action="store_true",
                        help="show all containers including stopped and temporary ones; "
                             "default is to show only active ybox containers and also skip "
                             "any temporary containers spun by ybox-create")
    parser.add_argument("-f", "--filter", type=str, action="append",
                        help="apply filter to output which is in the <key>=<value> format as "
                             "accepted by podman/docker (can be specified multiple times)")
    parser.add_argument("-s", "--format", type=str,
                        help="format output using a template as accepted by podman/docker (see "
                             "https://docs.docker.com/reference/cli/docker/container/ls)")
    parser.add_argument("-l", "--long-format", action="store_true",
                        help="display extended information without truncating fields")
    parser_version_check(parser, argv)
    return parser.parse_args(argv)
