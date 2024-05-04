import argparse
import sys

from ybox.cmd import get_docker_command, run_command, verify_ybox_state
from ybox.print import fgcolor, print_color


def main() -> None:
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    args = parse_args(argv)
    docker_cmd = get_docker_command(args, "-d")
    container_name = args.container_name

    verify_ybox_state(docker_cmd, container_name, ["exited", "stopped"], error_msg=" stopped ")

    print_color(f"Restarting ybox container '{container_name}'", fg=fgcolor.cyan)
    run_command([docker_cmd, "container", "start", container_name], error_msg="container start")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restart a stopped ybox container")
    parser.add_argument("-d", "--docker-path", type=str,
                        help="path of docker/podman if not in /usr/bin")
    parser.add_argument("container_name", type=str, help="name of the stopped ybox")
    return parser.parse_args(argv)
