"""
Migrate from 0.9.1 upwards to 0.9.7 that requires copying updated scripts to the container.

Invoke this script using `exec` passing the `StaticConfiguration` object as `conf` local variable
and parsed distribution configuration `ConfigParser` object as `distro_config` local variable.
"""

from pathlib import Path

from ybox.config import Consts
from ybox.util import copy_ybox_scripts_to_container

# the two variables below should be passed as local variables to `exec`
copy_ybox_scripts_to_container(conf, distro_config)  # type: ignore # noqa: F821

# rename PKGMGR_CLEANUP to PKGMGR_CLEAN in pkgmgr.conf
scripts_dir: str = conf.scripts_dir  # type: ignore # noqa: F821
pkgmgr_conf = f"{scripts_dir}/pkgmgr.conf"
with open(pkgmgr_conf, "r", encoding="utf-8") as pkgmgr_file:
    pkgmgr_data = pkgmgr_file.read()
with open(pkgmgr_conf, "w", encoding="utf-8") as pkgmgr_file:
    pkgmgr_file.write(pkgmgr_data.replace("PKGMGR_CLEANUP", "PKGMGR_CLEAN"))

# touch the file that indiates that first run initialization of entrypoint.sh is complete
Path(f"{scripts_dir}/{Consts.entrypoint_init_done_file()}").touch(mode=0o640)
