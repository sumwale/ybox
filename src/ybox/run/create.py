import argparse
import getpass
import grp
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import time
from collections import defaultdict
from configparser import ConfigParser, SectionProxy
from importlib.resources import files
from pathlib import Path
from textwrap import dedent
from typing import Optional, Tuple

from ybox.cmd import PkgMgr, YboxLabel, get_docker_command, run_command, verify_ybox_state
from ybox.config import Consts, StaticConfiguration
from ybox.env import Environ, PathName
from ybox.filelock import FileLock
from ybox.pkg.inst import install_package, wrap_container_files
from ybox.print import bgcolor, fgcolor, print_color, print_error, print_info, print_warn
from ybox.run.pkg import parse_args as pkg_parse_args
from ybox.state import RuntimeConfiguration, YboxStateManagement
from ybox.util import EnvInterpolation, NotSupportedError, config_reader, ini_file_reader, \
    select_item_from_menu

# TODO: change double underscore to single everywhere

__EXTRACT_PARENS_NAME = re.compile(r"^.*\(([^)]+)\)$")
__DEP_SUFFIX = re.compile(r"^(.*):dep\((.*)\)$")


# Note: deliberately not using os.path.join for joining paths since the code only works on
# Linux/POSIX systems where path separator will always be "/" and explicitly forcing the same.
#
# Configuration files should be in $HOME/.config/ybox or ybox package directory.

