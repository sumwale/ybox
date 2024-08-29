"""
Format output of `pacman -Qi ...` as a table having four columns (Name, Version, Dependency Of,
  Description) string-separated fields using a user provided separator.
"""

import argparse
import re
import sys
from collections import defaultdict

_VAL_RE = re.compile(r"\s*([^:]+?)\s*:\s*(.*?)\s*")
_WS_RE = re.compile(r"\s{2,}")


def parse_separator() -> str:
    """expect a single argument which will be used as the separator between the fields"""
    parser = argparse.ArgumentParser(description="Format output of 'pacman -Qi ...' into a table.")
    parser.add_argument("separator", type=str,
                        help="separator to use between the fields of the output")
    args = parser.parse_args()
    return args.separator


def format_dep_of(req_by: list[str], opt_for: list[str]) -> str:
    """format the `Dependency Of` column to include the required and optional dependencies"""
    if req_by:
        req_by = [] if req_by[0] == "None" else [_WS_RE.sub(" ", req) for req in req_by]
    if opt_for:
        opt_for = [] if opt_for[0] == "None" else [_WS_RE.sub(" ", opt) for opt in opt_for]

    dep_of_parts: list[str] = []
    if req_by:
        dep_of_parts.extend(("req(", *req_by, ")"))
    if opt_for:
        if req_by:
            dep_of_parts.append(",")
        dep_of_parts.extend(("opt(", *opt_for, ")"))
    return "".join(dep_of_parts)


def process() -> None:
    """process pacman output on stdin to create fields separated by a given separator"""
    sep = parse_separator()
    pkg_map: defaultdict[str, list[str]] = defaultdict(list[str])
    key = ""

    def k_val(key: str) -> str:
        """return the value of the key in `pkg_map` as a single string"""
        return "".join(pkg_map[key])

    def format_package() -> None:
        """format details of a package as a table or a plain line with given separator"""
        dep_of = format_dep_of(pkg_map["Required By"], pkg_map["Optional For"])
        print(f"{k_val('Name')}{sep}{k_val('Version')}{sep}{dep_of}{sep}{k_val('Description')}")

    for line in sys.stdin:
        if (match := _VAL_RE.fullmatch(line)):
            key, value = match.groups()
            if key == "Name" and pkg_map:
                # indicates start of fields of a new package, so output previous one and clear
                format_package()
                pkg_map.clear()
            pkg_map[key].append(value)
        elif line and line[0].isspace():
            # "Description", "Required By" and "Optional For" can have multiline output
            val_list = pkg_map[key]
            # add space separately to avoid adding it in `format_dep_of``
            val_list.append(" ")
            val_list.append(line.strip())
    # output the last package
    if pkg_map:
        format_package()


if __name__ == "__main__":
    process()
