"""
Common utility classes and methods used by the scripts.
"""

import argparse
import os
import re
import subprocess
import sys
from configparser import BasicInterpolation, ConfigParser, Interpolation
from enum import Enum
from typing import Optional, Union

from simple_term_menu import TerminalMenu  # type: ignore

from .env import Environ
from .print import fgcolor, print_color, print_error, print_warn
from .state import ZboxStateManagement


class NotSupportedError(Exception):
    """Raised when an operation or configuration is not supported or invalid."""


class ZboxLabel(str, Enum):
    """
    Labels for zbox created objects.
    """
    CONTAINER_TYPE = "io.zbox.container.type"
    CONTAINER_DISTRIBUTION = "io.zbox.container.distribution"

    # zbox container types (first two are temporary ones)
    CONTAINER_BASE = f"{CONTAINER_TYPE}=base"
    CONTAINER_COPY = f"{CONTAINER_TYPE}=copy"
    CONTAINER_PRIMARY = f"{CONTAINER_TYPE}=primary"


class PkgMgr(str, Enum):
    """
    Package manager actions that are defined for each Linux distribution in its distro.ini file.
    """
    INSTALL = "install"
    QUIET_FLAG = "quiet_flag"
    OPT_DEPS = "opt_deps"
    OPT_DEP_FLAG = "opt_dep_flag"
    UNINSTALL = "uninstall"
    PURGE_FLAG = "purge_flag"
    REMOVE_DEPS_FLAG = "remove_deps_flag"
    UPDATE_META = "update_meta"
    UPDATE = "update"
    UPDATE_ALL = "update_all"
    CLEANUP = "cleanup"
    INFO = "info"
    LIST = "list"
    LIST_ALL = "list_all"
    LIST_LONG = "list_long"
    LIST_ALL_LONG = "list_all_long"
    LIST_FILES = "list_files"


class EnvInterpolation(BasicInterpolation):
    """
    Substitute environment variables in the values using 'os.path.expandvars'.
    In addition, a special substitution of ${NOW:<fmt>} is supported to substitute the
    current time (captured by InitNow above) in the 'datetime.strftime' format.

    This class extends `BasicInterpolation` hence the `%(.)s` syntax can be used to expand other
    keys in the same section or the `DEFAULT` section in the `before_get`. If a bare '%' is
    required in the value, then it should be escaped with a '%' i.e. use '%%' for a single '%'.
    Note that the environment variable and NOW substitution is done in the `before_read` phase
    before any `BasicInterpolation` is done, so any '%' characters in those environment variable
    or ${NOW:...} expansions should not be escaped.

    If 'skip_expansion' is specified in initialization to a non-empty list, then no
    environment variable substitution is performed for those sections but the
    ${NOW:...} substitution is still performed.
    """

    __NOW_RE = re.compile(r"\${NOW:([^}]*)}")

    def __init__(self, env: Environ, skip_expansion: list[str]):
        super().__init__()
        self.__skip_expansion = skip_expansion
        # for the NOW substitution
        self.__now = env.now

    # override before_read rather than before_get because we need expanded vars when writing
    # into the state.db database too
    def before_read(self, parser, section: str, option: str, value: str):
        """Override before_read to substitute environment variables and ${NOW...} pattern.
           This method is overridden rather than before_get because expanded variables are
           also required when writing the configuration into the state.db database."""
        if not value:
            return value
        if section not in self.__skip_expansion:
            value = os.path.expandvars(value)
        # replace ${NOW:...} pattern with appropriately formatted datetime string
        return re.sub(self.__NOW_RE, lambda mt: self.__now.strftime(mt.group(1)), value)


def get_docker_command(args: argparse.Namespace, option_name: str) -> str:
    """
    If custom docker/podman defined in arguments, then return that else check for podman and
    docker (in that order) in the standard /usr/bin path.

    :param args: the parsed arguments passed to the invoking script
    :param option_name: name of the argument that holds the docker/podman path, if specified
    :return: the podman/docker executable specified in arguments or in standard /usr/bin path
    """
    # check for podman first then docker
    if args.docker_path:
        return args.docker_path
    if os.access("/usr/bin/podman", os.X_OK):
        return "/usr/bin/podman"
    if os.access("/usr/bin/docker", os.X_OK):
        return "/usr/bin/docker"
    raise FileNotFoundError("Neither /usr/bin/podman nor /usr/bin/docker found "
                            f"and no '{option_name}' option has been provided")


# read the ini file, recursing into the includes to build the final dictionary
def config_reader(conf_file: str, interpolation: Optional[Interpolation],
                  top_level: str = "") -> ConfigParser:
    """
    Read the container configuration INI file, recursing into the includes to build the final
    dictionary having the sections with corresponding key-value pairs.

    :param conf_file: the configuration file to be read
    :param interpolation: if provided then used for value interpolation
    :param top_level: the top-level configuration file; don't pass this when calling
                      externally (or set it the same as `conf_file` argument)
    :return: instance of `configparser.ConfigParser` built after parsing the given file as
             well as any includes recursively
    """
    if not os.access(conf_file, os.R_OK):
        if top_level:
            raise FileNotFoundError(f"Config file '{conf_file}' among the includes of "
                                    f"'{top_level}' does not exist or not readable")
        raise FileNotFoundError(f"Config file '{conf_file}' does not exist or not readable")
    with open(conf_file, "r", encoding="utf-8") as conf_fd:
        config = ini_file_reader(conf_fd, interpolation)
    if not top_level:
        top_level = conf_file
    if not (includes := config.get("base", "includes", fallback="")):
        return config
    for include in includes.split(","):
        if not (include := include.strip()):
            continue
        inc_file = include if os.path.isabs(
            include) else f"{os.path.dirname(conf_file)}/{include}"
        inc_conf = config_reader(inc_file, interpolation, top_level)
        for section in inc_conf.sections():
            if not config.has_section(section):
                config[section] = inc_conf[section]
            else:
                conf_section = config[section]
                inc_section = inc_conf[section]
                for key in inc_section:
                    if key not in conf_section:
                        conf_section[key] = inc_section[key]
    return config