def main() -> None:
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    args = parse_args(argv)
    env = Environ()

    # use provided distribution else let user select from available ones
    distro = select_distribution(args, env)
    # the profile used to build the docker/podman command-line which is either provided
    # on command-line or else let user select from available ones in standard locations
    profile = select_profile(args, env)

    box_name, docker_cmd = process_args(args, distro, profile)
    print_color(f"Creating ybox container named '{box_name}'", fg=fgcolor.green)
    if verify_ybox_state(docker_cmd, box_name, [], exit_on_error=False):
        print_error(f"ybox container '{box_name}' already exists.")
        sys.exit(1)

    conf = StaticConfiguration(env, distro, box_name)
    # read the distribution specific configuration
    base_image_name, shared_root_dirs, distro_config = read_distribution_config(conf)
    # setup entrypoint and related scripts to share with the container on a mount point
    setup_ybox_scripts(conf, distro_config)

    docker_full_args = [docker_cmd, "run", "-itd", f"--name={box_name}"]
    # process the profile before any actions to ensure it is in proper shape
    shared_root, box_conf, apps_with_deps = process_sections(profile, conf, distro_config,
                                                             docker_full_args)
    current_user = getpass.getuser()

    # The sequence for container creation and run is thus:
    # 1) First start a basic container with the smallest upstream distro image (important to
    #    save space when 'base.shared_root' is true) with "entrypoint-base.sh" as the entrypoint
    #    script giving user/group arguments to be same as the user as on the host machine.
    # 2) Next do a docker/podman commit and save the stopped container as local image which
    #    will be used henceforth. The main point of doing #1 is to ensure that a sudo enabled
    #    user is available which matches the current host user so that "--userns" option
    #    will not try to remap the image that can substantially increase the size of image.
    #    Either way, the user created by "--userns" in the container does not have sudo
    #    permissions, so we temporarily need to run such a container as root user in any case.
    #    Hence, step 1 uses a cleaner and better option that also creates separate
    #    container-specific images that can be enhanced with more container-specific stuff
    #    later if required. Also change the USER and WORKDIR of the commit to point to the
    #    user added in step 1).
    # 3) Start up the saved image of step 2 and run the distro specific entrypoint script
    #    that will do basic configuration and package installation (e.g. git/neovim/... on arch)
    #    followed by the generic "entrypoint.sh" script which will create the configuration
    #    file links (from [configs] section), install required apps (from [apps] section),
    #    followed by invoking the startup scripts from the [startup] section.
    # 4) The container is now ready to use so 'ybox-cmd' will only do a docker/podman exec
    #    of /bin/bash to open a shell (or any given command).
    # 5) Mounts and environment variables are set up for step 3 which are automatically also
    #    available in step 4, and hence no special setup is required in step 4.
    #
    # If 'base.shared_root' is true, the above sequence has the following changes:
    # 1) First acquire a file/process lock so that no other container creation can interfere.
    # 2) Once the lock has been acquired, check if the shared container image already exists.
    #    If it does exist, then skip to step 7.
    # 3) If not, then start the basic container like in step 1) of previous sequence.
    # 4) Like step 2) of the previous sequence, commit the container but with a temporary name.
    # 5) Unlike step 3) of the previous sequence, do a temporary restart of the previous
    #    committed image with "--userns=keep-id" option, and then copy the shared root
    #    directories to the shared mount point. This copying cannot be done in step 4) above
    #    because the file permissions are different with and without the --userns option.
    # 6) Stop the container and commit the image again with the final shared image name.
    #    Delete the previous temporary image. Release the file lock acquired in step 1).
    # 7) Now start the shared image like in step 3) of the previous sequence but with the
    #    additional root directory mounts that were copied in step 5 above.
    # Finally, continue with step 4) onwards of previous sequence.

    # handle the shared_root case: acquire file lock and check if shared container image exists
    if shared_root:
        os.makedirs(os.path.dirname(conf.shared_root_host_dir), exist_ok=True)
        with FileLock(f"{conf.shared_root_host_dir}-image.lock"):
            # if image already exists, then skip the subsequent steps
            if subprocess.run([docker_cmd, "inspect", "--type=image",
                               "--format={{.Id}}", conf.box_image(True)], check=False,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode != 0:
                # run the "base" container with appropriate arguments for the current user to
                # the 'entrypoint-base.sh' script to create the user and group in the container
                run_base_container(base_image_name, current_user, docker_cmd, conf)
                # commit the stopped container with a temporary name, then remove the container
                tmp_image = f"{conf.box_image(False)}__ybox_tmp"
                commit_container(current_user, docker_cmd, tmp_image, conf)
                # start a container using the temporary image with "--userns" option to make
                # a copy of the container root directories to the shared location
                run_shared_copy_container(docker_cmd, tmp_image, shared_root_dirs, conf)
                # finally commit this container with the name of the shared image
                commit_container(current_user, docker_cmd, conf.box_image(True), conf)
                remove_image(docker_cmd, tmp_image)
    else:
        shared_root_dirs = ""
        # run the "base" container with appropriate arguments for the current user to the
        # 'entrypoint-base.sh' script to create the user and group in the container
        run_base_container(base_image_name, current_user, docker_cmd, conf)
        # commit the stopped container, remove it, then start new container with the
        # "--userns=keep-id" option for the required container state
        commit_container(current_user, docker_cmd, conf.box_image(False), conf)

    # there is one additional stop/start below because all packages are upgraded by the
    # entrypoint script to pick up any important fixes which can lead to system libraries
    # getting upgraded, so it's best to restart container for those to take effect properly

    # set up the final container with all the required arguments
    print_info(f"Initializing container for '{distro}' using '{profile}'")
    start_container(docker_full_args, current_user, shared_root_dirs, conf)
    print_info("Waiting for the container to initialize (see "
               f"'ybox-logs -f {box_name}' for detailed progress)")
    sys.stdout.flush()
    # wait for container to initialize while printing out its progress from conf.status_file
    wait_for_container(docker_cmd, conf)

    # remove distribution specific scripts and restart container the final time
    print_info(f"Restarting the final container '{box_name}'")
    for script in Consts.distribution_scripts():
        os.unlink(f"{conf.scripts_dir}/{script}")
    restart_container(docker_cmd, conf)
    print_info("Waiting for the container to be ready (see "
               f"'ybox-logs -f {box_name}' for detailed progress)")
    sys.stdout.flush()
    wait_for_container(docker_cmd, conf)

    # finally add the state and register the installed packages
    with YboxStateManagement(env) as state:
        shared_root_dir = conf.shared_root_host_dir if shared_root else ""
        owned_packages = state.register_container(box_name, distro, shared_root_dir, box_conf)
        # create wrappers for owned_packages
        pkgmgr = distro_config["pkgmgr"]
        list_cmd = pkgmgr[PkgMgr.LIST_FILES.value]
        for package, copy_type in owned_packages.items():
            wrap_container_files(package, copy_type, list_cmd, docker_cmd, conf, box_conf)
        if apps_with_deps:
            runtime_conf = RuntimeConfiguration(box_name, distro, shared_root_dir, box_conf)
            for app, deps in apps_with_deps.items():
                pkg_args = ["install", "-z", box_name, "-q", "-o", "-c"]
                if deps:
                    pkg_args.append("-w")
                    pkg_args.append(",".join(deps))
                pkg_args.append(app)
                parsed_args = pkg_parse_args(pkg_args)
                install_package(parsed_args, pkgmgr, docker_cmd, conf, runtime_conf, state)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="""Create a new ybox container for given Linux distribution and configured
                       with given file in INI format. It allows for set up of various aspects of
                       the ybox including support for X11, Wayland, audio, video acceleration,
                       NVIDIA, dbus among others. It also allows controlling various parameters
                       of the container including directories to be shared, logging etc.
                       See src/ybox/conf/profiles/basic.ini in the distribution for all available
                       options with examples and comments having the explanations.""")
    parser.add_argument("-n", "--name", type=str,
                        help="name of the ybox; default is ybox-<distribution>_<profile> "
                             "if not provided (removing the .ini suffix from <profile> file)")
    parser.add_argument("-d", "--docker-path", type=str,
                        help="path of docker/podman if not in /usr/bin")
    parser.add_argument("distribution", nargs="?", type=str,
                        help="short name of the distribution as listed in distros/supported.list "
                             "(either in ~/.config/ybox or package's ybox/conf); it is optional "
                             "and user is presented with selection menu if there are multiple "
                             "listed in the first supported.list file that is found")
    parser.add_argument("profile", nargs="?", type=str,
                        help="the profile defined in INI file to use for creating the ybox "
                             "(can be a relative or absolute path, or be in user or system "
                             "configuration directory which are $HOME/.config/ybox/profiles and "
                             "package's ybox/conf/profiles directory respectively); it is "
                             "optional and user is presented with a selection menu of the "
                             "available profiles in the user or system profiles directory "
                             "whichever is found (in that order)")
    return parser.parse_args(argv)


