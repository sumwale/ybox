import argparse
import sys

from zbox.cmd import get_docker_command, run_command


def main() -> None:
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    args = parse_args(argv)
    docker_cmd = get_docker_command(args, "-d")
    container_name = args.container_name

    # verify_zbox_state(docker_cmd, container_name, ["running"], error_msg=" active ")

    docker_args = [docker_cmd, "exec", "-it", container_name]
    if isinstance(args.command, str):
        docker_args.append(args.command)
    else:
        docker_args.extend(args.command)
    run_command(docker_args, error_msg=f"{args.command} execution on '{container_name}'")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a command on an active zbox container")
    parser.add_argument("-d", "--docker-path", type=str,
                        help="path of docker/podman if not in /usr/bin")
    parser.add_argument("container_name", type=str, help="name of the active zbox")
    parser.add_argument("command", nargs="*", default="/bin/bash",
                        help="run the given command (default is /bin/bash)")
    return parser.parse_args(argv)
