"""
Package management utility for ybox containers.
"""

import argparse
import sys
from typing import cast

from ybox.cmd import (YboxLabel, check_active_ybox, get_docker_command,
                      run_command)
from ybox.config import StaticConfiguration
from ybox.env import Environ
from ybox.pkg.clean import clean_cache
from ybox.pkg.info import info_packages
from ybox.pkg.inst import install_package
from ybox.pkg.list import list_files, list_packages
from ybox.pkg.mark import mark_package
from ybox.pkg.repair import repair_package_state
from ybox.pkg.repo import repo_add, repo_remove
from ybox.pkg.search import search_packages
from ybox.pkg.uninst import uninstall_package
from ybox.pkg.update import update_packages
from ybox.print import print_error, print_info
from ybox.state import YboxStateManagement
from ybox.util import (EnvInterpolation, config_reader, get_ybox_version,
                       select_item_from_menu)


def main() -> None:
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    args = parse_args(argv)
    # --quiet can be specified at most two times
    if args.quiet > 2:
        print_error("Argument -q/--quiet can be specified at most two times")
        sys.exit(1)
    docker_cmd = get_docker_command(args, "-d")
    container_name = args.ybox

    if container_name:
        check_active_ybox(docker_cmd, container_name, exit_on_error=True)
    else:
        # check active containers
        containers = str(run_command([docker_cmd, "container", "ls", "--format={{ .Names }}",
                                      f"--filter=label={YboxLabel.CONTAINER_PRIMARY.value}"],
                                     capture_output=True, error_msg="container ls")).splitlines()
        # use the active container if there is only one of them
        if len(containers) == 1:
            container_name = containers[0]
        elif not containers:
            print_error("No active ybox container found!")
            sys.exit(1)
        elif args.quiet:
            print_error(
                f"Expected one active ybox container but found: {', '.join(containers)}")
            sys.exit(1)
        else:
            print_info("Please select the container to use:", file=sys.stderr)
            if (container_name := select_item_from_menu(containers)) is None:
                sys.exit(1)

    if not args.quiet:
        print_info(f"Running the operation on '{container_name}'", file=sys.stderr)

    env = Environ()
    with YboxStateManagement(env) as state:
        # ensure that all state database changes are done as a single transaction and only applied
        # if there were no failures (commit/rollback are automatic at the end of `with`)
        state.begin_transaction()
        if (runtime_conf := state.get_container_configuration(container_name)) is None:
            print_error(f"No entry for ybox container '{container_name}' found!")
            sys.exit(1)
        conf = StaticConfiguration(env, runtime_conf.distribution, container_name)
        distribution_config_file = args.distribution_config if args.distribution_config \
            else conf.distribution_config(conf.distribution)
        env_interpolation = EnvInterpolation(env, [])
        distro_config = config_reader(env.search_config_path(
            distribution_config_file, only_sys_conf=True), env_interpolation)
        # if required, migrate the container to work with the latest product
        state.migrate_container(get_ybox_version(conf), conf, distro_config)
        # the "repo_cmd" flag set by the subcommands indicate whether the subcommand was
        # for package management or for repository management
        pkgmgr = distro_config["pkgmgr"]
        if args.is_repo_cmd:
            code = args.func(args, pkgmgr, distro_config["repo"], docker_cmd, conf,
                             runtime_conf, state)
        else:
            code = args.func(args, pkgmgr, docker_cmd, conf, runtime_conf, state)
        if code != 0:
            sys.exit(code)  # state will be automatically rolled back for exceptions


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package management across ybox containers")
    operations = parser.add_subparsers(title="Operations", required=True, metavar="OPERATION",
                                       help="DESCRIPTION")
    add_install(add_subparser(operations, "install", "install a package with dependencies"))
    add_uninstall(add_subparser(operations, "uninstall", "uninstall a package and "
                                                         "optionally its dependencies"))
    add_update(add_subparser(operations, "update", "update some or all packages"))
    add_repo_add(add_subparser(operations, "repo-add",
                               "add a new package repository with a given name and server URL(s)"))
    add_repo_remove(add_subparser(operations, "repo-remove",
                                  "remove an existing package repository with the given name"))
    add_list(add_subparser(operations, "list", "list installed packages"))
    add_list_files(add_subparser(operations, "list-files", "list files of an installed package"))
    add_search(add_subparser(operations, "search",
                             "search repository for packages with matching string"))
    add_info(add_subparser(operations, "info", "show detailed information about given package(s)"))
    add_clean(add_subparser(operations, "clean", "clean package cache and intermediate files"))
    add_mark(add_subparser(operations, "mark",
                           "mark a package as a dependency or an explicitly installed package"))
    add_repair(add_subparser(operations, "repair",
                             "try to repair state after a failed operation or an interrupt/kill"))
    return parser.parse_args(argv)