def quick_config_read(file: PathName) -> ConfigParser:
    """Quick read of an INI file without processing includes or any value interpolation"""
    with file.open("r", encoding="utf-8") as profile_fd:
        return ini_file_reader(profile_fd, None)


def select_distribution(args: argparse.Namespace, env: Environ) -> str:
    support_list = env.search_config_path("distros/supported.list")
    with support_list.open("r", encoding="utf-8") as supp_file:
        supported_distros = supp_file.read().splitlines()
    if distro := args.distribution:
        # check that the distribution is in supported.list
        if distro in supported_distros:
            return str(distro)
        raise NotSupportedError(f"Distribution '{distro}' not supported in {support_list}")
    if len(supported_distros) == 1:
        print_info(f"Using distribution '{supported_distros[0]}'")
        return supported_distros[0]

    # show a menu to choose from if the number of supported distributions exceeds 1
    distro_names: list[str] = []
    for distro in supported_distros:
        distro_config = quick_config_read(env.search_config_path(f"distros/{distro}/distro.ini"))
        distro_names.append(f"{distro_config['base']['name']} ({distro})")  # should always exist
    print_info("Please select the distribution to use for the container:", file=sys.stderr)
    if (distro_name := select_item_from_menu(distro_names)) is None:
        sys.exit(1)
    if match := __EXTRACT_PARENS_NAME.match(distro_name):
        return match.group(1)
    raise ValueError(f"Unexpected distribution name string: {distro_name}")


def select_profile(args: argparse.Namespace, env: Environ) -> PathName:
    # the profile used to build the docker/podman command-line
    if profile_arg := args.profile:
        if os.access(profile_arg, os.R_OK):
            return Path(profile_arg)
        return env.search_config_path(f"profiles/{profile_arg}")

    # search for available profiles in standard locations and provide a selection menu
    # for the user
    profile_names: list[str] = []
    profiles_dir = env.search_config_path("profiles")
    profiles = [file for file in profiles_dir.iterdir() if file.is_file()]
    if len(profiles) == 1:
        print_info(f"Using profile '{profiles[0]}'")
        return profiles[0]
    if len(profiles) == 0:
        print_error(f"No valid profile found in '{profiles_dir}'")
        sys.exit(1)

    profiles.sort(key=str)
    for profile in profiles:
        profile_config = quick_config_read(profile)
        profile_names.append(f"{profile_config['base']['name']} ({profile.name})")
    print_info("Please select the profile to use for the container:", file=sys.stderr)
    if (profile_name := select_item_from_menu(profile_names)) is None:
        sys.exit(1)
    if match := __EXTRACT_PARENS_NAME.match(profile_name):
        return profiles_dir.joinpath(match.group(1))
    raise ValueError(f"Unexpected profile name string: {profile_name}")


def process_args(args: argparse.Namespace, distro: str, profile: PathName) -> Tuple[str, str]:
    ini_suffix = ".ini"
    if args.name:
        box_name = args.name
    else:
        box_name = profile.name
        if box_name.endswith(ini_suffix):
            box_name = box_name[:-len(ini_suffix)]
        box_name = f"ybox-{distro}_{box_name}"

    # don't allow spaces or weird characters in the name
    if not re.match(r"^[\w\-]+$", box_name):
        print_error(f"Invalid container name '{box_name}' -- only alphanumeric, underscore and "
                    "hyphen characters are accepted")
        sys.exit(1)
    docker_cmd = get_docker_command(args, "-d")
    return box_name, docker_cmd


