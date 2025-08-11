"""
Methods for package installation on an active ybox container.
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from configparser import ConfigParser, SectionProxy
from pathlib import Path
from typing import Callable, Optional, Union

from simple_term_menu import TerminalMenu  # type: ignore

from ybox.cmd import PkgMgr, build_shell_command, run_command
from ybox.config import Consts, StaticConfiguration
from ybox.print import print_error, print_info, print_notice, print_warn
from ybox.state import (CopyType, DependencyType, RuntimeConfiguration,
                        YboxStateManagement)
from ybox.util import check_package, ini_file_reader, select_item_from_menu

# match both "Exec=" and "TryExec=" lines (don't capture trailing newline)
_EXEC_PATTERN = r"^\s*((Try)?Exec\s*=\s*)(\S+)\s*(.*?)\s*$"
# pattern to match icons with absolute paths and change them to just names
_ICON_PATH_PATTERN = r"^\s*Icon\s*=\s*(/usr/share/(icons|pixmaps)/\S+)\s*$"
# regex to match either of the two above
_EXEC_ICON_RE = re.compile(f"{_EXEC_PATTERN}|{_ICON_PATH_PATTERN}")
# match !p and !a to replace executable program (third group above) and arguments respectively
_FLAGS_RE = re.compile("![ap]")
# environment variables passed through from host environment to podman/docker executable
_PASSTHROUGH_ENVVARS = ("XAUTHORITY", "DISPLAY", "XDG_SESSION_TYPE", "FREETYPE_PROPERTIES",
                        "SSH_AUTH_SOCK", "GPG_AGENT_INFO",
                        "__NV_PRIME_RENDER_OFFLOAD", "__GLX_VENDOR_LIBRARY_NAME",
                        "__VK_LAYER_NV_optimus", "VK_ICD_FILES", "VK_ICD_FILENAMES")
# environment variables passed from host to podman/docker executable with empty if not set;
# note that these variables are assumed to have values that don't need quoting by /bin/sh
# else code will need to be updated to quote $<var> value when passing to the shell
_PASSTHRU_EMPTY_ENVVARS = ("WAYLAND_DISPLAY", "QT_QPA_PLATFORM")
# characters that need to be escaped in quoted string of Exec/TryExec line
_DESKTOP_ESCAPE_RE = re.compile(r'["`$\\]')


def install_package(args: argparse.Namespace, pkgmgr: SectionProxy, docker_cmd: str,
                    conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                    state: YboxStateManagement) -> int:
    """
    Install package specified by `args.package` on a ybox container with given podman/docker
    command. Additional flags honored are `args.quiet` to bypass user confirmation during install,
    `args.skip_opt_deps` to skip installing optional dependencies of the package,
    `args.skip_executables` to skip creating wrapper executables for the package executables,
    `args.skip_desktop_files` to skip creating wrapper desktop files for the package ones.

    When the `args.skip_opt_deps` flag is not enabled, then the package databases are searched
    for optional dependencies of the package as well as those of the new required dependencies
    being installed. Recursion level for this search is fixed to 2 for now else the number
    of packages can be overwhelming with most being largely irrelevant. A selection menu
    presented to the user allows choosing the optional dependencies to be installed after
    the main package installation has completed successfully.

    :param args: arguments having `package` and all other attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :return: integer exit status of install command where 0 represents success
    """
    quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value] if args.quiet else ""
    # restore the {opt_dep} placeholder in the installation command which will be replaced
    # before actual execution by _install_package(...)
    install_cmd = pkgmgr[PkgMgr.INSTALL.value].format(quiet=quiet_flag, opt_dep="{opt_dep}")
    list_cmd = pkgmgr[PkgMgr.LIST_FILES.value]
    selected_deps = args.with_opt_deps.split(",") if args.with_opt_deps else None
    opt_deps_cmd = pkgmgr[PkgMgr.OPT_DEPS.value]
    # TODO: use this flag for -w option only if get_optional_deps returned the package/provides;
    #       when this is done, then the opt_dep_flag in distro.ini can have proper values
    #       also allow for re-installation of packages using a flag
    opt_dep_flag = pkgmgr[PkgMgr.OPT_DEP_FLAG.value]
    check_avail = pkgmgr[PkgMgr.CHECK_AVAIL.value]
    check_inst = pkgmgr[PkgMgr.CHECK_INSTALL.value]
    return _install_package(args.package, args, install_cmd, list_cmd, docker_cmd, conf,
                            runtime_conf, state, opt_deps_cmd, opt_dep_flag, False,
                            args.check_package, check_avail, check_inst, selected_deps, args.quiet)


def _install_package(package: str, args: argparse.Namespace, install_cmd: str, list_cmd: str,
                     docker_cmd: str, conf: StaticConfiguration, rt_conf: RuntimeConfiguration,
                     state: YboxStateManagement, opt_deps_cmd: str, opt_dep_flag: str,
                     opt_dep_install: bool, check_pkg: bool, check_avail: str, check_inst: str,
                     selected_deps: Optional[list[str]], quiet: int) -> int:
    """
    Real workhorse for :func:`install_package` that is invoked recursively for
    optional dependencies if required.

    :param package: the package to be installed
    :param args: arguments having all the attributes passed by the user (`package` is ignored)
    :param install_cmd: installation command as read from `distro.ini` configuration file of the
                        distribution which should have an unresolved `{opt_dep}` placeholder
                        for the `opt_dep_flag`
    :param list_cmd: command to list files for an installed package read from `distro.ini`
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param rt_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :param opt_deps_cmd: command to determine optional dependencies as read from `distro.ini`
    :param opt_dep_flag: flag to be added during installation of an optional dependency to mark
                         it as a dependency (as read from `distro.ini`)
    :param opt_dep_install: `True` if installation is for an optional dependency
    :param check_pkg: if True then skip installation if package already exists
    :param check_avail: command to check if package is available in the package repositories
    :param check_inst: command to check if package is installed
    :param selected_deps: list of dependencies to install if user has already provided them
    :param quiet: perform operations quietly
    :return: exit code of install command for the main package
    """
    # need to determine optional dependencies before installation else second level or higher
    # dependencies will never be found (as the dependencies are already installed)
    optional_deps: list[tuple[str, str, int]] = []
    installed_optional_deps: set[str] = set()
    if opt_dep_install:
        resolved_install_cmd = install_cmd.format(opt_dep=opt_dep_flag)
    else:
        resolved_install_cmd = install_cmd.format(opt_dep="")
    # don't exit on error here because the caller may have further actions to perform before exit
    code = -1
    if check_pkg:
        code, inst_pkgs = check_package(docker_cmd, check_inst, package, conf.box_name)
        if code == 0:
            if not quiet:
                suffix = "" if len(inst_pkgs) == 1 and package == inst_pkgs[0] \
                    else f" (as {inst_pkgs})"
                print_notice(f"'{package}'{suffix} is already installed in '{conf.box_name}'")
            package = inst_pkgs[0]
    if code != 0:
        if check_avail:
            _, avail_pkgs = check_package(docker_cmd, check_avail, package, conf.box_name)
            if len(avail_pkgs) > 1:
                print_notice(f"Multiple packages found for '{package}', select one to install")
                if selected_pkg := select_item_from_menu(avail_pkgs):
                    package = selected_pkg
                else:
                    return 1
        if not quiet:
            print_info(f"Installing '{package}' in '{conf.box_name}'")
        code = int(run_command(build_shell_command(
            docker_cmd, conf.box_name, f"{resolved_install_cmd} {package}"), exit_on_error=False,
            error_msg=f"installing '{package}'"))
        # actual installed package name can be different due to package being virtual and/or
        # having multiple choices
        if code == 0:
            code, inst_pkgs = check_package(docker_cmd, check_inst, package, conf.box_name)
            if code == 0:
                package = inst_pkgs[0]  # pick first since it is sorted by latest installation time
            else:
                print_error(f"Package '{package}' was not installed successfully")
                return 1
    if code == 0:
        skip_desktop_files = args.skip_desktop_files
        skip_executables = args.skip_executables
        copy_type = CopyType(0)
        # check if wrappers for optional dependencies have to be created
        if not opt_dep_install or args.add_dep_wrappers:
            if not skip_desktop_files:
                copy_type |= CopyType.DESKTOP
            if not skip_executables:
                resp = input("Create wrapper(s) for application executable(s) of package "
                             f"'{package}'? (Y/n) ") if quiet == 0 else "Y"
                if resp.strip().lower() != "n":
                    copy_type |= CopyType.EXECUTABLE
        # TODO: wrappers for newly installed required dependencies should also be created;
        #       handle DependencyType.SUGGESTION if supported by underlying package manager
        app_flags: dict[str, str] = {}
        if args.app_flags:
            for flag in args.app_flags.split(","):
                if (split_idx := flag.find("=")) != -1:
                    app_flags[flag[:split_idx]] = flag[split_idx + 1:]
        local_copies = wrap_container_files(package, copy_type, app_flags, list_cmd,
                                            docker_cmd, conf, rt_conf.ini_config,
                                            rt_conf.shared_root, quiet)
        dep_type, dep_of = (DependencyType.OPTIONAL, args.package) if opt_dep_install else (
            None, "")
        state.register_package(conf.box_name, package, local_copies, copy_type, app_flags,
                               rt_conf.shared_root, dep_type, dep_of)
        # get optional deps even if args.skip_opt_deps is true to obtain installed_optional_deps
        # which need to be registered against this package too (state.register_dependency below)
        if not opt_dep_install:
            optional_deps, installed_optional_deps = get_optional_deps(package, docker_cmd,
                                                                       conf.box_name, opt_deps_cmd)
        # register the recorded optional dependencies for this package too
        if recorded_deps := state.check_packages(conf.box_name, installed_optional_deps):
            for dep in recorded_deps:
                state.register_dependency(conf.box_name, package, dep, DependencyType.OPTIONAL)
        if optional_deps and selected_deps is None and not args.skip_opt_deps:
            selected_deps = select_optional_deps(package, optional_deps)
        if selected_deps:
            for dep in selected_deps:
                _install_package(dep, args, install_cmd, list_cmd, docker_cmd, conf, rt_conf,
                                 state, "", opt_dep_flag, True, check_pkg, check_avail,
                                 check_inst, None, quiet)

    return code


def get_optional_deps(package: str, docker_cmd: str, container_name: str,
                      opt_deps_cmd: str) -> tuple[list[tuple[str, str, int]], set[str]]:
    """
    Find the optional dependencies recursively, removing the ones already installed.

    :param package: package to be installed
    :param docker_cmd: the podman/docker executable to use
    :param container_name: name of the ybox container
    :param opt_deps_cmd: command to determine optional dependencies as read from `distro.ini`
    :return: first part is list of tuples having the name of optional dependency, its description
             and an integer `level` denoting its depth in the dependency tree
             (i.e. level 1 means immediate dependency of the package, 2 means dependency of
              another dependency which is being newly installed and so on);
              second part of the tuple is the set of optional dependencies of the package that
              are already installed and registered as dependency in state.db for some other package
    """
    optional_deps: list[tuple[str, str, int]] = []
    installed_optional_deps: set[str] = set()
    pkg_start = "Found optional dependencies"
    pkg_prefix = "PKG:"
    pkg_sep = Consts.default_field_separator()
    # fill in the expected separator, prefix and header line
    opt_deps_cmd = opt_deps_cmd.format(separator=pkg_sep, prefix=pkg_prefix, header=pkg_start)
    # Expected format of output below is -- PKG:<name>::::<level>::::<installed>::::<description>
    # This is preceded by a line "Found optional dependencies".
    # Print other lines on output as is which are for informational purpose.
    # Code below does progressive display of output which is required for showing stuff like
    # download progress properly.
    # The following alternatives were considered:
    #  1) print PKG: lines to stderr: this works only if "-t" is removed from docker exec
    #          otherwise both stdout and stderr are combined to tty, but if it is removed
    #          then you can no longer see the progressive download due to buffering
    #  2) redirect PKG: lines somewhere else like a common file: this can be done but will
    #          likely be more messy than the code below (e.g. handle concurrent executions),
    #          but still can be considered in future
    # (reduced bufsize to show download progress better)
    with subprocess.Popen(build_shell_command(
            docker_cmd, container_name, f"{opt_deps_cmd} {package}"),
            bufsize=256, stdout=subprocess.PIPE) as deps_result:
        line = bytearray()
        # possible end of lines
        eol1 = ord(b"\r")
        eol2 = ord(b"\n")
        buffered = 0
        assert deps_result.stdout is not None
        # readline does not work for in-place updates like from aria2
        while char := deps_result.stdout.read(1):
            sys.stdout.buffer.write(char)
            buffered += 1
            if char[0] == eol1 or char[0] == eol2:
                sys.stdout.flush()
                buffered = 0
                output = line.decode("utf-8")
                line.clear()
                if output == pkg_start:
                    break
            else:
                line.append(char[0])
                if buffered >= 8:  # flush frequently to show download progress, for example
                    sys.stdout.flush()
                    buffered = 0
        sys.stdout.flush()
        while pkg_out := deps_result.stdout.readline():
            output = pkg_out.decode("utf-8")
            # there can be a trailing '\n' from the loop before due to '\r\n' ending
            if output == "\n":
                continue
            name, level, installed, desc = output[len(pkg_prefix):].split(pkg_sep, maxsplit=3)
            desc = desc.rstrip()
            if installed.strip().lower() == "true":
                installed_optional_deps.add(name)
            else:
                optional_deps.append((name, desc, int(level)))

        if deps_result.wait(60) != 0:
            print_warn(f"FAILED to determine optional dependencies of {package} -- "
                       "see the output above for details. Skipping optional dependencies.")
            return [], installed_optional_deps

    return optional_deps, installed_optional_deps


def select_optional_deps(package: str, deps: list[tuple[str, str, int]]) -> list[str]:
    """
    Show a selection menu to the user having optional dependencies of a package to be installed.

    :param package: package that is being installed
    :param deps: list of dependencies as tuples from :func:`get_optional_deps`
    :return: list of names of the selected optional dependencies (or empty list for no selection)
    """
    menu_options = [f"{'*' if level <= 1 else ''} {name} ({desc})" for name, desc, level in deps]
    print_info(f"Select optional dependencies of {package} "
               "(starred ones are the immediate dependencies):")
    # don't select on <Enter> (multi_select_select_on_accept) and allow for empty selection
    terminal_menu = TerminalMenu(menu_options, multi_select=True, show_multi_select_hint=True,
                                 multi_select_select_on_accept=False, multi_select_empty_ok=True)
    selection = terminal_menu.show()
    return [deps[index][0] for index in selection] if isinstance(selection, tuple) else []


def wrap_container_files(package: str, copy_type: CopyType, app_flags: dict[str, str],
                         list_cmd: str, docker_cmd: str, conf: StaticConfiguration,
                         box_conf: Union[str, ConfigParser], shared_root: str,
                         quiet: int) -> list[str]:
    """
    Create wrappers in host environment to invoke container's desktop files and executables.

    :param package: the package to be installed
    :param copy_type: the `CopyType` to tell whether to create wrapper .desktop files and/or
                      wrapper executables that invoke corresponding ones of the container
    :param app_flags: application flags that have been explicitly specified with --app-flags
    :param list_cmd: command to list files for an installed package read from `distro.ini`
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param box_conf: the resolved INI format configuration of the container as a string or
                     a `ConfigParser` object
    :param shared_root: the local shared root directory if `shared_root` is provided
                        for the container
    :param quiet: perform operations quietly
    :return: the list of paths of the wrapper files
    """
    if not copy_type:
        return []
    # skip on errors below and do not fail the installation
    package_files = run_command(build_shell_command(
        docker_cmd, conf.box_name, list_cmd.format(package=package), enable_pty=False),
        capture_output=True, exit_on_error=False, error_msg=f"listing files of '{package}'")
    if isinstance(package_files, int):
        return []
    wrapper_files: list[str] = []
    desktop_dirs = Consts.container_desktop_dirs()
    icon_dir_pattern = re.compile(f"({')|('.join(Consts.container_icon_dirs())})")
    # map of found icons where key is the name of icon file (without extension) while the value
    # is a tuple with first one being a float inverse priority (lower is better) followed by path
    selected_icons: dict[str, tuple[float, str]] = {}
    executable_dirs = Consts.container_bin_dirs()
    man_dir_pattern = Consts.container_man_dir_pattern()
    # get the parsed container configuration
    parsed_box_conf = _get_parsed_box_conf(box_conf)
    # read the container configuration for [app_flags] section
    app_flags_section = parsed_box_conf["app_flags"] \
        if parsed_box_conf and parsed_box_conf.has_section("app_flags") else None
    file_paths = [(os.path.dirname(file), filename, file) for file in package_files.splitlines()
                  if (filename := os.path.basename(file).strip())]  # empty name means directory

    # if an executable from a package is skipped by user, then skip all of them for consistency
    for file_dir, filename, file in file_paths:
        if file_dir in executable_dirs:
            # check for additional flags for the executables as specified in [app_flags] section
            if app_flags_section and (flags := app_flags_section.get(filename)):
                # command-line --app-flags will override those in the configuration files
                app_flags.setdefault(filename, flags)
            if copy_type & CopyType.EXECUTABLE:
                if not _can_wrap_executable(filename, file, conf, quiet):
                    # clear EXECUTABLE mask so that no wrapper executable is created
                    copy_type &= ~CopyType.EXECUTABLE

    # the "-i" flag is used in the wrapper executable for podman/docker exec which is safe;
    # if the app needs stdin then Terminal must be true in its desktop file in which case
    # a terminal will be opened during execution
    for file_dir, filename, file in file_paths:
        # check if this is a .desktop directory and copy it over adding appropriate
        # "docker exec" prefix to the command
        if copy_type & CopyType.DESKTOP:
            if file_dir in desktop_dirs:
                _wrap_desktop_file(filename, file, docker_cmd, conf, app_flags, wrapper_files)
                continue  # if it is a .desktop file, then skip executable check
            if _select_app_icon(file_dir, filename, file, icon_dir_pattern, selected_icons):
                continue  # if it is an icon file, then skip executable check
        if copy_type & CopyType.EXECUTABLE:
            if file_dir in executable_dirs:
                _wrap_executable(filename, file, docker_cmd, conf, app_flags, wrapper_files)
            elif shared_root and man_dir_pattern.match(file_dir):
                _link_man_page(file, shared_root, conf, wrapper_files)
    if selected_icons:
        _copy_app_icons(selected_icons, docker_cmd, conf, quiet, wrapper_files)

    return wrapper_files


def _get_parsed_box_conf(box_conf: Union[str, ConfigParser]) -> Optional[ConfigParser]:
    """
    Get the parsed `ConfigParser` for the container configuration.

    :param box_conf: the resolved INI format configuration of the container as a string or
                     a `ConfigParser` object
    :return: the `ConfigParser` object for the container configuration
    """
    if isinstance(box_conf, ConfigParser):
        return box_conf
    if not box_conf:
        return None
    with io.StringIO(box_conf) as box_conf_fd:
        return ini_file_reader(box_conf_fd, interpolation=None, case_sensitive=False)


def _replace_flags(match: re.Match[str], flags: str, program: str, args: str) -> str:
    """
    `_FLAGS_RE.sub` callback to replace `!p` in a value of `[app_flags]` section with given
    `program` and `!a` with `args` while honoring `!!` escape for literal `!`.

    :param match: an `re.Match` for `_FLAGS_RE` pattern defined in this module
    :param flags: the value in `[app_flags]` section for `program` name as the key
    :param program: the executable which can be its full path or the name
    :param args: arguments to be passed to the `program`
    :return: the substitution string for `_FLAGS_RE.sub` call
    """
    # check for !![ap]
    if (start := match.start()) > 0 and flags[start - 1] == "!":
        return match.group()[1]
    if match.group()[1] == "p":
        return program
    return args


def docker_cp_action(docker_cmd: str, box_name: str, src: str,
                     func: Callable[[str], None]) -> int:
    """
    Copy a file from docker container to a temporary location on host and perform given action.
    This does not use the `cp` command of podman/docker because it fails for rootless docker.

    :param docker_cmd: the podman/docker executable to use
    :param box_name: name of the ybox container
    :param src: path of the file to be copied on the container
    :param func: function that takes temporary copied file as an argument with no return
    :return: exit code of the podman/docker command
    """
    src_dir = os.path.dirname(src)
    src_file = os.path.basename(src)
    with tempfile.TemporaryDirectory() as temp_dir:
        # use shell pipe and tar instead of python Popen and tarfile which will require much more
        # code unncessarily and may not be able to use `run_command`
        shell_cmd = (f"'{docker_cmd}' exec '{box_name}' tar -C '{src_dir}' -chpf - '{src_file}' | "
                     f"tar -C '{temp_dir}' -xpf -")
        if (code := int(run_command(["/bin/sh", "-c", shell_cmd], exit_on_error=False,
                                    error_msg=f"copying of file from '{box_name}:{src}'"))) == 0:
            func(f"{temp_dir}/{src_file}")
        return code


def _wrap_desktop_file(filename: str, file: str, docker_cmd: str, conf: StaticConfiguration,
                       app_flags: dict[str, str], wrapper_files: list[str]) -> None:
    """
    For a desktop file, add "podman/docker exec ..." to its `Exec` lines. Also read the additional
    flags for the command passed in `app_flags` and add them to an appropriate position in the
    `Exec` lines. Also removes the `TryExec` lines that do not work in some desktop environments.

    :param filename: name of the desktop file being wrapped
    :param file: full path of the desktop file being wrapped
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param app_flags: map of executable file name to the value from [app_flags] section from the
                      container configuration
    :param wrapper_files: the accumulated list of all wrapper files so far
    """

    def replace_exec_icon(match: re.Match[str]) -> str:
        """replace Exec, TryExec and Icon lines appropriately for the host system"""
        if not (exec_word := match.group(1)):  # check for the case of `Icon=/usr/...`
            return f"Icon={os.path.basename(match.group(5))}\n"
        # remove TryExec lines that don't work in some desktop environments (like KDE plasma 5)
        if match.group(2):
            return ""
        program = match.group(3)
        args = match.group(4)
        # check for additional flags to be added
        if flags := app_flags.get(os.path.basename(program), ""):
            full_cmd = _FLAGS_RE.sub(
                lambda f_match: _replace_flags(f_match, flags, program, args), flags)
        elif args:
            full_cmd = f"{program} {args}"
        else:
            full_cmd = program
        # pseudo-tty cannot be allocated with rootless docker outside of a terminal app
        ev1 = " -e=".join(_PASSTHROUGH_ENVVARS)
        ev2 = " -e=".join((f"{k}=\\\\${k}" for k in _PASSTHRU_EMPTY_ENVVARS))
        full_cmd = _DESKTOP_ESCAPE_RE.sub(r'\\\g<0>', full_cmd)
        # TODO: SW: add "-i" flag if Terminal is true
        return (f'{exec_word}/bin/sh -c "{docker_cmd} exec -e={ev1} -e={ev2} {conf.box_name} '
                f'/usr/local/bin/run-in-dir \\\\"\\\\" {full_cmd}"\n')

    # the destination will be $HOME/.local/share/applications
    os.makedirs(conf.env.user_applications_dir, mode=Consts.default_directory_mode(),
                exist_ok=True)
    wrapper_file = f"{conf.env.user_applications_dir}/{filename}"
    if os.path.exists(wrapper_file):
        # container name is added to desktop file to make it unique
        wrapper_file = f"{conf.env.user_applications_dir}/ybox.{conf.box_name}.{filename}"
    print_notice(f"Linking container desktop file {file} to {wrapper_file}")

    def write_desktop_file(src: str) -> None:
        with open(wrapper_file, "w", encoding="utf-8") as wrapper_fd:
            with open(src, "r", encoding="utf-8") as src_fd:
                wrapper_fd.writelines(_EXEC_ICON_RE.sub(replace_exec_icon, line) for line in src_fd)
    if docker_cp_action(docker_cmd, conf.box_name, file, write_desktop_file) == 0:
        wrapper_files.append(wrapper_file)


def _select_app_icon(file_dir: str, filename: str, file: str, icon_dir_pattern: re.Pattern[str],
                     selected_icons: dict[str, tuple[float, str]]) -> bool:
    """
    Check if given file is an application icon file and fill in the given dict of `selected_icons`
    if there is no icon selected with the same name so far or it is higher priority than the
    existing one in `selected_icons`.

    :param file_dir: the directory of the application icon file
    :param filename: name of the application icon file
    :param file: full path of the application icon file
    :param icon_dir_pattern: a regular expression of the form `(<dir1>|<dir2>|...)` capturing all
                             the standard icon directories and also separately capture icon size
                             for directory of the form `/path/64x64/...` (i.e. capture `64`)
    :param selected_icons: dictionary of icon names (i.e. file name without extension) to a tuple
                           having inverse priority as a float and full path of the icon file
    :return: `True` if `file_dir` was one of the app icon directories else `False`
    """
    if icon_match := icon_dir_pattern.fullmatch(file_dir):
        # find index of the first pattern that matched
        match_groups = icon_match.groups()
        dir_idx = next(idx for idx, d in enumerate(match_groups) if d)
        # deal with 16x16 kind of directories; max dimension expected is 512
        if len(match_groups) >= dir_idx + 2 and (icon_dim_str := icon_match.group(
                dir_idx + 2)) and (icon_dim := float(icon_dim_str)) < 1024:
            # larger `icon_dim` should give smaller `inv_priority`, hence (1.0 - ...)
            inv_priority = dir_idx + 1.0 - icon_dim / 1024.0
        else:
            inv_priority = float(dir_idx)
        icon_name = Path(filename).stem  # name is without extension
        if not (existing := selected_icons.get(icon_name)) or inv_priority < existing[0]:
            selected_icons[icon_name] = (inv_priority, file)
        return True
    return False


def _copy_app_icons(selected_icons: dict[str, tuple[float, str]], docker_cmd: str,
                    conf: StaticConfiguration, quiet: int, wrapper_files: list[str]) -> None:
    """
    Copy application icons (as accumulated in `selected_icons`) from the container to user's
    standard application icon directory. It will also ask for confirmation (if `-q/--quiet` flag
      was not pass) if an icon with same name already exists in user's directory.

    :param selected_icons: dictionary of icon names (i.e. file name without extension) to a tuple
                           having inverse priority as a float and full path of the icon file
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param quiet: perform operations quietly: a value != 0 will skip overwriting existing icon
                  file in user's application icon directory without confirmation
    :param wrapper_files: the accumulated list of all wrapper files so far
    """
    target_icon_dir = Path(conf.env.user_base, "share", "icons")
    os.makedirs(target_icon_dir, mode=Consts.default_directory_mode(), exist_ok=True)
    for icon_name, (_, icon_path) in selected_icons.items():
        if existing_icons := [str(p) for p in target_icon_dir.glob(f"{icon_name}.*")]:
            resp = input(f"Application icon(s) [{' '.join(existing_icons)}] already present. "
                         "Override? (y/N) ") if quiet == 0 else "N"
            if resp.strip().lower() != "y":
                print_warn(f"Skipping copying of application icon {icon_path}")
                continue
        target_icon_path = target_icon_dir.joinpath(os.path.basename(icon_path))
        print_notice(f"Copying application icon file {icon_path} to {target_icon_path}")
        # copy from temporary file over the existing one, if any, to overwrite rather than move
        # (which will preserve all of its hard links, for example)
        exists = os.path.exists(target_icon_path)
        if docker_cp_action(docker_cmd, conf.box_name, icon_path, lambda src, dest=target_icon_path:
                            None if shutil.copy2(src, dest) else None) == 0:  # "if" for pyright
            # skip registration of icon file it already existed and was overwritten so that
            # it is not removed on package uninstall
            if not exists:
                wrapper_files.append(str(target_icon_path))


def _can_wrap_executable(filename: str, file: str, conf: StaticConfiguration, quiet: int) -> bool:
    """
    For an executable, check if a wrapper executable that invokes "podman/docker exec" should
    be created (with user confirmation or allow without confirmation if `quiet` is non-zero).

    :param filename: name of the executable file being wrapped
    :param file: full path of the executable file being wrapped
    :param conf: the :class:`StaticConfiguration` for the container
    :param quiet: perform operations quietly: a value of 1 will skip overwriting existing wrapper
                  file without confirmation while a value of 2 will also skip overriding
                  system executable, if present, without confirmation
    :return: `True` if the wrapper executable file name if allowed else `False`
    """
    wrapper_exec = _get_wrapper_executable(filename, conf)
    if os.path.exists(wrapper_exec):
        resp = input(
            f"Target file {wrapper_exec} already exists. Overwrite? (y/N) ") if quiet == 0 else "N"
        if resp.strip().lower() != "y":
            print_warn(f"Skipping local wrapper for {file}")
            return False
    # also check if creating user executable will override system executable
    for bin_dir in Consts.sys_bin_dirs():
        sys_exec = f"{bin_dir}/{filename}"
        if os.access(sys_exec, os.X_OK):
            resp = input(f"Target file {wrapper_exec} will override system installed "
                         f"{sys_exec}. Continue? (y/N) ") if quiet < 2 else "N"
            if resp.strip().lower() != "y":
                print_warn(f"Skipping local wrapper for {file}")
                return False
            break
    return True


def _wrap_executable(filename: str, file: str, docker_cmd: str, conf: StaticConfiguration,
                     app_flags: dict[str, str], wrapper_files: list[str]) -> None:
    """
    For an executable, create a wrapper executable that invokes "podman/docker exec".

    :param filename: name of the executable file being wrapped
    :param file: full path of the executable file being wrapped
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param app_flags: map of executable file name to the value from [app_flags] section from the
                      container configuration
    :param wrapper_files: the accumulated list of all wrapper files so far
    """
    os.makedirs(conf.env.user_executables_dir, mode=Consts.default_directory_mode(),
                exist_ok=True)
    wrapper_exec = _get_wrapper_executable(filename, conf)
    print_notice(f"Linking container executable {file} to {wrapper_exec}")
    # ensure to change working directory to same on as on host if possible using `run-in-dir`
    # check for additional flags to be added
    if flags := app_flags.get(filename, ""):
        full_cmd = '/usr/local/bin/run-in-dir "`pwd`" ' + _FLAGS_RE.sub(
            lambda f_match: _replace_flags(f_match, flags, f'"{file}"', '"$@"'), flags)
    else:
        full_cmd = f'/usr/local/bin/run-in-dir "`pwd`" "{file}" "$@"'
    ev1 = " -e=".join(_PASSTHROUGH_ENVVARS)
    ev2 = " -e=".join((f"{k}=${k}" for k in _PASSTHRU_EMPTY_ENVVARS))
    # TODO: some apps like those asking for password from terminal (e.g. ssh/ykman) also
    # need pseudo-terminal i.e. "-t", so allow for an cmdline option to add "-t" here
    exec_content = ("#!/bin/sh\n",
                    f"exec {docker_cmd} exec -i -e={ev1} -e={ev2} {conf.box_name} ", full_cmd)
    with open(wrapper_exec, "w", encoding="utf-8") as wrapper_fd:
        wrapper_fd.writelines(exec_content)
    os.chmod(wrapper_exec, mode=0o755, follow_symlinks=True)
    wrapper_files.append(wrapper_exec)


def _get_wrapper_executable(filename: str, conf: StaticConfiguration) -> str:
    """get the file path for local wrapper executable"""
    return f"{conf.env.user_executables_dir}/{filename}"


def _link_man_page(file: str, shared_root: str, conf: StaticConfiguration,
                   wrapper_files: list[str]) -> None:
    """
    For an executable, create a wrapper executable that invokes "podman/docker exec".

    :param file: full path of the executable file being wrapped
    :param shared_root: the local shared root directory if `shared_root` is provided
                        for the container
    :param conf: the :class:`StaticConfiguration` for the container
    :param wrapper_files: the accumulated list of all wrapper files so far
    """
    man_dir_base = file.index("/man/")  # expect /man/ to exist in the file path
    linked_man_page = Path(conf.env.user_base, "share", "man", file[man_dir_base + 5:])
    print_notice(f"Linking man page {file} to {linked_man_page}")
    linked_man_page.parent.mkdir(parents=True, exist_ok=True)
    linked_man_page.unlink(missing_ok=True)
    linked_man_page.symlink_to(f"{shared_root}{file}")
    wrapper_files.append(str(linked_man_page))
