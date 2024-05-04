import argparse
import sys

from zbox.cmd import get_docker_command, run_command, ZboxLabel


def main() -> None:
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    args = parse_args(argv)
    docker_cmd = get_docker_command(args, "-d")

    docker_args = [docker_cmd, "container", "ls"]
    if args.all:
        docker_args.append("--all")
        docker_args.append(f"--filter=label={ZboxLabel.CONTAINER_TYPE}")
    else:
        docker_args.append(f"--filter=label={ZboxLabel.CONTAINER_PRIMARY}")
    if args.filter:
        for flt in args.filter:
            docker_args.append(f"--filter={flt}")
    if args.format:
        docker_args.append(f"--format={args.format}")
    if args.long_format:
        docker_args.append("--no-trunc")
    run_command(docker_args, error_msg="listing zbox containers")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List zbox containers")
    parser.add_argument("-a", "--all", action="store_true",
                        help="show all containers including stopped and temporary ones; "
                             "default is to show only active zbox containers and also skip "
                             "any temporary containers spun by zbox-create")
    parser.add_argument("-d", "--docker-path", type=str,
                        help="path of docker/podman if not in /usr/bin")
    parser.add_argument("-f", "--filter", type=str, action="append",
                        help="apply filter to output which is in the <key>=<value> format as "
                             "accepted by docker/podman (can be specified multiple times)")
    parser.add_argument("-s", "--format", type=str,
                        help="format output using a template as accepted by docker/podman (see "
                             "https://docs.docker.com/reference/cli/docker/container/ls)")
    parser.add_argument("-l", "--long-format", action="store_true",
                        help="display extended information and without truncating fields")
    return parser.parse_args(argv)