def process_sections(profile: PathName, conf: StaticConfiguration, distro_config: ConfigParser,
                     docker_args: list[str]) -> Tuple[bool, ConfigParser, dict[str, list[str]]]:
    # Read the config file, recursively reading the includes if present,
    # then replace the environment variables and the special ${NOW:...} from all values.
    # Skip environment variable substitution for the "configs" section since the values
    # there have to be written as is to 'config.list' file for the container (since the
    #   $HOME variable can be different inside the container).
    env_interpolation = EnvInterpolation(conf.env, ["configs"])
    config = config_reader(profile, env_interpolation)
    # shared_root is false by default
    shared_root = False
    # hard links are false by default
    config_hardlinks = False
    apps_with_deps: dict[str, list[str]] = {}
    # finally process all the sections and the keys forming the docker/podman command-line
    for section in config.sections():
        if section == "base":
            shared_root, config_hardlinks = process_base_section(
                config["base"], profile, conf.env, docker_args)
        elif section == "security":
            process_security_section(config["security"], profile, docker_args)
        elif section == "mounts":
            process_mounts_section(config["mounts"], docker_args)
        elif section == "env":
            process_env_section(config["env"], docker_args)
        elif section == "configs":
            process_configs_section(config["configs"], config_hardlinks, conf, docker_args)
        elif section == "apps":
            apps_with_deps = process_apps_section(config["apps"], conf, distro_config)
        elif section not in ("app_flags", "startup"):
            raise NotSupportedError(f"Unknown section [{section}] in '{profile}' "
                                    "or one of its includes")
    return shared_root, config, apps_with_deps


def process_base_section(base_section: SectionProxy, profile: PathName,
                         env: Environ, args: list[str]) -> Tuple[bool, bool]:
    # shared root is true by default
    shared_root = True
    # hard links are false by default
    config_hardlinks = False
    for key in base_section:
        if key == "home":
            source_home = base_section[key]
            # create the source directory if it does not exist
            os.makedirs(source_home, exist_ok=True)
            add_mount_option(args, source_home, env.target_home)
        elif key == "shared_root":
            shared_root = base_section.getboolean("shared_root")
        elif key == "config_hardlinks":
            config_hardlinks = base_section.getboolean("config_hardlinks")
        elif key == "x11":
            if base_section.getboolean("x11"):
                enable_x11(args)
        elif key == "wayland":
            if base_section.getboolean("wayland"):
                enable_wayland(args, env)
        elif key == "pulseaudio":
            if base_section.getboolean("pulseaudio"):
                enable_pulse(args, env)
        elif key == "dbus":
            if base_section.getboolean("dbus"):
                enable_dbus(args, base_section.getboolean("dbus_sys", fallback=False))
        elif key == "dri":
            if base_section.getboolean("dri"):
                args.append("--device=/dev/dri")
        elif key == "nvidia":
            if base_section.getboolean("nvidia"):
                args.append("--device=nvidia.com/gpu=all")
        elif key == "shm_size":
            shm_size = base_section["shm_size"]
            if shm_size:
                args.append(f"--shm-size={shm_size}")
        elif key == "pids_limit":
            pids_limit = base_section["pids_limit"]
            if pids_limit:
                args.append(f"--pids-limit={pids_limit}")
        elif key == "log_driver":
            log_driver = base_section["log_driver"]
            if log_driver:
                args.append(f"--log-driver={log_driver}")
        elif key == "log_opts":
            add_multi_opt(args, base_section, "log_opts", "log-opt")
            # create the log directory if required
            log_dirs = [mt.group(1) for mt in
                        (re.match("^--log-opt=path=(.*)/.*$", path) for path in args) if mt]
            for log_dir in log_dirs:
                os.makedirs(log_dir, exist_ok=True)
        elif key not in ("name", "dbus_sys", "includes"):
            raise NotSupportedError(f"Unknown key '{key}' in the [base] of {profile} "
                                    "or its includes")
    return shared_root, config_hardlinks


def add_env_option(args: list[str], env_var: str, env_val: Optional[str] = None) -> None:
    if env_val is None:
        args.append(f"-e={env_var}")
    else:
        args.append(f"-e={env_var}={env_val}")


def add_mount_option(args: list[str], src: str, dest: str, flags: str = "") -> None:
    if flags:
        args.append(f"-v={src}:{dest}:{flags}")
    else:
        args.append(f"-v={src}:{dest}")


def enable_x11(args: list[str]) -> None:
    add_env_option(args, "DISPLAY")
    xsock = "/tmp/.X11-unix"
    if os.access(xsock, os.R_OK):
        add_mount_option(args, xsock, xsock, "ro")
    if xauth := os.environ.get("XAUTHORITY"):
        add_mount_option(args, xauth, xauth, "ro")
        add_env_option(args, "XAUTHORITY", xauth)


def enable_wayland(args: list[str], env: Environ) -> None:
    if wayland_display := os.environ.get("WAYLAND_DISPLAY"):
        add_env_option(args, "WAYLAND_DISPLAY", wayland_display)
        wayland_sock = f"{env.xdg_rt_dir}/{wayland_display}"
        if os.access(wayland_sock, os.W_OK):
            add_mount_option(args, wayland_sock, wayland_sock)


