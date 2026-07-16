"""
Code for the `ybox-launch` script that is used to launch an existing ybox container.
"""

import argparse
import os
import sys
from pathlib import Path

from ybox.cmd import parser_version_check, run_command
from ybox.consts import Consts
from ybox.env import Environ
from ybox.print import print_error, print_info
from ybox.run.control import stop_container_impl, wait_for_container_stop
from ybox.util import DynamicToken


def main() -> None:
    """main function for `ybox-launch` script"""
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    """
    Main entrypoint of `ybox-launch` that takes a list of arguments which are usually the
    command-line arguments of the `main()` function. Pass ["-h"]/["--help"] to see all the
    available arguments with help message for each.

    :param argv: arguments to the function (main function passes `sys.argv[1:]`)
    """
    args = parse_args(argv)
    env = Environ()
    container_name = args.container
    # read YBOX_CONTAINER_MANAGER from the env file and update in env if found
    container_env = f"{env.container_config_dir(container_name)}/{Consts.container_env_file()}"
    if os.path.exists(container_env):
        manager_prefix = f"{Consts.container_manager_envvar()}="
        with open(container_env, "r", encoding="utf-8") as env_fd:
            while env_line := env_fd.readline():
                if env_line.startswith(manager_prefix):
                    env.set_docker_cmd(env_line[len(manager_prefix):].rstrip())

    if args.rm:
        stop_container_impl(env.docker_cmd, container_name, timeout=10, remove=True,
                            force_remove=False, ignore_stopped=True)
    print_info(f"Launching ybox container '{container_name}'")
    launch_container(env, container_name)
    if args.wait:
        # arguments are a superset of those for `ybox-control stop`, so can pass args as is
        wait_for_container_stop(env.docker_cmd, args)


def launch_container(env: Environ, container_name: str) -> None:
    """
    Launches a ybox container using `podman`/`docker run` with the arguments and environment as
    defined in the container's configuration directory (~/.config/ybox/containers/<name>).

    :param env: an instance of the current :class:`Environ`
    :param container_name: name of the ybox container
    """
    container_config_dir = env.container_config_dir(container_name)
    run_args_file = Path(container_config_dir, Consts.container_args_file())
    run_args_str = run_args_file.read_text(encoding="utf-8")
    # resolve dynamic args using the obsolete dynamic arguments file or in-place tokens
    dyn_args_file = Path(container_config_dir, "args.dyn")
    has_empty = False
    if dyn_args_file.exists():
        dyn_args_str = dyn_args_file.read_text(encoding="utf-8")
        dyn_args = [DynamicToken[fname].value[0](env) for fname in dyn_args_str.splitlines()]
        has_empty = "" in dyn_args
        run_args = run_args_str.format(*dyn_args).splitlines()
    else:
        run_args = run_args_str.splitlines()
        # resolve the dynamic tokens of the form {<NAME>}
        for arg_idx, arg in enumerate(run_args):
            if arg[0] == "{" and arg[len(arg) - 1] == "}":
                run_args[arg_idx] = DynamicToken[arg[1:len(arg) - 1]].value[0](env)
                has_empty = run_args[arg_idx] == ""
    if has_empty:
        run_args = [arg for arg in run_args if arg]

    docker_run = [env.docker_cmd, "run"]
    docker_run.extend(run_args)
    if (code := run_command(docker_run, exit_on_error=False)) != 0:
        print_error(f"Also check 'ybox-logs {container_name}' for details")
        sys.exit(int(code))


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse command-line arguments for the program and return the result :class:`argparse.Namespace`.

    :param argv: the list of arguments to be parsed
    :return: the result of parsing using the `argparse` library as a :class:`argparse.Namespace`
    """
    parser = argparse.ArgumentParser(description="Launch a container created using `ybox-create`")
    parser.add_argument("-w", "--wait", action="store_true",
                        help="wait for the launched container to stop")
    parser.add_argument("-t", "--timeout", type=int, default=sys.maxsize,
                        help="time in seconds to wait for the container to stop when -w/--wait "
                             f"argument has been provided (default is {sys.maxsize} secs)")
    parser.add_argument("-R", "--rm", action="store_true",
                        help="stop and remove the container before launch")
    parser.add_argument("container", type=str, help="name of the ybox container to launch")
    parser_version_check(parser, argv)
    return parser.parse_args(argv)
