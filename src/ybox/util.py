"""
Common utility classes and methods used by the scripts.
"""

import os
import re
import stat
import subprocess
from configparser import BasicInterpolation, ConfigParser, Interpolation
from importlib.resources import files
from typing import Any, Iterable, Optional, Sequence

from simple_term_menu import TerminalMenu  # type: ignore
from tabulate import tabulate

from ybox import __version__ as PRODUCT_VERSION

from .cmd import build_bash_command
from .config import Consts, StaticConfiguration
from .env import Environ, PathName, resolve_inc_path
from .print import fgcolor, get_terminal_width, print_warn


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

    # override before_read rather than before_get because expanded vars are needed when writing
    # into the state.db database too
    def before_read(self, parser, section: str, option: str, value: str) -> str:  # type: ignore
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
    # TODO: relative paths inside an include file (e.g. scripts in distro.ini) should be relative
    # to the include and not the parent
    for include in includes.split(","):
        if not (include := include.strip()):
            continue
        inc_file = resolve_inc_path(include, conf_file)
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


def ini_file_reader(fd: Iterable[str], interpolation: Optional[Interpolation],
                    case_sensitive: bool = True) -> ConfigParser:
    """
    Read an INI file from a given file handle. It applies some basic rules that are used
    for all ybox configurations like allowing no values, only '=' as delimiters and
    case-sensitive keys.

    :param fd: file handle for the INI format data
    :param interpolation: if provided then used for value interpolation
    :param case_sensitive: if true then keys are case-sensitive (default) else case-insensitive
    :return: instance of `configparser.ConfigParser` built after parsing the given file
    """
    config = ConfigParser(allow_no_value=True, interpolation=interpolation, delimiters="=")
    if case_sensitive:
        config.optionxform = str  # type: ignore
    config.read_file(fd)
    return config


def copy_file(src: PathName, dest: str, permissions: Optional[int] = None) -> None:
    """
    Copy a given source file (can be on filesystem or package resource) to destination path
    overwriting if it exists, and with given optional permissions.

    :param src: the source file or package resource
    :param dest: destination file path
    :param permissions: optional file permissions as an integer as accepted by :func:`os.chmod`,
                        defaults to None
    """
    with open(dest, "w", encoding="utf-8") as dest_fd:
        dest_fd.write(src.read_text(encoding="utf-8"))
    if permissions is not None:
        os.chmod(dest, permissions)
    elif hasattr(src, "stat"):  # copy the permissions
        # pyright does not check hasattr, hence the "type: ignore" instead of artificial TypeGuards
        if hasattr(src, "resolve"):
            src = src.resolve()  # type: ignore
        perms = stat.S_IMODE(src.stat().st_mode)  # type: ignore
        os.chmod(dest, perms)


def copy_ybox_scripts_to_container(conf: StaticConfiguration, distro_config: ConfigParser) -> None:
    """
    Copy ybox setup scripts to local directory mounted on container.

    :param conf: the `StaticConfiguration` of the container
    :param distro_config: the parsed configuration (`ConfigParser`) of the Linux distribution
    """
    env = conf.env
    # copy the common scripts
    for script in Consts.resource_scripts():
        path = env.search_config_path(f"resources/{script}", only_sys_conf=True)
        copy_file(path, f"{conf.scripts_dir}/{script}", permissions=0o750)
    # also copy distribution specific scripts
    for script in Consts.distribution_scripts():
        path = env.search_config_path(conf.distribution_config(conf.distribution, script),
                                      only_sys_conf=True)
        copy_file(path, f"{conf.scripts_dir}/{script}", permissions=0o750)
    base_section = distro_config["base"]
    if scripts := base_section.get("scripts"):
        for script in scripts.split(","):
            path = env.search_config_path(conf.distribution_config(conf.distribution, script),
                                          only_sys_conf=True)
            copy_file(path, f"{conf.scripts_dir}/{script}")
        # finally copy the ybox python module which may be used by distribution scripts
        src_dir = files("ybox")
        dest_dir = f"{conf.scripts_dir}/ybox"
        os.makedirs(dest_dir, exist_ok=True)
        for resource in src_dir.iterdir():
            if resource.is_file():
                copy_file(resource, f"{dest_dir}/{resource.name}")
    # finally write the current version string
    version_file = f"{conf.scripts_dir}/version"
    with open(version_file, "w", encoding="utf-8") as version_fd:
        version_fd.write(PRODUCT_VERSION)


def get_ybox_version(conf: StaticConfiguration) -> str:
    """
    Get the product version string recorded in the container or empty if no version was recorded.

    :param conf: the `StaticConfiguration` of the container
    :return: the version recorded in the container as a string, or empty if not present
    """
    version_file = f"{conf.scripts_dir}/version"
    if os.access(version_file, os.R_OK):
        with open(version_file, "r", encoding="utf-8") as fd:
            return fd.read().strip()
    return ""


def check_installed_package(docker_cmd: str, check_cmd: str, package: str,
                            container_name: str) -> tuple[int, str]:
    """
    Check if a given package is installed in a container.

    :param docker_cmd: the docker/podman executable to use
    :param check_cmd: the command used to check the existence of the package
    :param package: name of the package to check
    :param container_name: name of the container
    :return: exit code of the `check_cmd` which should be 0 if the package exists
    """
    check_result = subprocess.run(build_bash_command(
        docker_cmd, container_name, check_cmd.format(package=package), enable_pty=False),
        check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    output = check_result.stdout.decode("utf-8").splitlines()
    first_line = output[0] if len(output) > 0 else ""
    return check_result.returncode, first_line


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
    if isinstance(selection, int):
        return items[int(selection)]
    print_warn("Aborted selection")
    return None


def format_as_table(table: Iterable[Iterable[Any]], headers: Sequence[str], colors: Sequence[str],
                    fmt: str, col_width_ratios: Iterable[float]) -> str:
    """
    Format given table of values as a table appropriate for display on a terminal.

    :param table: an `Iterable` of `Iterable` values as accepted by :func:`tabulate.tabulate`
    :param headers: a `Sequence` of header names corresponding to each column in the `table`
    :param colors: a `Sequence` of color strings (e.g. :func:`fgcolor.red`) for each of the columns
    :param fmt: formatting style of the table (e.g. `rounded_grid`) as accepted by
                :func:`tabulate.tabulate`
    :param col_width_ratios: ratios of widths of the columns as an `Iterable` of floats; the
                             length of this should match that of `table` and `headers_with_colors`
    :return: formatted table as a string appropriate for display in the current terminal
    """
    # surround the table values and headers with the given color strings
    table = ((f"{color}{v}{fgcolor.reset}" for v, color in zip(line, colors)) for line in table)
    headers = [f"{color}{header}{fgcolor.reset}" for header, color in zip(headers, colors)]
    # reduce available width for borders and padding
    available_width = get_terminal_width() - (len(headers) - 1) * 4
    ratio_sum = sum(col_width_ratios)
    max_col_widths = [int(ratio * available_width / ratio_sum) for ratio in col_width_ratios]
    return tabulate(table, headers=headers, tablefmt=fmt, maxcolwidths=max_col_widths)


def page_output(out: str, pager: str) -> None:
    """
    Display given string on the terminal one screenful at a time using the given `pager` command.

    :param out: the string to be displayed
    :param pager: the command to be executed for pagination as a separate process
    """
    with subprocess.Popen(pager.split(), stdin=subprocess.PIPE) as page_in:
        assert page_in.stdin is not None
        page_in.stdin.write(out.encode("utf-8"))
        page_in.communicate()
