"""
Migrate from 0.9.0 upwards to 0.9.7 that requires copying updated scripts to the container.

Invoke this script using `exec` passing the `StaticConfiguration` object as `conf` local variable
and parsed distribution configuration `ConfigParser` object as `distro_config` local variable.
"""

import subprocess
from configparser import ConfigParser
from pathlib import Path
from typing import cast

from ybox.config import Consts, StaticConfiguration
from ybox.util import copy_ybox_scripts_to_container

# the two variables below should be passed as local variables to `exec`
static_conf = cast(StaticConfiguration, conf)  # type: ignore # noqa: F821
distro_conf = cast(ConfigParser, distro_config)  # type: ignore # noqa: F821
copy_ybox_scripts_to_container(static_conf, distro_conf)

# rename PKGMGR_CLEANUP to PKGMGR_CLEAN in pkgmgr.conf
scripts_dir = static_conf.scripts_dir
pkgmgr_conf = Path(f"{scripts_dir}/pkgmgr.conf")
if pkgmgr_conf.exists():
    with pkgmgr_conf.open("r", encoding="utf-8") as pkgmgr_file:
        pkgmgr_data = pkgmgr_file.read()
    with pkgmgr_conf.open("w", encoding="utf-8") as pkgmgr_file:
        pkgmgr_file.write(pkgmgr_data.replace("PKGMGR_CLEANUP", "PKGMGR_CLEAN"))
# run entrypoint-root.sh again to refresh scripts and configuration
subprocess.run([static_conf.env.docker_cmd, "exec", "-it", static_conf.box_name, "/usr/bin/sudo",
                "/bin/bash", f"{static_conf.target_scripts_dir}/entrypoint-root.sh"])

# touch the file to indicate that first run initialization of entrypoint.sh is complete
Path(f"{scripts_dir}/{Consts.entrypoint_init_done_file()}").touch(mode=0o644)
