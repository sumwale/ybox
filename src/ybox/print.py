"""
Utility `namedtuple`s and methods to print in color on terminal/console.
"""

from typing import IO, NamedTuple, Optional


# define color names for printing in terminal
class TermColors(NamedTuple):
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


def print_color(msg: str, fg: Optional[str] = None,
                bg: Optional[str] = None, end: str = "\n", file: Optional[IO[str]] = None) -> None:
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
    :param file: the text-mode file object to use for writing (defaults to `sys.stdout`)
    """
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
