import argparse
import sys

from ybox.cmd import check_ybox_exists, get_docker_command, run_command
from ybox.print import print_info


def main() -> None:
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    args = parse_args(argv)
    docker_cmd = get_docker_command(args, "-d")
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
    parser = argparse.ArgumentParser(
        description="Show logs from an active or stopped ybox container")
    parser.add_argument("-d", "--docker-path", type=str,
                        help="path of docker/podman if not in /usr/bin")
    parser.add_argument("-f", "--follow", action="store_true",
                        help="follow log output like 'tail -f'")
    parser.add_argument("container_name", type=str, help="name of the running ybox")
    return parser.parse_args(argv)
