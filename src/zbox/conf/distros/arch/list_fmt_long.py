"""
Format output of `pacman -Qi ...` as a table having four columns (Name, Version, Description,
  Dependency Of) with headings or as plain string-separated fields.
"""

import os
import re
import shutil
import sys
from typing import Tuple

from tabulate import tabulate

from list_fmt_common import FG_NAME, FG_VER, FG_DESC, FG_REQ, FG_OPT, FG_NONE, parse_separator

__VAL_RE = re.compile(r"^\s*[^:]*:\s*")
__WS_RE = re.compile(r"\s\s+")

# Adjust column widths as per the terminal width.
# Use stderr for the terminal width since stdout is piped to pager.
try:
    terminal_width = os.get_terminal_size(sys.stderr.fileno()).columns
except OSError:
    terminal_width = shutil.get_terminal_size().columns
available_width = terminal_width - 12  # -12 is for the borders and padding

# using ratio of 4:4:6:6 for the four columns
nv_width = int(available_width * 4.0 / 20.0)
desc_width = int(available_width * 6.0 / 20.0)
dep_of_width = int(available_width * 6.0 / 20.0)


def format_dep_of(req_by: str, opt_for: str, description: str, plain_sep: str) -> str:
    """format the `Dependency Of` column to include the required and optional dependencies"""
    dep_of_total_width = 0
    if req_by == "None":
        req_by = ""
    elif req_by:
        req_by = __WS_RE.sub(" ", req_by)
        dep_of_total_width += len(req_by) + 6  # +6 due to being surrounded by 'req()'
    if opt_for == "None":
        opt_for = ""
    elif opt_for:
        opt_for = __WS_RE.sub(" ", opt_for)
        dep_of_total_width += len(opt_for) + 6  # +6 due to being surrounded by 'opt()'

    dep_of_parts: list[str] = []
    if plain_sep:
        if req_by:
            dep_of_parts.append(f"req({req_by})")
        if opt_for:
            dep_of_parts.append(f"opt({opt_for})")
    else:
        # description is not trimmed, so can use up to it's size
        max_width = max(dep_of_width, len(description))
        if dep_of_total_width > max_width:
            trim_factor = (dep_of_total_width - max_width) / float(len(req_by) + len(opt_for))
            if req_by:
                trim_size = int(trim_factor * len(req_by) + 0.5)
                req_by = req_by[:max(0, len(req_by) - trim_size - 3)] + "..."
            if opt_for:
                trim_size = int(trim_factor * len(opt_for) + 0.5)
                opt_for = opt_for[:max(0, len(opt_for) - trim_size - 3)] + "..."
        if req_by:
            dep_of_parts.append(f"{FG_REQ}req({req_by}){FG_NONE}")
        if opt_for:
            dep_of_parts.append(f"{FG_OPT}opt({opt_for}){FG_NONE}")
    return ",".join(dep_of_parts)


def process() -> None:
    """process pacman output on stdin to create a table or plain output"""
    table: list[Tuple[str, str, str, str]] = []
    plain_sep = parse_separator()
    name = version = description = req_by = opt_for = ""
    req_by_start = opt_for_start = False

    def format_package() -> None:
        """format details of a package as a table or a plain line with given separator"""
        # because opt_for can be multi-line which will be skipped if processed here
        dep_of = format_dep_of(req_by, opt_for, description, plain_sep)
        if plain_sep:
            print(f"{name}{plain_sep}{version}{plain_sep}{description}{plain_sep}{dep_of}")
        else:
            table.append((f"{FG_NAME}{name}{FG_NONE}", f"{FG_VER}{version}{FG_NONE}",
                          f"{FG_DESC}{description}{FG_NONE}", dep_of))

    for line in sys.stdin:
        if line.startswith("Name"):
            if name:
                format_package()
                req_by = opt_for = ""
            name = __VAL_RE.sub("", line).rstrip()
        elif line.startswith("Version"):
            version = __VAL_RE.sub("", line).rstrip()
        elif line.startswith("Description"):
            description = __VAL_RE.sub("", line).rstrip()
        elif line.startswith("Required By"):
            req_by = __VAL_RE.sub("", line).rstrip()
            req_by_start = True
            opt_for_start = False
        elif line.startswith("Optional For"):
            opt_for = __VAL_RE.sub("", line).rstrip()
            opt_for_start = True
            req_by_start = False
        elif line and line[0].isspace():
            # "Required By" and "Optional For" can have multiline output
            if req_by_start:
                req_by += line.rstrip()
            elif opt_for_start:
                opt_for += line.rstrip()
        elif req_by_start or opt_for_start:
            req_by_start = opt_for_start = False

    if name:
        format_package()
    if not plain_sep:
        try:
            print(tabulate(table, headers=(f"{FG_NAME}Name{FG_NONE}", f"{FG_VER}Version{FG_NONE}",
                                           f"{FG_DESC}Description{FG_NONE}",
                                           f"Dependency Of ({FG_REQ}req {FG_OPT}opt{FG_NONE})"),
                           tablefmt="rounded_grid",
                           maxcolwidths=[nv_width, nv_width, desc_width, dep_of_width]))
        except BrokenPipeError:  # ignore error if subsequent pipe to pager is broken
            pass


if __name__ == "__main__":
    process()
