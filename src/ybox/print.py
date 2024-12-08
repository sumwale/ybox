"""
Utility classes and methods to print in color on terminal/console.
"""

import os
import shutil
import sys
from dataclasses import dataclass
from typing import IO, Optional


# define color names for printing in terminal
@dataclass(frozen=True)
class TermColors:
    """basic ASCII color strings for terminals"""
    black: str
    red: str
    green: str
    orange: str
    blue: str
    purple: str
    cyan: str
    lightgray: str
    reset: str
    bold: str
    disable: str


# foreground colors in the terminal
fgcolor = TermColors(
    "\033[30m", "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m",
    "\033[37m", "\033[00m", "\033[01m", "\033[02m")
# background colors in the terminal
bgcolor = TermColors(
    "\033[40m", "\033[41m", "\033[42m", "\033[43m", "\033[44m", "\033[45m", "\033[46m",
    "\033[47m", "\033[00m", "\033[01m", "\033[02m")


def get_terminal_width() -> int:
    """
    Get the best estimate of the width of the current terminal.
    This may not work well if the output is piped, for example.
    """
    # Use stderr for the terminal width since stdout can be piped to pager.
    try:
        return os.get_terminal_size(sys.stderr.fileno()).columns
    except OSError:
        return shutil.get_terminal_size().columns


def print_color(msg: str, fg: Optional[str] = None,
                bg: Optional[str] = None, end: str = "\n", file: Optional[IO[str]] = None) -> None:
    """
    Display given string to standard output with foreground and background colors, if provided.
    The colors will show up as expected on most known Linux terminals and console though
    some colors may look different on different terminal implementation
    (e.g. orange could be more like yellow).

    :param msg: the string to be displayed
    :param fg: the foreground color of the string
    :param bg: the background color of the string
    :param end: the terminating string which is newline by default (or can be empty for example)
    :param file: the text-mode file object to use for writing (defaults to `sys.stdout`)
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
    print(full_msg, end=end, file=file, flush=end != "\n")


def print_error(msg: str, end: str = "\n", file: Optional[IO[str]] = None) -> None:
    """
    Display an error string in red foreground (and no background change).

    :param msg: the string to be displayed
    :param end: the terminating string which is newline by default (or can be empty for example)
    :param file: the text-mode file object to use for writing (defaults to `sys.stderr`)
    """
    if not file:
        file = sys.stderr
    print_color(msg, fg=fgcolor.red, end=end, file=file)


def print_warn(msg: str, end: str = "\n", file: Optional[IO[str]] = None):
    """
    Display a warning string in purple foreground (and no background change).

    :param msg: the string to be displayed
    :param end: the terminating string which is newline by default (or can be empty for example)
    :param file: the text-mode file object to use for writing (defaults to `sys.stdout`)
    """
    print_color(msg, fg=fgcolor.purple, end=end, file=file)


def print_notice(msg: str, end: str = "\n", file: Optional[IO[str]] = None):
    """
    Display a string in orange foreground (and no background change).

    :param msg: the string to be displayed
    :param end: the terminating string which is newline by default (or can be empty for example)
    :param file: the text-mode file object to use for writing (defaults to `sys.stdout`)
    """
    print_color(msg, fg=fgcolor.orange, end=end, file=file)


def print_info(msg: str, end: str = "\n", file: Optional[IO[str]] = None):
    """
    Display an informational string in blue foreground (and no background change).

    :param msg: the string to be displayed
    :param end: the terminating string which is newline by default (or can be empty for example)
    :param file: the text-mode file object to use for writing (defaults to `sys.stdout`)
    """
    print_color(msg, fg=fgcolor.blue, end=end, file=file)
