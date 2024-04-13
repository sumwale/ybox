#!/usr/bin/python3

import os
import sys
import argparse
import time

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(script_dir))

from configparser import SectionProxy
from typeguard import typechecked
from zbox.util import *

# add user and group as per the provided options
parser = argparse.ArgumentParser()
parser.add_argument("--user", type=str, help="login of the user to add", default="zbox")
parser.add_argument("--uid", type=int, help="UID of the user", default=1000)
parser.add_argument("--fullname", type=str, help="full name of the user", default="zbox")
parser.add_argument("--group", type=str, help="primary group of the user to add",
        default="zbox")
parser.add_argument("--gid", type=int, help="GID of the primary group of the user",
        default=1000)
parser.add_argument("--config", type=str,
        help="zbox configuration file to be used for initialization")
args = parser.parse_args()

user = args.user
uid = args.uid
fullname = args.fullname
group = args.group
gid = args.gid
config_file = args.config

# add the user with the same UID/GID as provided which should normally be the same as the
# user running this zbox (which avoids --userns=keep-id from increasing the image size
#   else the image size gets nearly doubled)
os.system("dbus-uuidgen --ensure=/etc/machine-id")
os.system(f"groupadd -g {gid} {group}")
print(fgcolor.blue, f"Added group '{group}'", sep="")
os.system(f"useradd -m -g {group} -G wheel,nobody,video,lp,mail,realtime -u {uid} "
          f"-d /home/{user} -s /bin/bash -c '{fullname}' {user}")
os.system(f"usermod --lock {user}")
sudoers_file = f"/etc/sudoers.d/{user}"
with open(sudoers_file, "w") as sudoers:
    sudoers.write(f"{user} ALL=(ALL:ALL) NOPASSWD: ALL")
os.chmod(sudoers_file, 0o440)
print(fgcolor.purple, f"Added admin user '{user}' to sudoers with NOPASSWD", sep="")

# change ownership of user's /run/user/<uid> tree which may have root ownership due to the
# docker bind mounts
run_dir = f"/run/user/{uid}"
os.makedirs(run_dir, exist_ok=True)
os.chmod(run_dir, 0o700)
os.system(f"chown -Rf {uid}:{gid} {run_dir}")
print(fgcolor.blue, f"Created run directory for '{user}' with proper permissions",
      fgcolor.reset, sep="")

@typechecked
def process_configs_section(configs_section: SectionProxy) -> None:
    print(bgcolor.red, "NOT DONE", bgcolor.reset)

@typechecked
def process_apps_section(apps_section: SectionProxy) -> None:
    # first update the mirrors
    pkgmgr = config["pkgmgr"]
    if (mirror_cmd := pkgmgr.get("mirrors")):
        print(fgcolor.blue, f"Updating mirrors: {mirror_cmd}", end="  ...", sep="")
        os.system(mirror_cmd)
        print(fgcolor.green, "  [DONE]", sep="")
    if (install_cmd := pkgmgr.get("install")):
        extra_args = "extra-args="
        for key in apps_section:
            arg_msg = ""
            apps = apps_section[key].split(";")
            if (args := [a[len(extra_args):] for a in apps if a.startswith(extra_args)]):
                args = " ".join(args)
                arg_msg = f" with args '{args}'"
                apps = [app for app in apps if not app.startswith(extra_args)]
            print(fgcolor.blue, f"Installing group '{key}'{arg_msg}: {apps}", sep="")
            os.system(f"{install_cmd} {args} {' '.join(apps)}")
            print(fgcolor.green, "[DONE]", fgcolor.reset, sep="")
    else:
        print(bgcolor.red, fgcolor.bold, fgcolor.lightgray,
                "Skipping app installation since no 'pkgmgr.install' has "
                "been defined in distro.ini or is empty", fgcolor.reset, sep="")

@typechecked
def process_startup_section(startup_section: SectionProxy) -> None:
    print(bgcolor.red, "NOT DONE", bgcolor.reset)

# read the config file and apply the settings (the [configs], [apps] and [startup] sections)
if config_file and (config := config_postprocess(config_reader(config_file))):
    if "configs" in config:
        process_configs_section(config["configs"])
    if "apps" in config:
        process_apps_section(config["apps"])
    if "startup" in config:
        process_startup_section(config["startup"])