def enable_pulse(args: list[str], env: Environ) -> None:
    cookie = f"{env.home}/.config/pulse/cookie"
    if os.access(cookie, os.R_OK):
        add_mount_option(args, cookie, f"{env.target_home}/.config/pulse/cookie", "ro")
    if env.xdg_rt_dir:
        pulse_native = f"{env.xdg_rt_dir}/pulse/native"
        if os.access(pulse_native, os.W_OK):
            add_mount_option(args, pulse_native, pulse_native)
        for pwf in [f for f in os.listdir(env.xdg_rt_dir) if re.match("pipewire-[0-9]+$", f)]:
            pipewire_path = f"{env.xdg_rt_dir}/{pwf}"
            if os.access(pipewire_path, os.W_OK):
                add_mount_option(args, pipewire_path, pipewire_path)


def enable_dbus(args: list[str], sys_enable: bool) -> None:
    if dbus_session := os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        dbus_user = dbus_session[dbus_session.find("=") + 1:]
        if (dbus_opts_idx := dbus_user.find(",")) != -1:
            dbus_user = dbus_user[:dbus_opts_idx]
        add_mount_option(args, dbus_user, dbus_user)
        add_env_option(args, "DBUS_SESSION_BUS_ADDRESS", dbus_session)
    if sys_enable:
        dbus_sys = "/run/dbus/system_bus_socket"
        dbus_sys2 = "/var/run/dbus/system_bus_socket"
        if os.access(dbus_sys, os.W_OK):
            add_mount_option(args, dbus_sys, dbus_sys)
        elif os.access(dbus_sys2, os.W_OK):
            add_mount_option(args, dbus_sys2, dbus_sys)


def add_multi_opt(args: list[str], section: SectionProxy, key: str, opt: str) -> None:
    if opts := section.get(key):
        for opt_val in opts.split(","):
            args.append(f"--{opt}={opt_val}")


def process_security_section(sec_section: SectionProxy, profile: PathName,
                             args: list[str]) -> None:
    sec_options = ["label", "apparmor", "seccomp", "mask", "umask", "proc_opts"]
    single_options = ["seccomp_policy", "ipc", "cgroup_parent", "cgroupns", "cgroups"]
    multi_options = {"caps_add": "cap-add", "caps_drop": "cap-drop", "ulimits": "ulimit",
                     "cgroup_confs": "cgroup-conf", "device_cgroup_rules": "device-cgroup-rule",
                     "secrets": "secret"}
    for key in sec_section:
        if key in sec_options:
            add_sec_option_if_exists(args, sec_section, key.replace("_", "-"))
        elif opt := multi_options.get(key):
            add_multi_opt(args, sec_section, key, opt)
        elif key in single_options:
            add_option_if_exists(args, sec_section, key, key.replace("_", "-"))
        elif key == "no_new_privileges":
            if sec_section.getboolean(key):
                args.append("--security-opt=no-new-privileges")
        else:
            raise NotSupportedError(f"Unknown key '{key}' in the [security] of {profile} "
                                    "or its includes")


def add_sec_option_if_exists(args: list[str], sec_section: SectionProxy, key: str) -> None:
    if val := sec_section[key]:
        args.append(f"--security-opt={key}={val}")


def add_option_if_exists(args: list[str], section: SectionProxy, key: str, opt: str) -> None:
    if val := section[key]:
        args.append(f"--{opt}={val}")


def process_mounts_section(mounts_section: SectionProxy, args: list[str]) -> None:
    for key in mounts_section:
        # keys here are only symbolic names and serve no purpose other than allowing
        # later profile files to override previous ones
        if val := mounts_section[key]:
            if "=" in val or "," in val:
                args.append(f"--mount={val}")
            else:
                args.append(f"-v={val}")


def process_configs_section(configs_section: SectionProxy, config_hardlinks: bool,
                            conf: StaticConfiguration, args: list[str]) -> None:
    # copy or link the mentioned files in [configs] section which can be either files
    # or directories (recursively copy/link in the latter case)
    # this is refreshed on every container start

    # always recreate the directory to pick up any changes
    if os.path.exists(conf.configs_dir):
        shutil.rmtree(conf.configs_dir)
    os.makedirs(conf.configs_dir, exist_ok=True)
    if config_hardlinks:
        print_info("Creating hard links to paths specified in [configs]", end="  ...  ")
    else:
        print_info("Creating a copy of paths specified in [configs]", end="  ...  ")
    # write the links to be created in a file that will be passed to container
    # entrypoint to create symlinks from container user's home to the mounted config files
    with open(conf.config_list, "w", encoding="utf-8") as config_list_fd:
        for key in configs_section:
            val = configs_section[key]
            # perform environment variable substitution now which was skipped earlier
            f_val = os.path.expandvars(val)
            split_idx = f_val.find("->")
            if split_idx == -1:
                raise NotSupportedError("Incorrect value format in [configs] section for "
                                        f"'{key}'. Required: '{{src}} -> {{dest}}'")
            src_path = os.path.realpath(f_val[:split_idx].strip())
            dest_path = f"{conf.configs_dir}/{f_val[split_idx + 2:].strip()}"
            if os.access(src_path, os.R_OK):
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                if os.path.isdir(src_path):
                    copytree(src_path, dest_path, hardlink=config_hardlinks)
                else:
                    if config_hardlinks:
                        os.link(os.path.realpath(src_path), dest_path, follow_symlinks=True)
                    else:
                        shutil.copy2(src_path, dest_path, follow_symlinks=True)
                config_list_fd.write(val)
                config_list_fd.write("\n")
            else:
                print_warn(f"Skipping inaccessible configuration path '{src_path}'")
    print_info("DONE")
    # finally mount the configs directory to corresponding directory in the target container
    add_mount_option(args, conf.configs_dir, conf.target_configs_dir, "ro")


