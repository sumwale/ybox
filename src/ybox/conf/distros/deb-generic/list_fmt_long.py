"""
Format output of `dpkg-query -W -f '${binary:Package}<sep>${Version}<sep>${Provides}<sep>\
    ${Pre-Depends}<sep>${Depends}<sep>${Recommends}<sep>${Suggests}<sep>${Description}\n\n'`
into four columns ${binary:Package}<sep>${Version}<sep>${Dependency Of}<sep>${Description}
where <sep> is a user provided separator.
"""

import argparse
import re
import sys
from collections import defaultdict
from typing import Iterable

from pkgdeps import PKG_DEP_RE  # pylint: disable=no-name-in-module

_DOT_LINE = re.compile(r"\s+\.\s*")


def parse_separator():
    """expect a single argument which will be used as the separator between the fields"""
    parser = argparse.ArgumentParser(description="Format output of dpkg-query into a table.")
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
    """process dpkg-query output on stdin to create fields separated by a given separator"""
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
    provides_map: defaultdict[str, list[str]] = defaultdict(list[str])

    for line in sys.stdin:
        if not line:
            continue
        if line[0].isspace():
            # continuation of the previous description
            if _DOT_LINE.fullmatch(line):
                desc.append(r"\n")  # literal \n will be replaced by newline in the table display
            else:
                # for simple line breaks in the description, it is just a continuation and can be
                # appended with a space, but for the case of `_DOT_LINE` as well as the first
                # description line and details later, it constitutes a new paragraph which are
                # separated by a literal \n
                if desc and desc[-1] != r"\n":
                    desc.append(" ")
                desc.append(line.strip())
        else:
            if current_pkg:
                # indicates start of fields of a new package, so fill in description and clear
                pkg_map[current_pkg][1] = "".join(desc)
                desc.clear()
            current_pkg, version, provides, pre_depends, depends, recommends, suggests, desc_s = \
                line.split(sep, maxsplit=7)
            pkg_map[current_pkg][0] = version
            # Iterate Provides, Pre-Depends, Depends, Recommends, Suggests to fill in their maps.
            # This does not take care of version comparisons in the dependencies but it should
            # not be possible for an installed package to fail version dependency check (assuming
            #   the packages are not broken), while virtual packages don't have versions
            for match in PKG_DEP_RE.finditer(provides):
                provides_map[current_pkg].append(match.group(1))
            # fill in reverse mapping of required dependencies
            for match in PKG_DEP_RE.finditer(pre_depends):
                req_map[match.group(1)].append(current_pkg)
            for match in PKG_DEP_RE.finditer(depends):
                req_map[match.group(1)].append(current_pkg)
            # fill in reverse mapping of optional dependencies
            for match in PKG_DEP_RE.finditer(recommends):
                opt_map[match.group(1)].append(current_pkg)
            for match in PKG_DEP_RE.finditer(suggests):
                opt_map[match.group(1)].append(current_pkg)
            desc.append(desc_s.rstrip())
            desc.append(r"\n")  # literal \n will be replaced by newline in the table display
    # fill description of the last package
    if current_pkg and desc:
        pkg_map[current_pkg][1] = "".join(desc)

    # for each package in pkg_map, find the packages that require it by looking up the
    # req_map and opt_map reverse maps; it also need to check all entries in the provides
    # map to get the full list of packages that require the dependency
    for pkg_name, (version, description) in pkg_map.items():
        req_parts = set[str]()
        opt_parts = set[str]()
        for dep_name in (pkg_name, *provides_map.get(pkg_name, [])):
            if req_pkg := req_map.get(dep_name):
                req_parts.update(req_pkg)
            if opt_pkg := opt_map.get(dep_name):
                opt_parts.update(opt_pkg)
        dep_of = format_dep_of(req_parts, opt_parts)
        print(f"{pkg_name}{sep}{version}{sep}{dep_of}{sep}{description}")


if __name__ == "__main__":
    process()
