import argparse
import os
import re
import subprocess
from collections import namedtuple
from configparser import ConfigParser, Interpolation
from enum import Enum, auto
from typing import Optional

from .env import Environ, ZboxLabel


class NotSupportedError(Exception):
    """Raised when an operation or configuration is not supported or invalid."""


class PkgMgr(Enum):
    install = auto()
    opt_deps = auto()
    uninstall = auto()
    uninstall_w_deps = auto()
    quiet_flag = auto()
    update_all = auto()
    cleanup = auto()
    info = auto()
    list = auto()
    list_all = auto()


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
        if not value:
            return value
        if section not in self.__skip_expansion:
            value = os.path.expandvars(value)
        # replace ${NOW:...} pattern with appropriately formatted datetime string
        return re.sub(self.__NOW_RE, lambda mt: self.__now.strftime(mt.group(1)), value)


def get_docker_command(args: argparse.Namespace, option_name: str) -> str:
    # check for podman first then docker
    if args.docker_path:
        return args.docker_path
    elif os.access("/usr/bin/podman", os.X_OK):
        return "/usr/bin/podman"
    elif os.access("/usr/bin/docker", os.X_OK):
        return "/usr/bin/docker"
    else:
        raise FileNotFoundError("Neither /usr/bin/podman nor /usr/bin/docker found "
                                f"and no '{option_name}' option has been provided")


# read the ini file, recursing into the includes to build the final dictionary
def config_reader(conf_file: str, interpolation: Optional[Interpolation],
                  top_level: str = "") -> ConfigParser:
    if not os.access(conf_file, os.R_OK):
        if top_level:
            raise FileNotFoundError(f"Config file '{conf_file}' among the includes of "
                                    f"'{top_level}' does not exist or not readable")
        else:
            raise FileNotFoundError(f"Config file '{conf_file}' does not exist or not readable")
    config = ConfigParser(allow_no_value=True, interpolation=interpolation, delimiters="=")
    config.optionxform = str  # type: ignore
    config.read(conf_file)
    if not top_level:
        top_level = conf_file
    if includes := config.get("base", "includes", fallback=""):
        for include in includes.split(","):
            if include := include.strip():
                inc_file = include if os.path.isabs(
                    include) else f"{os.path.dirname(conf_file)}/{include}"
                inc_conf = config_reader(inc_file, interpolation, top_level)
                for section in inc_conf.sections():
                    if section not in config.sections():
                        config[section] = inc_conf[section]
                    else:
                        conf_section = config[section]
                        inc_section = inc_conf[section]
                        for key in inc_section:
                            if key not in conf_section:
                                conf_section[key] = inc_section[key]
    return config


# print the entire contents of a ConfigParser as a nested dictionary
def print_config(config: ConfigParser) -> None:
    print({section: dict(config[section]) for section in config.sections()})


def check_zbox_state(docker_cmd: str, box_name: str, expected_states: list[str]) -> bool:
    check_result = subprocess.run(
        [docker_cmd, "inspect", "--type=container",
         '--format={{index .Config.Labels "' + ZboxLabel.CONTAINER_TYPE + '"}} {{.State.Status}}',
         box_name], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if check_result.returncode == 0:
        result = check_result.stdout.decode("utf-8").rstrip()
        primary_zbox = "primary "
        if result.startswith(primary_zbox):
            state = result[len(primary_zbox):]
            if expected_states:
                return state in expected_states
            else:
                return True

    return False


def run_and_get_output(cmd: str, capture_output: bool = True, exit_on_error: bool = True) -> str:
    result = subprocess.run(cmd.split(), capture_output=capture_output)
    if result.returncode != 0:
        if exit_on_error:
            print_error(f"FAILURE in '{cmd}'")
            if capture_output:
                print(result.stdout.decode("utf-8"))
                print(result.stderr.decode("utf-8"))
            raise ChildProcessError
        else:
            return ""
    return result.stdout.decode("utf-8") if capture_output else ""


# colors for printing in terminal
TermColors = namedtuple("TermColors",
                        "black red green orange blue purple cyan lightgray reset bold disable")
fgcolor = TermColors("\033[30m", "\033[31m", "\033[32m", "\033[33m", "\033[34m",
                     "\033[35m", "\033[36m", "\033[37m", "\033[00m", "\033[01m", "\033[02m")
bgcolor = TermColors("\033[40m", "\033[41m", "\033[42m", "\033[43m", "\033[44m",
                     "\033[45m", "\033[46m", "\033[47m", "\033[00m", "\033[01m", "\033[02m")


def print_color(msg: str, fg: Optional[str] = None,
                bg: Optional[str] = None, end: str = "\n"):
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


def print_error(msg: str, end: str = "\n"):
    print_color(msg, fg=fgcolor.red, end=end)


def print_warn(msg: str, end: str = "\n"):
    print_color(msg, fg=fgcolor.purple, end=end)


def print_info(msg: str, end: str = "\n"):
    print_color(msg, fg=fgcolor.blue, end=end)