def process_env_section(env_section: SectionProxy, args: list[str]) -> None:
    for key in env_section:
        add_env_option(args, key, env_section[key])


def process_apps_section(apps_section: SectionProxy, conf: StaticConfiguration,
                         distro_config: ConfigParser) -> dict[str, list[str]]:
    if len(apps_section) == 0:
        return {}
    pkgmgr = distro_config["pkgmgr"]
    quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value]
    opt_dep_flag = pkgmgr[PkgMgr.OPT_DEP_FLAG.value]
    install_cmd = pkgmgr[PkgMgr.INSTALL.value].format(quiet=quiet_flag, opt_dep="")
    cleanup_cmd = pkgmgr[PkgMgr.CLEANUP.value]
    if not install_cmd:
        print_color("Skipping app installation since no 'pkgmgr.install' has "
                    "been defined in distro.ini or is empty",
                    fg=fgcolor.lightgray, bg=bgcolor.red)
        return {}
    # write pkgmgr.conf for entrypoint.sh
    with open(f"{conf.scripts_dir}/pkgmgr.conf", "w", encoding="utf-8") as pkg_fd:
        pkg_fd.write(f"PKGMGR_INSTALL='{install_cmd}'\n")
        pkg_fd.write(f"PKGMGR_CLEANUP='{cleanup_cmd}'\n")
    apps_with_deps = defaultdict[str, list[str]](list[str])

    def capture_dep(match: re.Match) -> str:
        dep = match.group(1)
        apps_with_deps[match.group(2)].append(dep)
        return dep

    with open(conf.app_list, "w", encoding="utf-8") as apps_fd:
        for key in apps_section:
            apps = [app.strip() for app in apps_section[key].split(",")]
            deps = [capture_dep(match) for dep in apps if (match := __DEP_SUFFIX.match(dep))]
            if deps:
                apps = [app for app in apps if not __DEP_SUFFIX.match(app)]
                apps_fd.write(f"{opt_dep_flag} {' '.join(deps)}\n")
            if apps:
                apps_fd.write(f"{' '.join(apps)}\n")
                for app in apps:
                    assert apps_with_deps[app] is not None  # insert with empty list if absent
    return apps_with_deps


# The shutil.copytree(...) method does not work correctly for "symlinks=False" (or at least
#   not like 'cp -rL' or 'cp -rlL') where it does not create the source symlinked file rather
# only the target one in the destination directory.
# This is a simplified version using os.walk(...) that works correctly that always has:
#   a. follow_symlinks=True, and b. ignore_dangling_symlinks=True
def copytree(src: str, dest: str, hardlink: bool = False) -> None:
    for src_dir, _, src_files in os.walk(src, followlinks=True):
        # substitute 'src' prefix with 'dest'
        dest_dir = f"{dest}{src_dir[len(src):]}"
        os.mkdir(dest_dir)
        for src_file in src_files:
            src_path = f"{src_dir}/{src_file}"
            if os.path.exists(src_path):
                if hardlink:
                    os.link(os.path.realpath(src_path), f"{dest_dir}/{src_file}",
                            follow_symlinks=True)
                else:
                    shutil.copy2(src_path, f"{dest_dir}/{src_file}", follow_symlinks=True)


def copy_file(src: PathName, dest: str, permissions: Optional[int] = None) -> None:
    with open(dest, "w", encoding="utf-8") as dest_fd:
        dest_fd.write(src.read_text(encoding="utf-8"))
    if permissions is not None:
        os.chmod(dest, permissions)
    elif hasattr(src, "stat"):  # copy the permissions
        perms = stat.S_IMODE(src.stat(follow_symlinks=True).st_mode)
        os.chmod(dest, perms)


