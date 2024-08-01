"""
Format output of `pacman -Qi ...` as a table having four columns (Name, Version, Description,
  Dependency Of) with headings or as plain string-separated fields.
"""

import argparse
import re
import sys

_VAL_RE = re.compile(r"^\s*[^:]*:\s*")
_WS_RE = re.compile(r"\s\s+")


def parse_separator() -> str:
    """expect a single argument which will be used as the separator between the fields"""
    parser = argparse.ArgumentParser()
    parser.add_argument("separator", type=str,
                        help="use the given separator between the fields of the output")
    args = parser.parse_args()
    return args.separator


def format_dep_of(req_by: str, opt_for: str) -> str:
    """format the `Dependency Of` column to include the required and optional dependencies"""
    dep_of_total_width = 0
    if req_by == "None":
        req_by = ""
    elif req_by:
        req_by = _WS_RE.sub(" ", req_by)
        dep_of_total_width += len(req_by) + 6  # +6 due to being surrounded by 'req()'
    if opt_for == "None":
        opt_for = ""
    elif opt_for:
        opt_for = _WS_RE.sub(" ", opt_for)
        dep_of_total_width += len(opt_for) + 6  # +6 due to being surrounded by 'opt()'

    dep_of_parts: list[str] = []
    if req_by:
        dep_of_parts.extend(("req(", req_by, ")"))
    if opt_for:
        if req_by:
            dep_of_parts.append(",")
        dep_of_parts.extend(("opt(", opt_for, ")"))
    return "".join(dep_of_parts)


def process() -> None:
    """process pacman output on stdin to create a table or plain output"""
    plain_sep = parse_separator()
    name = version = description = req_by = opt_for = ""
    req_by_start = opt_for_start = False

    def format_package() -> None:
        """format details of a package as a table or a plain line with given separator"""
        dep_of = format_dep_of(req_by, opt_for)
        print(f"{name}{plain_sep}{version}{plain_sep}{dep_of}{plain_sep}{description}")

    for line in sys.stdin:
        if line.startswith("Name"):
            if name:
                format_package()
                req_by = opt_for = ""
            name = _VAL_RE.sub("", line).rstrip()
        elif line.startswith("Version"):
            version = _VAL_RE.sub("", line).rstrip()
        elif line.startswith("Description"):
            description = _VAL_RE.sub("", line).rstrip()
        elif line.startswith("Required By"):
            req_by = _VAL_RE.sub("", line).rstrip()
            req_by_start = True
            opt_for_start = False
        elif line.startswith("Optional For"):
            opt_for = _VAL_RE.sub("", line).rstrip()
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
    # add the last one
    if name:
        format_package()


if __name__ == "__main__":
    process()
