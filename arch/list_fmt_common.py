"""
Common utilities for `list_fmt` and `list_fmt_long`.
"""

import argparse

from zbox.util import fgcolor

# aliases for colors used in display
FG_NAME = fgcolor.lightgray
FG_VER = fgcolor.orange
FG_DESC = fgcolor.blue
FG_REQ = fgcolor.purple
FG_OPT = fgcolor.cyan
FG_NONE = fgcolor.reset


def parse_separator() -> str:
    """expect a single optional argument asking for non-tabular output with given separator"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--plain-separator", type=str,
                        help="use 'plain' output (appropriate for processing in scripts etc) "
                             "with given separator between fields instead of using table layout")
    args = parser.parse_args()
    return args.plain_separator