def setup_ybox_scripts(conf: StaticConfiguration, distro_config: ConfigParser) -> None:
    # first create local mount directory having entrypoint and other scripts
    if os.path.exists(conf.scripts_dir):
        shutil.rmtree(conf.scripts_dir)
    os.makedirs(conf.scripts_dir, exist_ok=True)
    env = conf.env
    # copy the common scripts
    for script in [Consts.entrypoint_common(), Consts.entrypoint_base(),
                   Consts.entrypoint_cp(), Consts.entrypoint(), "prime-run"]:
        path = env.search_config_path(f"resources/{script}")
        copy_file(path, f"{conf.scripts_dir}/{script}", permissions=0o750)
    # also copy distribution specific scripts
    for script in Consts.distribution_scripts():
        path = env.search_config_path(f"distros/{conf.distribution}/{script}")
        copy_file(path, f"{conf.scripts_dir}/{script}", permissions=0o750)
    base_section = distro_config["base"]
    if scripts := base_section.get("scripts"):
        for script in scripts.split(","):
            path = env.search_config_path(f"distros/{conf.distribution}/{script}")
            copy_file(path, f"{conf.scripts_dir}/{script}")
        # finally copy the ybox python module which may be used by distribution scripts
        src_dir = files("ybox")
        dest_dir = f"{conf.scripts_dir}/ybox"
        os.mkdir(dest_dir)
        for resource in src_dir.iterdir():
            if resource.is_file():
                copy_file(resource, f"{dest_dir}/{resource.name}")


def read_distribution_config(conf: StaticConfiguration) -> Tuple[str, str, ConfigParser]:
    env_interpolation = EnvInterpolation(conf.env, [])
    distro_config = config_reader(
        conf.env.search_config_path(f"distros/{conf.distribution}/distro.ini"), env_interpolation)
    distro_base_section = distro_config["base"]
    image_name = distro_base_section["image"]  # should always exist
    shared_root_dirs = distro_base_section["shared_root_dirs"]  # should always exist
    return image_name, shared_root_dirs, distro_config


def run_base_container(image_name: str, current_user: str, docker_cmd: str,
                       conf: StaticConfiguration) -> None:
    # refresh the image locally first to decrease update size later
    print_info(f"Refreshing local copy of the base image '{image_name}'")
    if run_command([docker_cmd, "pull", image_name], exit_on_error=False,
                   error_msg=f"pulling {image_name}") != 0:
        print_warn("Trying to continue with local copy of the image")
    # get current user and group details to pass to the entrypoint script
    user_entry = pwd.getpwnam(current_user)
    group_entry = grp.getgrgid(user_entry.pw_gid)
    print_warn(f"Creating container specific image having sudo user '{current_user}'")
    docker_run = [docker_cmd, "run", "-it", "-e=XDG_RUNTIME_DIR", f"--name={conf.box_name}",
                  f"-v={conf.scripts_dir}:{conf.target_scripts_dir}:ro",
                  f"--label={YboxLabel.CONTAINER_BASE}",
                  f"--entrypoint={conf.target_scripts_dir}/{Consts.entrypoint_base()}",
                  image_name, "-u", current_user, "-U", str(user_entry.pw_uid),
                  "-n", user_entry.pw_gecos, "-g", group_entry.gr_name,
                  "-G", str(group_entry.gr_gid)]
    if conf.localtime:
        docker_run.append("-l")
        docker_run.append(conf.localtime)
    if conf.timezone:
        docker_run.append("-z")
        docker_run.append(conf.timezone)
    run_command(docker_run, error_msg="running container with base image")


def run_shared_copy_container(docker_cmd: str, image_name: str, shared_root_dirs: str,
                              conf: StaticConfiguration) -> None:
    root_host = conf.shared_root_host_dir
    # if shared root copy exists locally, then prompt user to delete it or else exit
    if os.path.exists(root_host):
        input_msg = f"""
            The shared root directory for '{conf.distribution}' already exists in:
                {root_host}
            However, the corresponding ybox container image for '{conf.distribution}' does not
            exist. This can happen if an old copy of shared root directory is lying around and
            is usually safe to remove, but you should be sure that no other ybox is running
            for '{conf.distribution}' with 'shared_root' configuration that is using that
            directory. Should the root directory be removed (y/N): """
        response = input(dedent(input_msg))
        if response.lower() == "y":
            try:
                shutil.rmtree(root_host)
            except OSError:
                # try with sudo
                run_command(["sudo", "/bin/rm", "-rf", root_host], error_msg="deleting directory")
        else:
            print_error(f"Aborting creation of ybox container '{conf.box_name}'")
            # remove the temporary image before exit
            remove_image(docker_cmd, image_name)
            sys.exit(1)
    os.makedirs(root_host)
    # the entrypoint-cp.sh script requires two arguments: first is the comma separated
    # list of directories to be copied, and second the target directory
    run_command([docker_cmd, "run", "-it", f"--name={conf.box_name}",
                 f"-v={conf.scripts_dir}:{conf.target_scripts_dir}:ro",
                 f"-v={root_host}:{Consts.shared_root_mount_dir()}",
                 f"--label={YboxLabel.CONTAINER_COPY}", "--userns=keep-id", "--user=0",
                 f"--entrypoint={conf.target_scripts_dir}/{Consts.entrypoint_cp()}",
                 image_name, shared_root_dirs, Consts.shared_root_mount_dir()],
                error_msg="running container for copying shared root")


