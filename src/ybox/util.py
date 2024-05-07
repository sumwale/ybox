"""
Common utility classes and methods used by the scripts.
"""

import os
import re
import subprocess
from configparser import BasicInterpolation, ConfigParser, Interpolation
from pathlib import Path
from typing import Optional

from simple_term_menu import TerminalMenu  # type: ignore

from .env import Environ, PathName
from .print import print_warn
from .state import YboxStateManagement


class NotSupportedError(Exception):
    """Raised when an operation or configuration is not supported or invalid."""


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

    _NOW_RE = re.compile(r"\${NOW:([^}]*)}")

    def __init__(self, env: Environ, skip_expansion: list[str]):
        super().__init__()
        self._skip_expansion = skip_expansion
        # for the NOW substitution
        self._now = env.now

    # override before_read rather than before_get because we need expanded vars when writing
    # into the state.db database too
    def before_read(self, parser, section: str, option: str, value: str):
        """Override before_read to substitute environment variables and ${NOW...} pattern.
           This method is overridden rather than before_get because expanded variables are
           also required when writing the configuration into the state.db database."""
        if not value:
            return value
        if section not in self._skip_expansion:
            value = os.path.expandvars(value)
        # replace ${NOW:...} pattern with appropriately formatted datetime string
        return self._NOW_RE.sub(lambda mt: self._now.strftime(mt.group(1)), value)


# read the ini file, recursing into the includes to build the final dictionary
def config_reader(conf_file: PathName, interpolation: Optional[Interpolation],
                  top_level: Optional[PathName] = None) -> ConfigParser:
    """
    Read the container configuration INI file, recursing into the includes to build the final
    dictionary having the sections with corresponding key-value pairs.

    :param conf_file: the configuration file to be read as a `Path` or resource file from
                      importlib (`Traversable`)
    :param interpolation: if provided then used for value interpolation
    :param top_level: the top-level configuration file; don't pass this when calling
                      externally (or set it the same as `conf_file` argument)
    :return: instance of `configparser.ConfigParser` built after parsing the given file as
             well as any includes recursively
    """
    if not conf_file.is_file():
        if top_level:
            raise FileNotFoundError(f"Config file '{conf_file}' among the includes of "
                                    f"'{top_level}' does not exist or not a file")
        raise FileNotFoundError(f"Config file '{conf_file}' does not exist or not a file")
    with conf_file.open("r", encoding="utf-8") as conf_fd:
        config = ini_file_reader(conf_fd, interpolation)
    if not top_level:
        top_level = conf_file
    if not (includes := config.get("base", "includes", fallback="")):
        return config
    for include in includes.split(","):
        if not (include := include.strip()):
            continue
        inc_file = Path(include) if os.path.isabs(include) \
            else conf_file.parent.joinpath(include)  # type: ignore
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
    for all ybox configurations like allowing no values, only '=' as delimiters and
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


def get_other_shared_containers(container_name: str, shared_root: str,
                                state: YboxStateManagement) -> list[str]:
    """
    Get other containers sharing the same shared_root as the given container having a shared root.

    :param container_name: name of the container
    :param shared_root: the local shared root directory if `shared_root` flag is enabled
                        for the container
    :param state: instance of `YboxStateManagement`
    :return: list of containers sharing the same shared root with the given container
    """
    if shared_root:
        shared_containers = state.get_containers(shared_root=shared_root)
        shared_containers.remove(container_name)
        return shared_containers
    return []


def check_installed_package(docker_cmd: str, check_cmd: str, package: str,
                            container_name: str) -> int:
    """
    Check if a given package is installed in a container.

    :param docker_cmd: the docker/podman executable to use
    :param check_cmd: the command used to check the existence of the package
    :param package: name of the package to check
    :param container_name: name of the container
    :return: exit code of the `check_cmd` which should be 0 if the package exists
    """
    return subprocess.run(
        [docker_cmd, "exec", container_name, "/bin/bash", "-c", f"{check_cmd} {package}"],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def select_item_from_menu(items: list[str]) -> Optional[str]:
    """
    Display a list of items on terminal and allow user to select an item from it interactively
    using arrow keys and all.

    :param items: list of items to be displayed
    :return: the chosen item, or None if user aborted the selection
    """
    terminal_menu = TerminalMenu(items,
                                 status_bar="Press <Enter> to select, <Esc> to exit")
    selection = terminal_menu.show()
    if selection is not None:
        return items[int(selection)]
    print_warn("Aborted selection")
    return None
