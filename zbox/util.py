import argparse
import os
import re
import subprocess
import sys
from collections import namedtuple
from configparser import ConfigParser, Interpolation
from datetime import datetime
from typing import Optional

from typeguard import typechecked

from zbox.env import ZboxLabel

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(script_dir))


class InitNow:
    def __init__(self):
        self._now = datetime.now()
        os.environ["NOW"] = str(self._now)

    @property
    @typechecked
    def now(self) -> datetime:
        return self._now


class EnvInterpolation(Interpolation):
    """
    Substitute environment variables in the values using 'os.path.expandvars'.
    In addition, a special substitution of ${NOW:<fmt>} is supported to substitute the
    current time (captured by InitNow above) in the 'datetime.strftime' format.

    If 'skip_expansion' is specified in initialization to a non-empty list, then no
    environment variable substitution is performed for those sections but the
    ${NOW:...} substitution is still performed.
    """

    @typechecked
    def __init__(self, now: InitNow, skip_expansion: list[str]):
        self._skip_expansion = skip_expansion
        # for the NOW substitution
        self._now = now
        self._now_re = re.compile(r"\${NOW:([^}]*)}")

    @typechecked
    def before_get(self, parser: ConfigParser, section: str, option: str, value: str, defaults):
        if section not in self._skip_expansion:
            value = os.path.expandvars(value)
        # replace ${NOW:...} pattern with appropriately formatted datetime string
        return re.sub(self._now_re, lambda mt: self._now.now.strftime(mt.group(1)), value)


@typechecked
def get_docker_command(args: argparse.Namespace, option_name: str) -> str:
    # check for podman first then docker
    if args.docker_path:
        return args.docker_path
    elif os.access("/usr/bin/podman", os.X_OK):
        return "/usr/bin/podman"
    elif os.access("/usr/bin/docker", os.X_OK):
        return "/usr/bin/docker"
    else:
        print_color("Neither /usr/bin/podman nor /usr/bin/docker found "
                    f"and no {option_name} option provided",
                    fg=fgcolor.red)
        sys.exit(1)


# read the ini file, recursing into the includes to build the final dictionary
@typechecked
def config_reader(conf_file: str, interpolation: Optional[Interpolation],
                  top_level: str = "") -> ConfigParser:
    if not os.access(conf_file, os.R_OK):
        if top_level:
            sys.exit(f"Config file '{conf_file}' among the includes of '{top_level}' "
                     "does not exist or not readable")
        else:
            sys.exit(f"Config file '{conf_file}' does not exist or not readable")
    config = ConfigParser(allow_no_value=True, interpolation=interpolation, delimiters="=")
    config.optionxform = str
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
@typechecked
def print_config(config: ConfigParser) -> None:
    print({section: dict(config[section]) for section in config.sections()})


@typechecked
def check_running_zbox(docker_cmd: str, box_name: str, include_all: bool = False) -> bool:
    check_result = subprocess.run(
        [docker_cmd, "inspect", "--type=container",
         '--format={{index .Config.Labels "' + ZboxLabel.CONTAINER_TYPE + '"}} {{.State.Status}}',
         box_name], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if check_result.returncode == 0:
        result = check_result.stdout.decode("utf-8").rstrip()
        if include_all:
            return result.startswith("primary ")
        else:
            return result == "primary running"
    else:
        return False


# colors for printing in terminal
TermColors = namedtuple("TermColors",
                        "black red green orange blue purple cyan lightgray reset bold disable")
fgcolor = TermColors("\033[30m", "\033[31m", "\033[32m", "\033[33m", "\033[34m",
                     "\033[35m", "\033[36m", "\033[37m", "\033[00m", "\033[01m", "\033[02m")
bgcolor = TermColors("\033[40m", "\033[41m", "\033[42m", "\033[43m", "\033[44m",
                     "\033[45m", "\033[46m", "\033[47m", "\033[00m", "\033[01m", "\033[02m")


@typechecked
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
    print(full_msg, end=end)
    if end != "\n":
        sys.stdout.flush()
