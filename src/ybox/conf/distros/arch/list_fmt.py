"""
Format output of the form "<name> <version>" as a table with headings or as plain string-separated
fields.
"""

import sys

from list_fmt_common import FG_NAME, FG_NONE, FG_VER, parse_separator
from tabulate import tabulate


def process() -> None:
    """process pacman output on stdin to create a table or plain output"""
    table: list[tuple[str, str]] = []
    plain_sep = parse_separator()
    for line in sys.stdin:
        s_line = line.rstrip().split(maxsplit=1)
        name = s_line[0]
        version = s_line[1] if len(s_line) == 2 else ""
        if plain_sep:
            print(f"{name}{plain_sep}{version}")
        else:
            table.append((f"{FG_NAME}{name}{FG_NONE}", f"{FG_VER}{version}{FG_NONE}"))

    if not plain_sep:
        try:
            # outline formats like 'rounded_outline' would be preferable, but unfortunately they
            # are broken for multiline values, hence using the relatively better looking format
            # from the non-broken ones
            print(tabulate(table, headers=(f"{FG_NAME}Name{FG_NONE}",
                                           f"{FG_VER}Version{FG_NONE}"), tablefmt="psql"))
        except BrokenPipeError:  # ignore error if subsequent pipe to pager is broken
            pass


if __name__ == "__main__":
    process()
