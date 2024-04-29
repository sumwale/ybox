import re
import sys

from zbox.util import fgcolor

fg_name = fgcolor.lightgray
fg_ver = fgcolor.orange
fg_req = fgcolor.purple
fg_opt = fgcolor.cyan
fg_none = fgcolor.reset
__VAL_RE = re.compile(r"^\s*[^:]*:\s*")
name = version = req_by = ""

print(f"{fg_name}Name = {fg_ver}Version, {fg_req}Required By, {fg_opt}Optional For{fg_none}\n")
for line in sys.stdin:
    if line.startswith("Name"):
        name = __VAL_RE.sub("", line).rstrip()
    elif line.startswith("Version"):
        version = __VAL_RE.sub("", line).rstrip()
    elif line.startswith("Required By"):
        req_by = __VAL_RE.sub("", line).rstrip()
    elif line.startswith("Optional For"):
        opt_for = __VAL_RE.sub("", line).rstrip()
        sys.stdout.write(f"{fg_name}{name} = {fg_ver}{version}")
        if req_by != "None":
            if len(req_by) > 30:
                req_by = req_by[:30] + " ..."
            sys.stdout.write(f", {fg_req}{req_by}")
        if opt_for != "None":
            if len(opt_for) > 30:
                opt_for = opt_for[:30] + " ..."
            sys.stdout.write(f", {fg_opt}{opt_for}")
        sys.stdout.write(f"{fg_none}\n")
