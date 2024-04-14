import os
import re
import sys
import typing
from collections import namedtuple
from configparser import ConfigParser
from datetime import datetime

from typeguard import typechecked


class InitNow:
    def __init__(self):
        self._now = datetime.now()
        os.environ["NOW"] = str(self.now)

    @property
    @typechecked
    def now(self) -> datetime:
        return self._now


# read the ini file, recursing into the includes to build the final dictionary
@typechecked
def config_reader(conf_file: str, top_level: str = "") -> ConfigParser:
    if not os.access(conf_file, os.R_OK):
        if top_level:
            sys.exit(f"Config file '{conf_file}' among the includes of '{top_level}' "
                     "does not exist or not readable")
        else:
            sys.exit(f"Config file '{conf_file}' does not exist or not readable")
    config = ConfigParser(allow_no_value=True, interpolation=None, delimiters="=")
    config.optionxform = str
    config.read(conf_file)
    if not top_level:
        top_level = conf_file
    if "base" in config and "includes" in config["base"]:
        for include in config["base"]["includes"].split(","):
            if include := include.strip():
                inc_conf = config_reader(f"{os.path.dirname(conf_file)}/{include}", top_level)
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


# Replace the environment variables and the special ${NOW:...} from all values.
# If 'skip_section' is specified to a non-empty value, then no environment variable
# substitution is done for that section but the ${NOW...} substitution is still performed.
@typechecked
def config_post_process(config: ConfigParser, now: InitNow, skip_section: str) -> ConfigParser:
    # prepare NOW substitution
    now_re = re.compile(r"\${NOW:([^}]*)}")
    for section in config.sections():
        conf_section = config[section]
        for key in conf_section:
            if val := conf_section[key]:
                # replace ${NOW:...} pattern with appropriately formatted datetime string
                new_val = re.sub(now_re, lambda mt: now.now.strftime(mt.group(1)), val)
                if key != skip_section:
                    new_val = os.path.expandvars(new_val)
                if new_val is not val:
                    conf_section[key] = new_val
    return config


# print the entire contents of a ConfigParser as a nested dictionary
@typechecked
def print_config(config: ConfigParser) -> None:
    print({section: dict(config[section]) for section in config.sections()})


# colors for printing in terminal
TermColors = namedtuple("TermColors",
                        "black red green orange blue purple cyan lightgray reset bold disable")
fgcolor = TermColors("\033[30m", "\033[31m", "\033[32m", "\033[33m", "\033[34m",
                     "\033[35m", "\033[36m", "\033[37m", "\033[00m", "\033[01m", "\033[02m")
bgcolor = TermColors("\033[40m", "\033[41m", "\033[42m", "\033[43m", "\033[44m",
                     "\033[45m", "\033[46m", "\033[47m", "\033[00m", "\033[01m", "\033[02m")


@typechecked
def print_color(msg: str, fg: typing.Optional[str] = None,
                bg: typing.Optional[str] = None, end: str = "\n"):
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