def ini_file_reader(file, interpolation: Optional[Interpolation],
                    case_sensitive: bool = True) -> ConfigParser:
    """
    Read an INI file from a given file handle. It applies some basic rules that are used
    for all zbox configurations like allowing no values, only '=' as delimiters and
    case-sensitive keys.

    :param file: file handle for the INI format data
    :param interpolation: if provided then used for value interpolation
    :param case_sensitive: if true then keys are case-sensitive (default) else case-insensitive
    :return: instance of `configparser.ConfigParser` built after parsing the given file
    """
    config = ConfigParser(allow_no_value=True, interpolation=interpolation, delimiters="=")
    if case_sensitive:
        config.optionxform = str  # type: ignore
    config.read_file(file)
    return config


def verify_zbox_state(docker_cmd: str, box_name: str, expected_states: list[str],
                      exit_on_error: bool = True, error_msg: str = " ") -> bool:
    """
    Verify that a given zbox container exists and is in one of the given states.

    :param docker_cmd: the docker/podman executable to use
    :param box_name: name of the zbox container
    :param expected_states: list of one or more expected states like 'running', 'exited';
                            empty value means any state is permissible
    :param exit_on_error: whether to exit using `sys.exit` if verification fails
    :param error_msg: string to be inserted in the error message "No...zbox container ...",
                      so this should be a user-friendly name for the `expected_states` e.g.
                      ' active ', ' stopped '
    :return: if `exit_on_error` is False, then return the result of verification as True or False
    """
    check_result = subprocess.run(
        [docker_cmd, "inspect", "--type=container",
         '--format={{index .Config.Labels "' + ZboxLabel.CONTAINER_TYPE + '"}} {{.State.Status}}',
         box_name], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    if check_result.returncode != 0:
        if exit_on_error:
            print_error(f"No{error_msg}zbox container named '{box_name}' found")
            sys.exit(check_result.returncode)
        else:
            return False
    else:
        result = check_result.stdout.decode("utf-8").rstrip()
        primary_zbox = "primary "
        if result.startswith(primary_zbox):
            state = result[len(primary_zbox):]
            if expected_states:
                if not (exists := state in expected_states) and exit_on_error:
                    sys.exit(1)
                else:
                    return exists
            else:
                return True
    return False


def run_command(cmd: Union[str, list[str]], capture_output: bool = False,
                exit_on_error: bool = True, error_msg: Optional[str] = None) -> Union[str, int]:
    """
    Helper wrapper around `subprocess.run` to display failure message (in red foreground color)
    for the case of failure, exit on failure and capturing and returning output if required.

    :param cmd: the command to be run which can be either a list of strings, or a single string
                which will be split on whitespace
    :param capture_output: if True then capture stdout and return it but stderr is still displayed
                           on screen using `print_warn` method in purple foreground color
    :param exit_on_error: whether to exit using `sys.exit` if command fails
    :param error_msg: string to be inserted in error message "FAILURE in ..." so should be a
                      user-friendly name of the action that the command was supposed to do;
                      if not specified then the entire command string is displayed;
                      the special value 'SKIP' can be used to skip printing any error message
    :return: the captured standard output if `capture_output` is true else the return code of
             the command as a string (if `exit_on_error` is False or command was successful)
    """
    args = cmd.split() if isinstance(cmd, str) else cmd
    result = subprocess.run(args, capture_output=capture_output, check=False)
    if result.returncode != 0:
        if capture_output:
            print_subprocess_output(result)
        if not error_msg:
            error_msg = f"'{' '.join(cmd)}'"
        if error_msg != "SKIP":
            print_error(f"FAILURE in {error_msg} -- see the output above for details")
        if exit_on_error:
            sys.exit(result.returncode)
        else:
            return result.returncode
    if capture_output and result.stderr:
        print_warn(result.stderr.decode("utf-8"))
    return result.stdout.decode("utf-8") if capture_output else result.returncode


def print_subprocess_output(result: subprocess.CompletedProcess) -> None:
    """print completed subprocess output in color (orange for standard output and purple
       for standard error)"""
    print_color(result.stdout.decode("utf-8"), fg=fgcolor.orange)
    print_warn(result.stderr.decode("utf-8"))


def get_other_shared_containers(container_name: str, shared_root: str,
                                state: ZboxStateManagement) -> list[str]:
    """
    Get other containers sharing the same shared_root as the given container having a shared root.

    :param container_name: name of the container
    :param shared_root: the local shared root directory if `shared_root` flag is enabled
                        for the container
    :param state: instance of `ZboxStateManagement`
    :return: list of containers sharing the same shared root with the given container
    """
    if shared_root:
        shared_containers = state.get_containers(shared_root=shared_root)
        shared_containers.remove(container_name)
        return shared_containers
    return []


def select_item_from_menu(items: list[str]) -> Optional[str]:
    terminal_menu = TerminalMenu(items,
                                 status_bar="Press <Enter> to select, <Esc> to exit")
    selection = terminal_menu.show()
    if selection is not None:
        return items[int(selection)]
    else:
        print_warn("Aborted selection")
        return None
