"""
Methods for package installation on a running zbox container.
"""

import argparse
import subprocess
import sys
from configparser import SectionProxy
from typing import Tuple

from simple_term_menu import TerminalMenu  # type: ignore

from zbox.state import ZboxStateManagement
from zbox.util import PkgMgr, print_info, print_warn, run_command


def install_package(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                    container_name: str, state: ZboxStateManagement) -> int:
    """
    Install package specified by `args.package` on a zbox container with given docker/podman
    command. Additional flags honored are `args.quiet` to bypass user confirmation during install
    and `args.opt_deps` to also allow installing optional dependencies of the package.

    When the `args.opt_deps` flag is enabled, then the package databases are searched for
    optional dependencies of the package as well as those of the new required dependencies
    being installed. Recursion level for this search is fixed to 2 for now else the number
    of packages can be overwhelming with most being largely irrelevant. A selection menu
    presented to the user allows choosing the optional dependencies to be installed after
    the main package installation has completed successfully.

    :param args: arguments having `package`, `quiet` and `opt_deps` attributes
    :param pkgmgr: the `pkgmgr` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the docker/podman executable to use
    :param container_name: name of the zbox container
    :param state: instance of the `ZboxStateManagement` class having the state of all zboxes

    :return: integer exit status of install command where 0 represents success
    """
    package = args.package
    quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value] if args.quiet else ""
    # restore the {opt_dep} placeholder in the installation command which will be replaced
    # before actual execution by _install_package(...)
    install_cmd = pkgmgr[PkgMgr.INSTALL.value].format(quiet=quiet_flag, opt_dep="{opt_dep}")
    opt_deps_cmd, opt_dep_flag = (pkgmgr[PkgMgr.OPT_DEPS.value], pkgmgr[
        PkgMgr.OPT_DEP_FLAG.value]) if args.opt_deps else ("", "")
    (code, opt_deps) = _install_package(package, install_cmd, docker_cmd, container_name,
                                        opt_deps_cmd, opt_dep_flag)
    if code == 0:
        state.register_packages(container_name, packages=[package])
        if opt_deps:
            state.register_packages(container_name, packages=opt_deps,
                                    package_flags=state.optional_package_flag(package))

    return code


def _install_package(package: str, install_cmd: str, docker_cmd: str, container_name: str,
                     opt_deps_cmd: str, opt_dep_flag: str) -> Tuple[int, list[str]]:
    """
    Real workhorse for :func:`install_package` that is invoked recursively for
    optional dependencies if required.

    :param package: package to be installed
    :param install_cmd: installation command as read from `distro.ini` configuration file of the
                        distribution which should have an unresolved `{opt_dep}` placeholder
                        for the `opt_dep_flag`
    :param docker_cmd: the docker/podman executable to use
    :param container_name: name of the zbox container
    :param opt_deps_cmd: command to determine optional dependencies as read from `distro.ini`
    :param opt_dep_flag: flag to be added during installation of an optional dependency to mark
                         it as a dependency (as read from `distro.ini`)

    :return: pair having exit code of install command and list of optional dependencies
             selected by the user (if any)
    """
    print_info(f"Installing '{package}' in '{container_name}'")
    # need to determine optional dependencies before installation else second level or higher
    # dependencies will never be found (as the dependencies are already installed)
    optional_deps: list[Tuple[str, str, int]] = []
    selected_deps: list[str] = []
    if opt_deps_cmd:
        optional_deps = get_optional_deps(package, docker_cmd, container_name, opt_deps_cmd)
    if opt_dep_flag and not opt_deps_cmd:  # the case when installing dependency
        resolved_install_cmd = install_cmd.format(opt_dep=opt_dep_flag)
    else:
        resolved_install_cmd = install_cmd.format(opt_dep="")
    # don't exit on error here because the caller may have further actions to perform before exit
    code = int(run_command([docker_cmd, "exec", "-it", container_name, "/bin/bash", "-c",
                            f"{resolved_install_cmd} {package}"], exit_on_error=False,
                           error_msg=f"installing '{package}'"))
    if code == 0 and optional_deps:
        selected_deps = select_optional_deps(package, optional_deps)
        for dep in selected_deps:
            _install_package(dep, install_cmd, docker_cmd, container_name,
                             opt_deps_cmd="", opt_dep_flag=opt_dep_flag)

    return code, selected_deps


def get_optional_deps(package: str, docker_cmd: str, container_name: str,
                      opt_deps_cmd: str) -> list[tuple[str, str, int]]:
    """
    Find the optional dependencies recursively, removing the ones already installed.

    :param package: package to be installed
    :param docker_cmd: the docker/podman executable to use
    :param container_name: name of the zbox container
    :param opt_deps_cmd: command to determine optional dependencies as read from `distro.ini`

    :return: list of tuples having the name of optional dependency, its description and
             an integer `level` denoting its depth in the dependency tree
             (i.e. level 1 means immediate dependency of the package, 2 means dependency of
              another dependency which is being newly installed and so on)
    """
    optional_deps: list[Tuple[str, str, int]] = []
    pkg_start = "Found optional dependencies"
    pkg_prefix = "PKG: "
    # Expected format of output below is -- PKG: <name>::::<description>::::<level>.
    # This is preceded by a line "Found optional dependencies".
    # Print other lines on output as is which are for informational purpose.
    # Code below does progressive display of output which is required for showing stuff like
    # download progress properly.
    with subprocess.Popen([docker_cmd, "exec", "-it", container_name, "/bin/bash", "-c",
                           f"{opt_deps_cmd} {package}"], stdout=subprocess.PIPE) as deps_result:
        line = bytearray()
        eol = b"\n"[0]  # end of line
        buffered = 0
        # readline does not work for in-place updates like from aria2
        for char in iter(lambda: deps_result.stdout.read(1), b""):  # type: ignore
            # for output in deps_result.stdout:
            sys.stdout.buffer.write(char)
            buffered += 1
            if char[0] == eol:
                sys.stdout.flush()
                buffered = 0
                output = line.decode("utf-8")
                line.clear()
                if output.startswith(pkg_start):  # output can have a trailing '\r'
                    break
            else:
                line.append(char[0])
                if buffered >= 4:  # flush frequently to show download progress, for example
                    sys.stdout.flush()
                    buffered = 0
        sys.stdout.flush()
        for pkg_out in iter(deps_result.stdout.readline, b""):  # type: ignore
            output = pkg_out.decode("utf-8")
            name, desc, level = output[len(pkg_prefix):].split("::::")
            optional_deps.append((name, desc, int(level.strip())))

        if deps_result.wait(60) != 0:
            print_warn(f"FAILED to determine optional dependencies of {package} -- "
                       "see above output for details. Skipping optional dependencies.")
            optional_deps = []

    return optional_deps


def select_optional_deps(package: str, deps: list[Tuple[str, str, int]]) -> list[str]:
    """
    Show a selection menu to the user having optional dependencies of a package to be installed.

    :param package: package that is being installed
    :param deps: list of dependencies as tuples from :func:`get_optional_deps`

    :return: list of names of the selected optional dependencies (or empty list for no selection)
    """
    menu_options = [f"{'*' if level <= 1 else ''} {name} ({desc})" for name, desc, level in deps]
    print_info(f"Select optional dependencies of {package} "
               "(starred ones are the immediate dependencies):")
    terminal_menu = TerminalMenu(menu_options, multi_select=True, show_multi_select_hint=True,
                                 multi_select_select_on_accept=False, multi_select_empty_ok=True)
    selection = terminal_menu.show()
    return [deps[index][0] for index in selection] if selection else []
