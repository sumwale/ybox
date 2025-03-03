"""
Code for the `ybox-logs` script that is used to show the podman/docker logs of an active
ybox container.
"""

import argparse
import sys

from ybox.cmd import check_ybox_exists, parser_version_check, run_command
from ybox.env import get_docker_command
from ybox.print import print_info


def main() -> None:
    """main function for `ybox-logs` script"""
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    """
    Main entrypoint of `ybox-logs` that takes a list of arguments which are usually the
    command-line arguments of the `main()` function. Pass ["-h"]/["--help"] to see all the
    available arguments with help message for each.

    :param argv: arguments to the function (main function passes `sys.argv[1:]`)
    """
    args = parse_args(argv)
    docker_cmd = get_docker_command()
    container_name = args.container_name

    check_ybox_exists(docker_cmd, container_name, exit_on_error=True)

    docker_args = [docker_cmd, "container", "logs"]
    if args.follow:
        docker_args.append("-f")
    docker_args.append(container_name)
    try:
        run_command(docker_args, error_msg=f"showing logs '{container_name}'")
    except KeyboardInterrupt:
        # allow for user interruption during follow or otherwise for a large log
        print()
        print_info("Interrupt")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse command-line arguments for the program and return the result :class:`argparse.Namespace`.

    :param argv: the list of arguments to be parsed
    :return: the result of parsing using the `argparse` library as a :class:`argparse.Namespace`
    """
    parser = argparse.ArgumentParser(
        description="Show logs from an active or stopped ybox container")
    parser.add_argument("-f", "--follow", action="store_true",
                        help="follow log output like 'tail -f'")
    parser.add_argument("container_name", type=str, help="name of the running ybox")
    parser_version_check(parser, argv)
    return parser.parse_args(argv)
