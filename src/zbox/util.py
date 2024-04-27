"""
Common utility classes and methods used by the scripts.
"""

import argparse
import os
import re
import subprocess
import sys
from collections import namedtuple
from configparser import ConfigParser, Interpolation
from enum import Enum
from typing import Annotated, Optional, Union

from .env import Environ


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
    LIST_FILES = "list_files"


class EnvInterpolation(Interpolation):
    """
    Substitute environment variables in the values using 'os.path.expandvars'.
    In addition, a special substitution of ${NOW:<fmt>} is supported to substitute the
    current time (captured by InitNow above) in the 'datetime.strftime' format.

    If 'skip_expansion' is specified in initialization to a non-empty list, then no
    environment variable substitution is performed for those sections but the
    ${NOW:...} substitution is still performed.
    """

    __NOW_RE = re.compile(r"\${NOW:([^}]*)}")

    def __init__(self, env: Environ, skip_expansion: list[str]):
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
        print_error(f"No{error_msg}zbox container named '{box_name}' found")
        if exit_on_error:
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


# define color names for printing in terminal
TermColors = namedtuple("TermColors",
                        "black red green orange blue purple cyan lightgray reset bold disable")

fgcolor: Annotated[TermColors, "foreground colors in terminal"] = TermColors(
    "\033[30m", "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m",
    "\033[37m", "\033[00m", "\033[01m", "\033[02m")
bgcolor: Annotated[TermColors, "background colors in terminal"] = TermColors(
    "\033[40m", "\033[41m", "\033[42m", "\033[43m", "\033[44m", "\033[45m", "\033[46m",
    "\033[47m", "\033[00m", "\033[01m", "\033[02m")


def print_color(msg: str, fg: Optional[str] = None,
                bg: Optional[str] = None, end: str = "\n") -> None:
    # pylint: disable=invalid-name
    """
    Display given string to standard output with foreground and background colors, if provided.
    The colors will show up as expected on most known Linux terminals and console though
    some colors may look different on different terminal implementation
    (e.g. orange could be more like yellow).

    :param msg: the string to be displayed
    :param fg: the foreground color of the string
    :param bg: the background color of the string
    :param end: the terminating string which is newline by default (or can be empty for example)
    """
    if fg:
        if bg:
            full_msg = f"{fg}{bg}{msg}{bgcolor.reset}{fgcolor.reset}"
        else:
            full_msg = f"{fg}{msg}{fgcolor.reset}"
    elif bg:
        full_msg = f"{bg}{msg}{bgcolor.reset}"
    else:
        full_msg = msg
    # force flush the output if it doesn't end in a newline
    print(full_msg, end=end, flush=(end != "\n"))


def print_error(msg: str, end: str = "\n") -> None:
    """
    Display an error string in red foreground (and no background change).

    :param msg: the string to be displayed
    :param end: the terminating string which is newline by default (or can be empty for example)
    """
    print_color(msg, fg=fgcolor.red, end=end)


def print_warn(msg: str, end: str = "\n"):
    """
    Display a warning string in purple foreground (and no background change).

    :param msg: the string to be displayed
    :param end: the terminating string which is newline by default (or can be empty for example)
    """
    print_color(msg, fg=fgcolor.purple, end=end)


def print_info(msg: str, end: str = "\n"):
    """
    Display an informational string in blue foreground (and no background change).

    :param msg: the string to be displayed
    :param end: the terminating string which is newline by default (or can be empty for example)
    """
    print_color(msg, fg=fgcolor.blue, end=end)
