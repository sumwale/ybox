import os
import re
import shutil
import sys

from tabulate import tabulate

from zbox.util import fgcolor

fg_name = fgcolor.lightgray
fg_ver = fgcolor.orange
fg_req = fgcolor.purple
fg_opt = fgcolor.cyan
fg_none = fgcolor.reset

__VAL_RE = re.compile(r"^\s*[^:]*:\s*")
__WS_RE = re.compile(r"\s\s+")

name = version = req_by = ""

# Adjust column widths as per the terminal width.
# Use stderr for the terminal width, since stdout is piped to pager.
try:
    terminal_width = os.get_terminal_size(sys.stderr.fileno()).columns
except OSError:
    terminal_width = shutil.get_terminal_size().columns
available_width = terminal_width - 12  # -12 is for the borders and padding

# using ratio of 4:4:6:5 for the four columns
nv_width = int(available_width * 4 / 19)
req_width = int(available_width * 6 / 19)
opt_width = int(available_width * 5 / 19)

table: list[(str, str, str, str)] = []
for line in sys.stdin:
    if line.startswith("Name"):
        name = __VAL_RE.sub("", line).rstrip()
    elif line.startswith("Version"):
        version = __VAL_RE.sub("", line).rstrip()
    elif line.startswith("Required By"):
        req_by = __VAL_RE.sub("", line).rstrip()
    elif line.startswith("Optional For"):
        opt_for = __VAL_RE.sub("", line).rstrip()
        if req_by != "None":
            req_by = __WS_RE.sub(" ", req_by)
            if len(req_by) > req_width:
                req_by = req_by[:req_width - 4] + " ..."
        else:
            req_by = ""
        if opt_for != "None":
            opt_for = __WS_RE.sub(" ", opt_for)
            if len(opt_for) > opt_width:
                opt_for = opt_for[:opt_width - 4] + " ..."
        else:
            opt_for = ""
        table.append((f"{fg_name}{name}{fg_none}", f"{fg_ver}{version}{fg_none}",
                      f"{fg_req}{req_by}{fg_none}", f"{fg_opt}{opt_for}{fg_none}"))

print(tabulate(table, headers=(f"{fg_name}Name{fg_none}", f"{fg_ver}Version{fg_none}",
                               f"{fg_req}Required By{fg_none}", f"{fg_opt}Optional For{fg_none}"),
               tablefmt="psql", maxcolwidths=[nv_width, nv_width, None, None]))
