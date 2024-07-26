import argparse
import sys

from ybox.cmd import check_ybox_exists, get_docker_command, run_command
from ybox.env import Environ
from ybox.print import fgcolor, print_color, print_error, print_warn
from ybox.state import YboxStateManagement


def main() -> None:
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    args = parse_args(argv)
    docker_cmd = get_docker_command(args, "-d")
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

    # remove the state from the database
    print_warn(f"Clearing ybox state for '{container_name}'")
    with YboxStateManagement(Environ()) as state:
        if not state.unregister_container(container_name):
            print_error(f"No entry found for '{container_name}' in the state database")
            sys.exit(1)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stop and remove an active ybox container")
    parser.add_argument("-d", "--docker-path", type=str,
                        help="path of docker/podman if not in /usr/bin")
    parser.add_argument("-f", "--force", action="store_true",
                        help="force destroy the container using SIGKILL if required")
    parser.add_argument("container_name", type=str, help="name of the active ybox")
    return parser.parse_args(argv)