def add_subparser(operations, name: str, hlp: str) -> argparse.ArgumentParser:  # type: ignore
    subparser = cast(argparse.ArgumentParser,
                     operations.add_parser(name, help=hlp))  # type: ignore
    add_common_args(subparser)
    # by default set the flag for repository command as false
    subparser.set_defaults(is_repo_cmd=False)
    return subparser


def add_common_args(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("-d", "--docker-path", type=str,
                           help="path of docker/podman if not in /usr/bin")
    subparser.add_argument("-z", "--ybox", type=str,
                           help="the ybox container to use for package operations else the user "
                                "is prompted to select a container from among the active ones")
    subparser.add_argument("-C", "--distribution-config", type=str,
                           help="path to distribution configuration file to use instead of the "
                                "`distro.ini` from user/system configuration paths")
    subparser.add_argument("-q", "--quiet", action="count", default=0,
                           help="proceed without asking any questions using default where "
                                "possible; this should usually be used with explicit -z/--ybox "
                                "argument for the container else it is assumed that there is only "
                                "one active container which is selected else the operation fails; "
                                "specifying this flag twice will make it real quiet (e.g. install "
                                "will silently override system executables with local ones)")


def add_install(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("-o", "--skip-opt-deps", action="store_true",
                           help="skip installation of optional dependencies (or recommendations)")
    subparser.add_argument("-w", "--with-opt-deps", type=str,
                           help="provide comma-separated optional dependencies to install "
                                "(in which case user will not be prompted to select them)")
    subparser.add_argument("-f", "--app-flags", type=str,
                           help="comma separated key-value pairs for the flags to be used when "
                                "invoking the container executables (e.g. 'chromium=...,...'")
    subparser.add_argument("-l", "--add-dep-wrappers", action="store_true",
                           help="create local wrapper desktop and executables for the newly "
                                "installed package dependencies too (both required and optional)")
    subparser.add_argument("-c", "--check-package", action="store_true",
                           help="check for existing package before actual installation")
    subparser.add_argument("-s", "--skip-executables", action="store_true",
                           help="skip creating wrappers for invoking executables installed by "
                                "the package; default is to create wrapper executables in user's "
                                "$HOME/.local/bin directory and link man pages to "
                                "$HOME/.local/share/man (or using $PYTHONUSERBASE)")
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
    subparser.set_defaults(func=update_packages)


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


def add_list_files(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("package", type=str, help="list files of this package")
    subparser.set_defaults(func=list_files)


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


def add_info(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("-a", "--all", action="store_true",
                           help="search for package information in the repositories, "
                                "otherwise search only among the installed packages")
    subparser.add_argument("packages", nargs="+", help="one or more packages")
    subparser.set_defaults(func=info_packages)


def add_clean(subparser: argparse.ArgumentParser) -> None:
    subparser.set_defaults(func=clean_cache)


def add_mark(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("-e", "--explicit", action="store_true",
                           help="mark the package as explicitly installed; the package will "
                                "henceforth be managed by `ybox-pkg` if not already; "
                                "exactly one of -e or -D option must be specified")
    subparser.add_argument("-D", "--dependency-of", type=str,
                           help="mark the package as a dependency of given package; both the "
                                "packages will henceforth be managed by `ybox-pkg` if not "
                                "already; exactly one of -e or -D option must be specified")
    subparser.add_argument("package", type=str, help="the package to be marked")
    subparser.set_defaults(func=mark_package)


def add_repair(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--extensive", action="store_true",
                           help="repair thoroughly by reinstalling all packages")
    subparser.set_defaults(func=repair_package_state)


def add_repo_add(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("-k", "--key", type=str,
                           help="key to be registered for verification of the packages (usually "
                                "a GPG/PGP signing key); this can be a URL to the key file or a "
                                "key ID that can be retrieved from default key server as "
                                "configured in the distribution's configuration file or the one "
                                "mentioned by the -s/--key-server option")
    subparser.add_argument("-s", "--key-server", type=str,
                           help="URL of the key server to be used for retrieving a key by ID "
                                "which will override the default key server configured in the "
                                "distribution's configuration file")
    subparser.add_argument("-o", "--options", type=str,
                           help="additional options that may be required for the repository "
                                "specification; for example debian/ubuntu need '<distribution> "
                                "<component...>' in its source specification so that need to be "
                                "provided using '--options=stable main' (as an example)")
    subparser.add_argument("-S", "--add-source-repo", action="store_true",
                           help="for distributions like debian/ubuntu, this specifies that the "
                                "repository for package sources (deb-src) should also be added "
                                "using the same specification as the package repository")
    subparser.add_argument("name", type=str, help="name for the package repository to be added")
    subparser.add_argument("urls", nargs="+",
                           help="one or more server URLs of the package repository")
    subparser.set_defaults(is_repo_cmd=True)
    subparser.set_defaults(func=repo_add)


def add_repo_remove(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("name", type=str, help="name of the package repository to be removed")
    subparser.set_defaults(is_repo_cmd=True)
    subparser.set_defaults(func=repo_remove)
