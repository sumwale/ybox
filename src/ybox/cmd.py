"""
Utilities related to command execution like running a command, get docker/podman executable etc.
"""

import argparse
import os
import subprocess
import sys
from enum import Enum
from typing import Optional, Union

from .print import print_error, print_notice, print_warn


class PkgMgr(str, Enum):
    """
    Package manager actions that are defined for each Linux distribution in its distro.ini file.
    """
    INSTALL = "install"
    CHECK_INSTALL = "check_install"
    QUIET_FLAG = "quiet_flag"
    QUIET_DETAILS_FLAG = "quiet_details_flag"
    OPT_DEPS = "opt_deps"
    OPT_DEP_FLAG = "opt_dep_flag"
    UNINSTALL = "uninstall"
    PURGE_FLAG = "purge_flag"
    REMOVE_DEPS_FLAG = "remove_deps_flag"
    UPDATE_META = "update_meta"
    UPDATE = "update"
    UPDATE_ALL = "update_all"
    CLEAN = "clean"
    CLEAN_QUIET = "clean_quiet"
    MARK_EXPLICIT = "mark_explicit"
    INFO = "info"
    INFO_ALL = "info_all"
    LIST = "list"
    LIST_ALL = "list_all"
    LIST_LONG = "list_long"
    LIST_ALL_LONG = "list_all_long"
    LIST_FILES = "list_files"
    SEARCH = "search"
    SEARCH_ALL = "search_all"
    SEARCH_OFFICIAL_FLAG = "search_official_flag"
    SEARCH_WORD_START_FLAG = "search_word_start_flag"
    SEARCH_WORD_END_FLAG = "search_word_end_flag"


class YboxLabel(str, Enum):
    """
    Labels for ybox created objects.
    """
    CONTAINER_TYPE = "io.ybox.container.type"
    CONTAINER_DISTRIBUTION = "io.ybox.container.distribution"

    # ybox container types (first two are temporary ones)
    CONTAINER_BASE = f"{CONTAINER_TYPE}=base"
    CONTAINER_COPY = f"{CONTAINER_TYPE}=copy"
    CONTAINER_PRIMARY = f"{CONTAINER_TYPE}=primary"


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
    print_error("Neither /usr/bin/podman nor /usr/bin/docker found "
                f"and no '{option_name}' option has been provided")
    raise FileNotFoundError(f"No podman/docker found or '{option_name}' specified")


def verify_ybox_state(docker_cmd: str, box_name: str, expected_states: list[str],
                      exit_on_error: bool = True, cnt_state_msg: str = "") -> bool:
    """
    Verify that a given ybox container exists and is in one of the given states.

    :param docker_cmd: the docker/podman executable to use
    :param box_name: name of the ybox container
    :param expected_states: list of one or more expected states like 'running', 'exited';
                            empty value means any state is permissible
    :param exit_on_error: whether to exit using `sys.exit` if verification fails
    :param cnt_state_msg: string to be inserted in the error message "No...ybox container ...",
                          so this should be a user-friendly name for the `expected_states` with
                          a space at the start e.g. ' active', ' stopped'
    :return: if `exit_on_error` is False, then return the result of verification as True or False
    """
    check_result = subprocess.run(
        [docker_cmd, "inspect", "--type=container", '--format={{index .Config.Labels "' +
         YboxLabel.CONTAINER_TYPE.value + '"}} {{.State.Status}}', box_name],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if check_result.returncode != 0:
        if exit_on_error:
            print_error(f"No{cnt_state_msg} ybox container named '{box_name}' found")
            sys.exit(check_result.returncode)
        else:
            return False
    else:
        result = check_result.stdout.decode("utf-8").strip()
        primary_ybox = "primary "
        if result.startswith(primary_ybox):
            state = result[len(primary_ybox):]
            if expected_states:
                if not (exists := state in expected_states) and exit_on_error:
                    sys.exit(1)
                else:
                    return exists
            else:
                return True
    if exit_on_error:
        sys.exit(1)
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
            _print_subprocess_output(result)
        if not error_msg:
            error_msg = f"'{' '.join(args)}'"
        if error_msg != "SKIP":
            print_error(f"FAILURE in {error_msg} -- see the output above for details")
        if exit_on_error:
            sys.exit(result.returncode)
        else:
            return result.returncode
    if capture_output and result.stderr:
        print_warn(result.stderr.decode("utf-8"))
    return result.stdout.decode("utf-8") if capture_output else result.returncode


def _print_subprocess_output(result: subprocess.CompletedProcess[bytes]) -> None:
    """print completed subprocess output in color (orange for standard output and purple
       for standard error)"""
    if result.stdout:
        print_notice(result.stdout.decode("utf-8"))
    if result.stderr:
        print_warn(result.stderr.decode("utf-8"))
