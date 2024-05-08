"""
Package management utility for ybox containers.
"""

import argparse
import sys

from ybox.cmd import YboxLabel, get_docker_command, run_command, verify_ybox_state
from ybox.config import StaticConfiguration
from ybox.env import Environ
from ybox.pkg.inst import install_package
from ybox.pkg.list import list_packages
from ybox.pkg.search import search_packages
from ybox.pkg.uninst import uninstall_package
from ybox.pkg.update import update_package
from ybox.print import print_error, print_info
from ybox.state import YboxStateManagement
from ybox.util import EnvInterpolation, config_reader, select_item_from_menu


def main() -> None:
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    args = parse_args(argv)
    docker_cmd = get_docker_command(args, "-d")
    container_name = args.ybox

    if not container_name:
        # check active containers
        containers = str(run_command([docker_cmd, "container", "ls", "--format={{ .Names }}",
                                      f"--filter=label={YboxLabel.CONTAINER_PRIMARY}"],
                                     capture_output=True, error_msg="container ls")).splitlines()
        # use the active container if there is only one of them
        if len(containers) == 1:
            container_name = containers[0]
        elif not containers:
            print_error("No active ybox container found!")
            sys.exit(1)
        elif args.quiet:
            print_error(
                f"Expected one active ybox container but found {', '.join(containers)}")
            sys.exit(1)
        else:
            print_info("Please select the container to use:", file=sys.stderr)
            if (container_name := select_item_from_menu(containers)) is None:
                sys.exit(1)

    if not args.quiet:
        print_info(f"Running the operation on '{container_name}'", file=sys.stderr)
    verify_ybox_state(docker_cmd, container_name, ["running"], error_msg=" active ")

    env = Environ()
    with YboxStateManagement(env) as state:
        if (runtime_conf := state.get_container_configuration(container_name)) is None:
            print_error(f"No entry for ybox container '{container_name}' found!")
            sys.exit(1)
        conf = StaticConfiguration(env, runtime_conf.distribution, container_name)
        env_interpolation = EnvInterpolation(env, [])
        distro_config = config_reader(
            env.search_config_path(f"distros/{conf.distribution}/distro.ini"), env_interpolation)
        pkgmgr = distro_config["pkgmgr"]
        if (code := args.func(args, pkgmgr, docker_cmd, conf, runtime_conf, state)) != 0:
            sys.exit(code)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package management across ybox containers")
    operations = parser.add_subparsers(title="Operations", required=True, metavar="OPERATION",
                                       help="DESCRIPTION")
    add_install(add_subparser(operations, "install", "install a package with dependencies"))
    add_uninstall(add_subparser(operations, "uninstall", "uninstall a package and "
                                                         "optionally its dependencies"))
    add_update(add_subparser(operations, "update", "update some or all packages"))
    add_list(add_subparser(operations, "list", "list installed packages"))
    add_search(add_subparser(operations, "search",
                             "search repository for packages with matching string"))
    # parser.add_argument("operation", type=str,
    #                    choices=("install", "uninstall", "update", "list", "info", "search",
    #                             "mark", "clean", "repair"),
    #                    help="the package operation to perform")
    return parser.parse_args(argv)


# noinspection PyProtectedMember
def add_subparser(operations: argparse._SubParsersAction, name: str,
                  hlp: str) -> argparse.ArgumentParser:
    subparser = operations.add_parser(name, help=hlp)
    add_common_args(subparser)
    return subparser


def add_common_args(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("-d", "--docker-path", type=str,
                           help="path of docker/podman if not in /usr/bin")
    subparser.add_argument("-z", "--ybox", type=str,
                           help="the ybox container to use for package operations else the user "
                                "is prompted to select a container from among the active ones")
    subparser.add_argument("-q", "--quiet", action="store_true",
                           help="proceed without asking any questions; the container selection "
                                "is also skipped and it is assumed that there is only one "
                                "active container which is selected else the operation fails")


def add_install(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("-o", "--skip-opt-deps", action="store_true",
                           help="skip installation of optional dependencies (or recommendations)")
    subparser.add_argument("-w", "--with-opt-deps", type=str,
                           help="provide comma-separated optional dependencies to install "
                                "(in which case user will not be prompted to select them)")
    subparser.add_argument("-l", "--add-dep-wrappers", action="store_true",
                           help="create local wrapper desktop and executables for the newly "
                                "installed package dependencies too (both required and optional)")
    subparser.add_argument("-c", "--check-package", action="store_true",
                           help="check for existing package before actual installation")
    subparser.add_argument("-s", "--skip-executables", action="store_true",
                           help="skip creating wrappers for invoking executables installed by "
                                "the package; default is to create wrapper executables in user's "
                                "$HOME/.local/bin directory (or using $PYTHONUSERBASE)")
    subparser.add_argument("-S", "--skip-desktop-files", action="store_true",
                           help="skip creating wrapper desktop files for those installed by the "
                                "package and its optional dependencies; default is to create "
                                "wrapper desktop files in user's $HOME/.local/share/applications "
                                "(or using $PYTHONUSERBASE)")
    subparser.add_argument("package", type=str, help="the package to install")
    subparser.set_defaults(func=install_package)


def add_uninstall(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("-k", "--keep-config-files", action="store_true",
                           help="keep system configuration and/or data files of the package")
    subparser.add_argument("-s", "--skip-deps", action="store_true",
                           help="skip uninstallation of the orphaned dependencies of the package")
    subparser.add_argument("package", type=str, help="the package to uninstall")
    subparser.set_defaults(func=uninstall_package)


def add_update(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("packages", nargs="*",
                           help="the packages to update if provided, else update the entire "
                                "installation of the container (which will end up updating all "
                                "other containers sharing the same root if configured)")
    subparser.set_defaults(func=update_package)


def add_list(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("-a", "--all", action="store_true",
                           help="show all packages including dependent packages in the output "
                                "otherwise only the packages that have been explicitly installed "
                                "are shown")
    subparser.add_argument("-o", "--os-pkgs", action="store_true",
                           help="list all packages installed in the container including those "
                                "not managed by 'ybox-pkg'; when multiple containers share the "
                                "same root directory, then it will include packages installed "
                                "on other containers; this can be combined with -a/--all "
                                "option to list all the packages including dependents")
    subparser.add_argument("-p", "--plain-separator", type=str,
                           help="show the output in 'plain' format rather than as a table with "
                                "the fields separated by the given string; it will also skip "
                                "any truncation of the 'Dependency Of' column")
    subparser.add_argument("-v", "--verbose", action="store_true",
                           help="show some package details including version, description and "
                                "whether it is a dependency or a top-level package")
    subparser.set_defaults(func=list_packages)


def add_search(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("-w", "--word", action="store_true",
                           help="match given search terms as full words")
    subparser.add_argument("-a", "--all", action="store_true",
                           help="search in package descriptions in addition to the package names")
    subparser.add_argument("-o", "--official", action="store_true",
                           help="search only in the official repositories and not the extra ones "
                                "(e.g. skip AUR repository on Arch Linux)")
    subparser.add_argument("search", nargs="+", help="one or more search terms")
    subparser.set_defaults(func=search_packages)
