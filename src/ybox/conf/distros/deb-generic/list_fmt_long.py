"""
Format output of `grep-status -FPackage,Provides -sPackage,Version,Pre-Depends,Depends,Recommends,\
    Suggests,Description -e "..."` as a table having four columns (Name, Version, Dependency Of,
  Description) string-separated fields using a user provided separator.
"""

import argparse
import re
import sys
from collections import defaultdict
from typing import Iterable

_VAL_RE = re.compile(r"\s*([^:]+?)\s*:\s*(.*?)\s*")
_DEP_RE = re.compile(r"([^,|\s]+)\s*(\([^)]*\)\s*)?[,|]?\s*")
_DOT_LINE = re.compile(r"\s*\.\s*")


def parse_separator():
    """expect a single argument which will be used as the separator between the fields"""
    parser = argparse.ArgumentParser(description="Format output of grep-status into a table.")
    parser.add_argument("separator", type=str,
                        help="separator to use between the fields of the output")
    args = parser.parse_args()
    return args.separator


def format_dep_of(req_parts: Iterable[str], opt_parts: Iterable[str]) -> str:
    """format the `Dependency Of` column to include the required and optional dependencies"""
    dep_of_parts = [f"req({' '.join(req_parts)})"] if req_parts else []
    if opt_parts:
        dep_of_parts.append(f"opt({' '.join(opt_parts)})")
    return ",".join(dep_of_parts)


def process() -> None:
    """process grep-status output on stdin to create fields separated by a given separator"""
    sep = parse_separator()
    current_pkg = ""
    desc: list[str] = []  # description can be multiline so accumulate it
    # map of package name to version and description; required and optional dependencies
    # have be to looked up in the respective maps using the dependency name so need to build
    # the full pkg_map first
    pkg_map: defaultdict[str, list[str]] = defaultdict(lambda: ["", ""])
    # reverse map of package to list of packages that require it (in their pre-depends or depends)
    req_map: defaultdict[str, list[str]] = defaultdict(list[str])
    # reverse map of package to list of packages that require it (in their recommends or suggests)
    opt_map: defaultdict[str, list[str]] = defaultdict(list[str])
    # map of package name to list of packages it provides (the reverse maps above can have
    #  either the dependency as the key or one of its provides as the key)
    provides: defaultdict[str, list[str]] = defaultdict(list[str])

    for line in sys.stdin:
        if (match := _VAL_RE.fullmatch(line)):
            key, value = match.groups()
            if key == "Package":
                if current_pkg:
                    # indicates start of fields of a new package, so fill in description and clear
                    pkg_map[current_pkg][1] = "".join(desc)
                    desc.clear()
                current_pkg = value
            elif key == "Version":
                pkg_map[current_pkg][0] = value
            elif key == "Provides":
                for match in _DEP_RE.finditer(value):
                    provides[current_pkg].append(match.group(1))
            # this does not take care of version comparisons in the dependencies but it should
            # not be possible for an installed package to fail version dependency check (assuming
            #   the packages are not broken), while virtual packages don't have versions
            elif key in ("Pre-Depends", "Depends"):
                # fill in reverse mapping of required dependencies
                for match in _DEP_RE.finditer(value):
                    req_map[match.group(1)].append(current_pkg)
            elif key in ("Recommends", "Suggests"):
                # fill in reverse mapping of optional dependencies
                for match in _DEP_RE.finditer(value):
                    opt_map[match.group(1)].append(current_pkg)
            elif key == "Description":
                desc.append(value)
                desc.append(r"\n")  # literal \n will be replaced by newline in the table display
        elif line and not line.isspace():
            if _DOT_LINE.fullmatch(line):
                desc.append(r"\n")
            else:
                if desc and desc[-1] != r"\n":
                    desc.append(" ")
                desc.append(line.strip())
    # fill description of the last package
    if current_pkg and desc:
        pkg_map[current_pkg][1] = "".join(desc)

    # for each package in pkg_map, find the packages that require it by looking up the
    # req_map and opt_map reverse maps; it also need to check all entries in the provides
    # map to get the full list of packages that require the dependency
    for pkg_name, (version, description) in pkg_map.items():
        req_parts = set[str]()
        opt_parts = set[str]()
        for dep_name in (pkg_name, *provides.get(pkg_name, [])):
            if req_pkg := req_map.get(dep_name):
                req_parts.update(req_pkg)
            if opt_pkg := opt_map.get(dep_name):
                opt_parts.update(opt_pkg)
        dep_of = format_dep_of(req_parts, opt_parts)
        print(f"{pkg_name}{sep}{version}{sep}{dep_of}{sep}{description}")


if __name__ == "__main__":
    process()
