"""
Migrate from 0.9.1 upwards to 0.9.7 that requires copying updated scripts to the container.

Invoke this script using `exec` passing the `StaticConfiguration` object as `conf` local variable
and parsed distribution configuration `ConfigParser` object as `distro_config` local variable.
"""

from ybox.util import copy_ybox_scripts_to_container

# the two variables below should be passed as local variables to `exec`
copy_ybox_scripts_to_container(conf, distro_config)  # type: ignore # noqa: F821