def commit_container(current_user: str, docker_cmd: str, box_image: str,
                     conf: StaticConfiguration) -> None:
    run_command([docker_cmd, "commit", f"-c=USER={current_user}",
                 f"-c=WORKDIR=/home/{current_user}", conf.box_name, box_image],
                error_msg="container commit")
    run_command([docker_cmd, "container", "rm", conf.box_name], error_msg="container rm")


def remove_image(docker_cmd: str, box_image: str) -> None:
    run_command([docker_cmd, "image", "rm", box_image], exit_on_error=False,
                error_msg="image remove")


def start_container(docker_full_cmd: list[str], current_user: str, shared_root_dirs: str,
                    conf: StaticConfiguration) -> None:
    add_mount_option(docker_full_cmd, conf.scripts_dir, conf.target_scripts_dir, "ro")
    # touch the status file and mount it
    status_path = Path(conf.status_file)
    status_path.unlink(missing_ok=True)
    status_path.touch(mode=0o600, exist_ok=False)
    add_mount_option(docker_full_cmd, conf.status_file, Consts.status_target_file())

    for shared_dir in shared_root_dirs.split(","):
        add_mount_option(docker_full_cmd, f"{conf.shared_root_host_dir}{shared_dir}", shared_dir)
    for lang_var in ["LANG", "LANGUAGE"]:
        docker_full_cmd.append(f"-e={lang_var}")
    docker_full_cmd.append("-e=XDG_RUNTIME_DIR")
    docker_full_cmd.append(f"--label={YboxLabel.CONTAINER_PRIMARY}")
    docker_full_cmd.append(f"--label={YboxLabel.CONTAINER_DISTRIBUTION}={conf.distribution}")
    docker_full_cmd.append(f"--entrypoint={conf.target_scripts_dir}/{Consts.entrypoint()}")
    docker_full_cmd.append("--userns=keep-id")
    # bubblewrap and thereby programs like steam do not work without --user
    # (https://github.com/containers/bubblewrap/issues/380#issuecomment-648169485)
    user_entry = pwd.getpwnam(current_user)
    docker_full_cmd.append(f"--user={user_entry.pw_uid}")
    docker_full_cmd.append(conf.box_image(bool(shared_root_dirs)))
    if os.access(conf.config_list, os.R_OK):
        docker_full_cmd.extend(["-c", f"{conf.target_scripts_dir}/config.list",
                                "-d", conf.target_configs_dir])
    if os.access(conf.app_list, os.R_OK):
        docker_full_cmd.append("-a")
        docker_full_cmd.append(f"{conf.target_scripts_dir}/app.list")
    docker_full_cmd.append(conf.box_name)

    if (code := int(run_command(docker_full_cmd, exit_on_error=False,
                                error_msg="container launch"))) != 0:
        print_error(f"Also check 'ybox-logs {conf.box_name}' for details")
        sys.exit(code)


def wait_for_container(docker_cmd: str, conf: StaticConfiguration) -> None:
    box_name = conf.box_name
    max_wait_secs = 600
    status_line = ""  # keeps the last valid line read from status file
    with open(conf.status_file, "r", encoding="utf-8") as status_fd:
        for _ in range(max_wait_secs):
            # check the container status first
            if verify_ybox_state(docker_cmd, box_name, ["running"], exit_on_error=False):
                while status_line := status_fd.readline():
                    if status_line == "started\n":
                        # clear the status file and return
                        truncate_file(conf.status_file)
                        return
                    print(status_line, end="")  # line already includes the terminating newline
            else:
                # check if container has explicitly stopped for restart later
                while line := status_fd.readline():
                    status_line = line
                    print(line, end="")  # line already includes the terminating newline
                if status_line == "stopped\n":
                    # clear the status file and return
                    truncate_file(conf.status_file)
                    return
                print_error("FAILED waiting for container to be ready -- check "
                            f"'ybox-logs {box_name}' for details")
                sys.exit(1)
            # using simple poll per second rather than inotify or similar because the
            # initialization will take a good amount of time and second granularity is enough
            time.sleep(1)
    # reading did not end after max_wait_secs
    print_error(f"TIMED OUT waiting for ready container after {max_wait_secs}secs -- check "
                f"'ybox-logs -f {box_name}' for details")
    sys.exit(1)


def truncate_file(file: str) -> None:
    with open(file, "a", encoding="utf-8") as file_fd:
        file_fd.truncate(0)


def restart_container(docker_cmd: str, conf: StaticConfiguration) -> None:
    if (code := int(run_command([docker_cmd, "container", "start", conf.box_name],
                                exit_on_error=False, error_msg="container restart"))) != 0:
        print_error("Also check 'ybox-logs {conf.box_name}' for details")
        sys.exit(code)
