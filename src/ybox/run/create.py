"""
Code for the `ybox-create` script that is used to create and configure a new ybox container.
"""

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
from collections import defaultdict
from configparser import ConfigParser, SectionProxy
from pathlib import Path
from textwrap import dedent
from typing import Optional

from ybox.cmd import PkgMgr, RepoCmd, YboxLabel, check_ybox_exists, run_command
from ybox.config import Consts, StaticConfiguration
from ybox.env import Environ, NotSupportedError, PathName
from ybox.filelock import FileLock
from ybox.pkg.inst import install_package, wrap_container_files
from ybox.print import (bgcolor, fgcolor, print_color, print_error, print_info,
                        print_warn)
from ybox.run.graphics import (add_env_option, add_mount_option, enable_dri,
                               enable_nvidia, enable_wayland, enable_x11)
from ybox.run.pkg import parse_args as pkg_parse_args
from ybox.state import RuntimeConfiguration, YboxStateManagement
from ybox.util import (EnvInterpolation, config_reader,
                       copy_ybox_scripts_to_container, ini_file_reader,
                       select_item_from_menu, truncate_file,
                       wait_for_ybox_container, write_ybox_version)

_EXTRACT_PARENS_NAME = re.compile(r"^.*\(([^)]+)\)$")
_DEP_SUFFIX = re.compile(r"^(.*):dep\((.*)\)$")
_WS_RE = re.compile(r"\s+")


# Note: deliberately not using os.path.join for joining paths since the code only works on
# Linux/POSIX systems where path separator will always be "/" and explicitly forcing the same.
#
# Configuration files should be in $HOME/.config/ybox or ybox package installation directory.

def main() -> None:
    """main function for `ybox-create` script"""
    main_argv(sys.argv[1:])


def main_argv(argv: list[str]) -> None:
    """
    Main entrypoint of `ybox-create` that takes a list of arguments which are usually the
    command-line arguments of the `main()` function. Pass ["-h"]/["--help"] to see all the
    available arguments with help message for each.

    :param argv: arguments to the function (main function passes `sys.argv[1:]`)
    """
    args = parse_args(argv)
    env = Environ()
    docker_cmd = env.docker_cmd

    # use provided distribution else let user select from available ones
    distro = select_distribution(args, env)
    # the profile used to build the podman/docker command-line which is either provided
    # on command-line or else let user select from available ones in standard locations
    profile = select_profile(args, env)

    box_name = process_args(args, distro, profile)
    print_color(f"Creating ybox container named '{box_name}' for distribution '{distro}' "
                f"using profile '{profile}'", fg=fgcolor.green)
    if check_ybox_exists(docker_cmd, box_name):
        print_error(f"ybox container '{box_name}' already exists.")
        sys.exit(1)

    conf = StaticConfiguration(env, distro, box_name)
    # read the distribution specific configuration
    base_image_name, shared_root_dirs, secondary_groups, distro_config = read_distribution_config(
        args, conf)
    # setup entrypoint and related scripts to share with the container on a mount point
    setup_ybox_scripts(conf, distro_config)

    docker_full_args = [docker_cmd, "run", "-itd", f"--name={box_name}"]
    # process the profile before any actions to ensure it is in proper shape
    pkgmgr = distro_config["pkgmgr"]
    shared_root, box_conf, apps_with_deps = process_sections(profile, conf, pkgmgr,
                                                             docker_full_args)
    process_distribution_config(distro_config, docker_full_args)
    current_user = getpass.getuser()

    # The sequence for container creation and run is thus:
    # 1) First start a basic container with the smallest upstream distro image (important to save
    #    space when `base.shared_root` is provided) with "entrypoint-base.sh" as the entrypoint
    #    script giving user/group arguments to be same as the user as on the host machine.
    # 2) Next do a podman/docker commit and save the stopped container as local image which
    #    will be used henceforth. The main point of doing #1 is to ensure that a sudo enabled
    #    user is available which matches the current host user so that "--userns" option
    #    will not try to remap the image that can substantially increase the size of image.
    #    Either way, the user created by "--userns" in the container does not have sudo
    #    permissions, so temporarily need to run such a container as root user in any case.
    #    Hence, step 1 uses a cleaner and better option that also creates separate
    #    container-specific images that can be enhanced with more container-specific stuff
    #    later if required. Also change the USER and WORKDIR of the commit to point to the
    #    user added in step 1).
    # 3) Start up the saved image of step 2 and run the distro specific entrypoint script
    #    that will do basic configuration and package installation (e.g. git/neovim/... on arch)
    #    followed by the generic "entrypoint.sh" script which will create the configuration
    #    file links (from [configs] section), install required apps (from [apps] section),
    #    followed by invoking the startup scripts from the [startup] section.
    # 4) The container is now ready to use so 'ybox-cmd' will only do a podman/docker exec
    #    of /bin/bash to open a shell (or any given command).
    # 5) Mounts and environment variables are set up for step 3 which are automatically also
    #    available in step 4, and hence no special setup is required in step 4.
    #
    # If `base.shared_root` is provided, the above sequence has the following changes:
    # 1) First acquire a file/process lock so that no other container creation can interfere.
    # 2) Once the lock has been acquired, check if the shared container image already exists.
    #    If it does exist, then skip to step 7.
    # 3) If not, then start the basic container like in step 1) of previous sequence.
    # 4) Like step 2) of the previous sequence, commit the container but with a temporary name.
    # 5) Unlike step 3) of the previous sequence, do a temporary restart of the previous
    #    committed image with "--userns=keep-id" option (podman), and then copy the shared root
    #    directories to the shared mount point. This copying cannot be done in step 4) above
    #    because the file permissions are different with and without the --userns option.
    #    For docker that does not support the "--userns=keep-id" option, the container image
    #    needs to be run as root user that maps to host's user.
    # 6) Stop the container and commit the image again with the final shared image name.
    #    Delete the previous temporary image. Release the file lock acquired in step 1).
    # 7) Now start the shared image like in step 3) of the previous sequence but with the
    #    additional root directory mounts that were copied in step 5 above.
    # Finally, continue with step 4) onwards of previous sequence.

    # handle the shared_root case: acquire file lock and check if shared container image exists
    if shared_root:
        os.makedirs(os.path.dirname(shared_root),
                    mode=Consts.default_directory_mode(), exist_ok=True)
        with FileLock(f"{shared_root}-image.lock"):
            # if image already exists, then skip the subsequent steps
            if subprocess.run([docker_cmd, "inspect", "--type=image",
                               "--format={{.Id}}", conf.box_image(True)], check=False,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode != 0:
                # run the "base" container with appropriate arguments for the current user to
                # the 'entrypoint-base.sh' script to create the user and group in the container
                run_base_container(base_image_name, current_user, secondary_groups, docker_cmd,
                                   conf)
                # commit the stopped container with a temporary name, then remove the container;
                # keeping a separate tmp_image helps reduce size of final image a bit because
                # this one is without --userns while the final shared image is with --userns
                tmp_image = f"{conf.box_image(False)}__ybox_tmp"
                commit_container(docker_cmd, tmp_image, conf)
                # start a container using the temporary image with "--userns" option to make
                # a copy of the container root directories to the shared location
                run_shared_copy_container(docker_cmd, tmp_image, shared_root, shared_root_dirs,
                                          conf, args.quiet)
                # finally commit this container with the name of the shared image
                commit_container(docker_cmd, conf.box_image(True), conf)
                remove_image(docker_cmd, tmp_image)
            # in case a shared root directory is not present but shared image is present,
            # need to run the container to copy to shared root
            elif any((not os.path.exists(f"{shared_root}{s_dir}") for s_dir in
                      shared_root_dirs.split(","))):
                run_shared_copy_container(docker_cmd, conf.box_image(True), shared_root,
                                          shared_root_dirs, conf, args.quiet)
                remove_container(docker_cmd, conf)
    else:
        # for no shared_root case, its best to refresh the local image
        run_command([docker_cmd, "pull", base_image_name],
                    error_msg="fetching container base image")
        # run the "base" container with appropriate arguments for the current user to the
        # 'entrypoint-base.sh' script to create the user and group in the container
        run_base_container(base_image_name, current_user, secondary_groups, docker_cmd, conf)
        # commit the stopped container, remove it, then start new container with the
        # "--userns=keep-id" option (podman) for the required container state
        commit_container(docker_cmd, conf.box_image(False), conf)

    # there is one additional stop/start below because all packages are upgraded by the
    # entrypoint script to pick up any important fixes which can lead to system libraries
    # getting upgraded, so it's best to restart container for those to take effect properly

    # set up the final container with all the required arguments
    print_info(f"Initializing container for '{distro}' using '{profile}'")
    start_container(docker_full_args, current_user, shared_root, shared_root_dirs, conf)
    print_info("Waiting for the container to initialize (see "
               f"'ybox-logs -f {box_name}' for detailed progress)")
    # wait for container to initialize while printing out its progress from conf.status_file
    wait_for_ybox_container(docker_cmd, conf)

    # remove distribution specific scripts and restart container the final time
    print_info(f"Restarting the final container '{box_name}'")
    Path(f"{conf.scripts_dir}/{Consts.entrypoint_init_done_file()}").touch(mode=0o644)
    restart_container(docker_cmd, conf)
    print_info("Waiting for the container to be ready (see "
               f"'ybox-logs -f {box_name}' for detailed progress)")
    wait_for_ybox_container(docker_cmd, conf)
    # truncate the app.list and config.list files so that those actions are skipped if the
    # container is restarted later
    if os.access(conf.app_list, os.W_OK):
        truncate_file(conf.app_list)
    if os.access(conf.config_list, os.W_OK):
        truncate_file(conf.config_list)

    # finally add the state and register the installed packages that were reassigned to this
    # container (because the previously destroyed one has the same configuration and shared root)
    with YboxStateManagement(env) as state:
        owned_packages = state.register_container(box_name, distro, shared_root, box_conf,
                                                  args.force_own_orphans)
        # create wrappers for owned_packages
        if owned_packages:
            list_cmd = pkgmgr[PkgMgr.LIST_FILES.value]
            for package, (copy_type, app_flags) in owned_packages.items():
                # skip packages already scheduled to be installed
                if package in apps_with_deps:
                    continue
                # skip all questions for -q/--quiet (equivalent to -qq to `ybox-pkg install`)
                quiet = 2 if args.quiet else 0
                # box_conf can be skipped in new state.db but not for pre 0.9.3 having empty flags
                if local_copies := wrap_container_files(package, copy_type, app_flags, list_cmd,
                                                        docker_cmd, conf, box_conf, shared_root,
                                                        quiet):
                    # register the package again with the local_copies (no change to package_deps)
                    state.register_package(box_name, package, local_copies, copy_type, app_flags,
                                           shared_root, dep_type=None, dep_of="")
        if apps_with_deps:
            runtime_conf = RuntimeConfiguration(box_name, distro, shared_root, box_conf)
            for app, deps in apps_with_deps.items():
                pkg_args = ["install", "-z", box_name, "-o", "-c"]
                if args.quiet:
                    pkg_args.append("-qq")
                if deps:
                    pkg_args.append("-w")
                    pkg_args.append(",".join(deps))
                pkg_args.append(app)
                parsed_args = pkg_parse_args(pkg_args)
                install_package(parsed_args, pkgmgr, docker_cmd, conf, runtime_conf, state)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse command-line arguments for the program and return the result :class:`argparse.Namespace`.

    :param argv: the list of arguments to be parsed
    :return: the result of parsing using the `argparse` library as a :class:`argparse.Namespace`
    """
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
    parser.add_argument("-F", "--force-own-orphans", action="store_true",
                        help="force ownership of orphan packages on the same shared root even "
                             "if container configuration does not match, meaning the packages "
                             "on the shared root directory that got orphaned due to their "
                             "owner container being destroyed will be assigned to this new "
                             "container regardless of the container configuration")
    parser.add_argument("-C", "--distribution-config", type=str,
                        help="path to distribution configuration file to use instead of the "
                             "`distro.ini` from user/system configuration paths")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="proceed without asking any questions using defaults where possible; "
                             "this should usually be used with explicit specification of "
                             "distribution and profile arguments else the operation will fail if "
                             "there more than one of them available")
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
    """
    Quickly read an INI file without processing `includes` or applying any value interpolation.

    :param file: a `Path` or resource file from importlib (`Traversable`) for the configuration
    :return: an object of :class:`ConfigParser` from parsing the configuration file
    """
    with file.open("r", encoding="utf-8") as profile_fd:
        return ini_file_reader(profile_fd, None)


def select_distribution(args: argparse.Namespace, env: Environ) -> str:
    """
    Interactively select a Linux distribution from a menu among the ones supported by this
    installation of ybox, or if there is only one supported distribution, then return its name.
    User can also provide one explicitly on the command-line which will be returned if valid.

    :param args: the parsed arguments passed to the invoking `ybox-create` script
    :param env: an instance of the current :class:`Environ`
    :raises ValueError: unexpected internal error in the name of the distribution
    :return: name of the selected or provided distribution
    """
    support_list = env.search_config_path("distros/supported.list", only_sys_conf=True)
    with support_list.open("r", encoding="utf-8") as supp_file:
        supported_distros = supp_file.read().splitlines()
    if distro := args.distribution:
        # check that the distribution is in supported.list
        if distro in supported_distros:
            return str(distro)
        print_error(f"Distribution '{distro}' not supported in {support_list}")
        sys.exit(1)
    if len(supported_distros) == 1:
        print_info(f"Using distribution '{supported_distros[0]}'")
        return supported_distros[0]
    if args.quiet:
        print_error(
            f"Expected one supported distribution but found: {', '.join(supported_distros)}")
        sys.exit(1)

    # show a menu to choose from if the number of supported distributions exceeds 1
    distro_names: list[str] = []
    for distro in supported_distros:
        distro_config = quick_config_read(env.search_config_path(
            StaticConfiguration.distribution_config(distro), only_sys_conf=True))
        distro_names.append(f"{distro_config['base']['name']} ({distro})")  # should always exist
    print_info("Please select the distribution to use for the container:", file=sys.stderr)
    if (distro_name := select_item_from_menu(distro_names)) is None:
        sys.exit(1)
    if match := _EXTRACT_PARENS_NAME.match(distro_name):
        return match.group(1)
    raise ValueError(f"Unexpected distribution name string: {distro_name}")


def select_profile(args: argparse.Namespace, env: Environ) -> PathName:
    """
    Interactively select a profile for ybox container to use for its setup from a menu among the
    ones provided by this installation of ybox, or those setup in user's configuration.
    If there is only one available profile, then return its name. User can also provide one
    explicitly on the command-line which will be returned if valid.

    :param args: the parsed arguments passed to the invoking `ybox-create` script
    :param env: an instance of the current :class:`Environ`
    :raises ValueError: unexpected internal error in the name of the profile
    :return: name of the selected or provided profile
    """
    # the profile used to build the podman/docker command-line
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
    if args.quiet:
        print_error(
            f"Expected one configured profile but found: {', '.join([p.name for p in profiles])}")
        sys.exit(1)

    for profile in profiles:
        profile_config = quick_config_read(profile)
        profile_names.append(f"{profile_config['base']['name']} ({profile.name})")
    print_info("Please select the profile to use for the container:", file=sys.stderr)
    if (profile_name := select_item_from_menu(profile_names)) is None:
        sys.exit(1)
    if match := _EXTRACT_PARENS_NAME.match(profile_name):
        return profiles_dir.joinpath(match.group(1))
    raise ValueError(f"Unexpected profile name string: {profile_name}")


def process_args(args: argparse.Namespace, distro: str, profile: PathName) -> str:
    """
    Initial processing of the provided command-line arguments to form the desired name of the
    ybox container.

    :param args: the parsed arguments passed to the invoking `ybox-create` script
    :param distro: the Linux distribution name returned by :func:`select_distribution` to use for
                   the ybox container
    :param profile: the profile file returned by :func:`select_profile` to use for ybox container
                    configuration as a `Path` or resource file from importlib (`Traversable`)
    :return: the ybox container name to use
    """
    ini_suffix = ".ini"
    if args.name:
        box_name = args.name
    else:
        def_name = profile.name
        if def_name.endswith(ini_suffix):
            def_name = def_name[:-len(ini_suffix)]
        def_name = f"ybox-{distro}_{def_name}"
        box_name = def_name if args.quiet else input(
            f"Name of the container to create (default: {def_name}): ").strip()
        if not box_name:
            box_name = def_name

    # don't allow spaces or weird characters in the name
    if not re.fullmatch(r"[\w.\-]+", box_name):
        print_error(f"Invalid container name '{box_name}' -- only alphanumeric, underscore and "
                    "hyphen characters are accepted")
        sys.exit(1)
    return box_name


def process_sections(profile: PathName, conf: StaticConfiguration, pkgmgr: SectionProxy,
                     docker_args: list[str]) -> tuple[str, ConfigParser, dict[str, list[str]]]:
    """
    Process all the sections in the given profile file to return a tuple having:
      * shared root to use for the container (if any)
      * :class:`ConfigParser` object from parsing the ini format profile, and
      * dictionary having the packages to be installed as specified in the `[apps]` section
        of the profile mapped to list of dependent packages for each application.

    :param profile: the profile file returned by :func:`select_profile` to use for ybox container
                    configuration as a `Path` or resource file from importlib (`Traversable`)
    :param conf: the :class:`StaticConfiguration` for the container
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_args: list of arguments to be provided to podman/docker command for creating the
                        final ybox container which is populated with required options as per
                        the configuration in the given profile
    :raises NotSupportedError: if there is an unknown section or key in the ini format profile
    :return: tuple of container's shared root, :class:`ConfigParser` object from parsing the
             profile, and dictionary of apps with dependencies to be installed in the container
             from the `[apps]` section of the profile
    """
    # Read the config file, recursively reading the includes if present,
    # then replace the environment variables and the special ${NOW:...} from all values.
    # Skip environment variable substitution for the "configs" section since the values
    # there have to be written as is to 'config.list' file for the container (since the
    #   $HOME variable can be different inside the container).
    env_interpolation = EnvInterpolation(conf.env, ["configs"])
    config = config_reader(profile, env_interpolation)
    # [base] section should always be present
    if not config.has_section("base"):
        raise NotSupportedError(f"Missing [base] section in profile '{profile}'")
    shared_root, config_hardlinks = process_base_section(config["base"], profile, conf,
                                                         docker_args)
    apps_with_deps: dict[str, list[str]] = {}
    # finally process all the sections and the keys forming the podman/docker command-line
    for section in config.sections():
        if section == "security":
            process_security_section(config["security"], profile, docker_args)
        elif section == "mounts":
            process_mounts_section(config["mounts"], docker_args)
        elif section == "env":
            process_env_section(config["env"], docker_args)
        elif section == "configs":
            if config_hardlinks is not None:
                process_configs_section(config["configs"], config_hardlinks, conf, docker_args)
        elif section == "apps":
            apps_with_deps = process_apps_section(config["apps"], conf, pkgmgr)
        elif section not in ("base", "app_flags", "startup"):
            raise NotSupportedError(f"Unknown section [{section}] in '{profile}' "
                                    "or one of its includes")
    return shared_root, config, apps_with_deps


def read_distribution_config(args: argparse.Namespace,
                             conf: StaticConfiguration) -> tuple[str, str, str, ConfigParser]:
    """
    Read and parse the Linux distribution's `distro.ini` file and return a tuple having:
      * the container image name
      * comma-separate list of directories shared if `shared_root` is provided for the container
      * secondary groups of the user, and
      * the result of parsing the `distro.ini` as an object of :class:`ConfigParser`.

    :param args: the parsed arguments passed to the invoking `ybox-create` script
    :param conf: the :class:`StaticConfiguration` for the container
    :return: a tuple of image name, shared root directories, secondary groups and an object of
             :class:`ConfigParser` for the `distro.ini`
    """
    env = conf.env
    env_interpolation = EnvInterpolation(env, [])
    distro_conf_file = args.distribution_config or conf.distribution_config(conf.distribution)
    distro_config = config_reader(env.search_config_path(
        distro_conf_file, only_sys_conf=True), env_interpolation)
    distro_base_section = distro_config["base"]
    image_name = distro_base_section["image"]  # should always exist
    shared_root_dirs = distro_base_section["shared_root_dirs"]  # should always exist
    secondary_groups = distro_base_section["secondary_groups"]  # should always exist
    return image_name, shared_root_dirs, secondary_groups, distro_config


def process_distribution_config(distro_config: ConfigParser, docker_args: list[str]) -> None:
    """
    Process the Linux distribution's `distro.ini` file and populate relevant podman/docker options
    in the given `docker_args` list.

    :param distro_config: an object of :class:`ConfigParser` from parsing the Linux
                          distribution's `distro.ini`
    :param docker_args: list of arguments to be provided to podman/docker command for creating the
                        final ybox container which is populated with required options
    """
    if distro_config.getboolean("base", "configure_fastest_mirrors", fallback=False):
        add_env_option(docker_args, "CONFIGURE_FASTEST_MIRRORS", "1")
    if distro_config.has_section("packages"):
        packages_section = distro_config["packages"]
        for key, env_var in (("required", "REQUIRED_PKGS"), ("recommended", "RECOMMENDED_PKGS"),
                             ("suggested", "SUGGESTED_PKGS"), ("required_deps", "REQUIRED_DEPS"),
                             ("recommended_deps", "RECOMMENDED_DEPS"),
                             ("suggested_deps", "SUGGESTED_DEPS"), ("extra", "EXTRA_PKGS")):
            if value := packages_section.get(key):
                add_env_option(docker_args, env_var, _WS_RE.sub(" ", value))
    key_server = distro_config.get("repo", RepoCmd.DEFAULT_GPG_KEY_SERVER.value,
                                   fallback=Consts.default_key_server())
    add_env_option(docker_args, "DEFAULT_GPG_KEY_SERVER", key_server)


def process_base_section(base_section: SectionProxy, profile: PathName, conf: StaticConfiguration,
                         docker_args: list[str]) -> tuple[str, Optional[bool]]:
    """
    Process the `[base]` section in the container profile to append required podman/docker
    options in the list that has been passed, and return a tuple having the shared root to use for
    the container (if any), and the value of `config_hardlinks` key in the section.

    :param base_section: an object of :class:`SectionProxy` from parsing the `[base]` section
    :param profile: the profile file returned by :func:`select_profile` to use for ybox container
                    configuration as a `Path` or resource file from importlib (`Traversable`)
    :param conf: the :class:`StaticConfiguration` for the container
    :param docker_args: list of podman/docker arguments to which required options as per the
                        configuration in the `[base]` section are appended
    :raises NotSupportedError: if there is an unknown key in the `[base]` section
    :return: tuple of container's shared root and the value of `config_hardlinks` key
    """
    env = conf.env
    # shared root is disabled by default
    shared_root = ""
    # hard links are false by default (value of None means skip the [configs] section entirely)
    config_hardlinks: Optional[bool] = False
    # configure locale by default
    config_locale = True
    # DRI will be force enabled if NVIDIA support is enabled
    dri = False
    # NVIDIA is disabled by default
    nvidia = False
    nvidia_ctk = False
    for key, val in base_section.items():
        if key == "home":
            if val:
                # create the source directory if it does not exist
                os.makedirs(val, mode=Consts.default_directory_mode(), exist_ok=True)
                add_mount_option(docker_args, val, env.target_home)
        elif key == "shared_root":
            shared_root = val or ""
        elif key == "config_hardlinks":
            if val:
                config_hardlinks = _get_boolean(val)
            else:
                config_hardlinks = None
        elif key == "config_locale":
            config_locale = _get_boolean(val)
        elif key == "x11":
            if _get_boolean(val):
                enable_x11(docker_args, env)
        elif key == "wayland":
            if _get_boolean(val):
                enable_wayland(docker_args, env)
        elif key == "pulseaudio":
            if _get_boolean(val):
                enable_pulse(docker_args, env)
        elif key == "dbus":
            if _get_boolean(val):
                enable_dbus(docker_args, base_section.getboolean("dbus_sys", fallback=False), env)
        elif key == "dri":
            dri = _get_boolean(val)
        elif key == "nvidia":
            nvidia = _get_boolean(val)
        elif key == "nvidia_ctk":
            nvidia_ctk = _get_boolean(val)
        elif key == "shm_size":
            if val:
                docker_args.append(f"--shm-size={val}")
        elif key == "pids_limit":
            if val:
                docker_args.append(f"--pids-limit={val}")
        elif key == "log_driver":
            if val:
                docker_args.append(f"--log-driver={val}")
        elif key == "log_opts":
            add_multi_opt(docker_args, "log-opt", val)
            # create the log directory if required
            log_dirs = [mt.group(1) for mt in
                        (re.match("^--log-opt=path=(.*)/.*$", path) for path in docker_args) if mt]
            for log_dir in log_dirs:
                os.makedirs(log_dir, mode=Consts.default_directory_mode(), exist_ok=True)
        elif key not in ("name", "dbus_sys", "includes"):
            raise NotSupportedError(f"Unknown key '{key}' in the [base] of {profile} "
                                    "or its includes")
    if config_locale:
        for lang_var in ("LANG", "LANGUAGE"):
            add_env_option(docker_args, lang_var)
    if dri or nvidia or nvidia_ctk:
        enable_dri(docker_args)
    if nvidia_ctk:  # takes precedence over "nvidia" option
        docker_args.append("--device=nvidia.com/gpu=all")
    elif nvidia:
        enable_nvidia(docker_args, conf)
    return shared_root, config_hardlinks


def _get_boolean(value: str) -> bool:
    """
    Convert a string to boolean else raise a `ValueError` if the value is not a boolean.
    Recognizes the following values and is case-insensitive: 0/1, false/true, no/yes, off/on.
    """
    if (result := ConfigParser.BOOLEAN_STATES.get(value.lower())) is not None:
        return result
    raise ValueError(f"Not a boolean: {value}")


def enable_pulse(docker_args: list[str], env: Environ) -> None:
    """
    Append options to podman/docker arguments to share host machine's pulse/pipewire audio server
    with the new ybox container.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    :param env: an instance of the current :class:`Environ`
    """
    cookie = f"{env.home}/.config/pulse/cookie"
    if os.access(cookie, os.R_OK):
        add_mount_option(docker_args, cookie, f"{env.target_home}/.config/pulse/cookie", "ro")
    if env.xdg_rt_dir:
        pulse_native = f"{env.xdg_rt_dir}/pulse/native"
        if os.access(pulse_native, os.W_OK):
            add_mount_option(docker_args, pulse_native, f"{env.target_xdg_rt_dir}/pulse/native")
        for pwf in [f for f in os.listdir(env.xdg_rt_dir) if re.match("pipewire-[0-9]+$", f)]:
            pipewire_path = f"{env.xdg_rt_dir}/{pwf}"
            if os.access(pipewire_path, os.W_OK):
                add_mount_option(docker_args, pipewire_path, f"{env.target_xdg_rt_dir}/{pwf}")


def enable_dbus(docker_args: list[str], sys_enable: bool, env: Environ) -> None:
    """
    Append options to podman/docker arguments to share host machine's dbus message bus
    with the new ybox container.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    :param sys_enable: if True then also share host machine's system dbus message bus in addition
                       to the user dbus message bus
    :param env: an instance of the current :class:`Environ`
    """
    def replace_target_dir(src: str) -> str:
        return src.replace(f"{env.xdg_rt_dir}/", f"{env.target_xdg_rt_dir}/")
    if dbus_session := os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        dbus_user = dbus_session[dbus_session.find("=") + 1:]
        if (dbus_opts_idx := dbus_user.find(",")) != -1:
            dbus_user = dbus_user[:dbus_opts_idx]
        add_mount_option(docker_args, dbus_user, replace_target_dir(dbus_user))
        add_env_option(docker_args, "DBUS_SESSION_BUS_ADDRESS", replace_target_dir(dbus_session))
    if sys_enable:
        dbus_sys = "/run/dbus/system_bus_socket"
        dbus_sys2 = "/var/run/dbus/system_bus_socket"
        if os.access(dbus_sys, os.W_OK):
            add_mount_option(docker_args, dbus_sys, dbus_sys)
        elif os.access(dbus_sys2, os.W_OK):
            add_mount_option(docker_args, dbus_sys2, dbus_sys)


def add_multi_opt(docker_args: list[str], opt: str, val: Optional[str]) -> None:
    """
    Append a comma-separated value in the profile as multiple options to podman/docker arguments.

    :param docker_args: list of podman/docker arguments to which the options have to be appended
    :param val: the comma-separated value
    :param opt: the option name which is added as `--{opt}=...` to podman/docker arguments
    """
    if val:
        for opt_val in val.split(","):
            docker_args.append(f"--{opt}={opt_val}")


def process_security_section(sec_section: SectionProxy, profile: PathName,
                             docker_args: list[str]) -> None:
    """
    Process the `[security]` section in the container profile to append required podman/docker
    options in the list that has been passed.

    :param sec_section: an object of :class:`SectionProxy` from parsing the `[security]` section
    :param profile: the profile file returned by :func:`select_profile` to use for ybox container
                    configuration as a `Path` or resource file from importlib (`Traversable`)
    :param docker_args: list of podman/docker arguments to which required options as per the
                        configuration in the `[security]` section are appended
    :raises NotSupportedError: if there is an unknown key in the `[security]` section
    """
    sec_options = {"label", "apparmor", "seccomp", "mask", "umask", "proc_opts"}
    single_options = {"seccomp_policy", "ipc", "cgroup_parent", "cgroupns", "cgroups"}
    multi_options = {"caps_add": "cap-add", "caps_drop": "cap-drop", "ulimits": "ulimit",
                     "cgroup_confs": "cgroup-conf", "device_cgroup_rules": "device-cgroup-rule",
                     "secrets": "secret"}
    for key, val in sec_section.items():
        if key in sec_options:
            if val:
                docker_args.append(f"--security-opt={key.replace('_', '-')}={val}")
        elif opt := multi_options.get(key):
            add_multi_opt(docker_args, opt, val)
        elif key in single_options:
            if val:
                docker_args.append(f"--{key.replace('_', '-')}={val}")
        elif key == "no_new_privileges":
            if _get_boolean(val):
                docker_args.append("--security-opt=no-new-privileges")
        else:
            raise NotSupportedError(f"Unknown key '{key}' in the [security] of {profile} "
                                    "or its includes")


def process_mounts_section(mounts_section: SectionProxy, docker_args: list[str]) -> None:
    """
    Process the `[mounts]` section in the container profile to append required podman/docker
    options in the list that has been passed.

    :param mounts_section: an object of :class:`SectionProxy` from parsing the `[mounts]` section
    :param docker_args: list of podman/docker arguments to which required options as per the
                        configuration in the `[mounts]` section are appended
    """
    # keys here are only symbolic names and serve no purpose other than allowing
    # later profile files to override previous ones
    for _, val in mounts_section.items():
        if val:
            if "=" in val or "," in val:
                docker_args.append(f"--mount={val}")
            else:
                docker_args.append(f"-v={val}")


def process_configs_section(configs_section: SectionProxy, config_hardlinks: bool,
                            conf: StaticConfiguration, docker_args: list[str]) -> None:
    """
    Process the `[configs]` section in the container profile to append required podman/docker
    options in the list that has been passed. This method also makes hard-links or copies of the
    configuration files in local user's ybox data directory to mount inside the ybox container so
    that the selected configuration files from host are available in the container.

    :param configs_section: an object of :class:`SectionProxy` from parsing the `[configs]` section
    :param config_hardlinks: the value of `config_hardlinks` key from the `[base]` section that
                             indicates whether the configuration files from host have to be made
                             available by creating hard-links to them or by making copies
    :param conf: the :class:`StaticConfiguration` for the container
    :param docker_args: list of podman/docker arguments to which required options as per the
                        configuration in the `[configs]` section are appended
    """
    # copy or link the mentioned files in [configs] section which can be either files
    # or directories (recursively copy/link in the latter case)
    # this is refreshed on every container start

    # always recreate the directory to pick up any changes
    if os.path.exists(conf.configs_dir):
        shutil.rmtree(conf.configs_dir)
    os.makedirs(conf.configs_dir, mode=Consts.default_directory_mode(), exist_ok=True)
    if config_hardlinks:
        print_info("Creating hard links to paths specified in [configs]  ...")
    else:
        print_info("Creating a copy of paths specified in [configs]  ...")
    # write the links to be created in a file that will be passed to container
    # entrypoint to create symlinks from container user's home to the mounted config files
    with open(conf.config_list, "w", encoding="utf-8") as config_list_fd:
        for key, val in configs_section.items():
            # perform environment variable substitution now which was skipped earlier
            f_val = os.path.expandvars(val)
            split_idx = f_val.find("->")
            if split_idx == -1:
                raise NotSupportedError("Incorrect value format in [configs] section for "
                                        f"'{key}'. Required: '{{src}} -> {{dest}}'")
            src_path = os.path.realpath(f_val[:split_idx].strip())
            dest_path = f"{conf.configs_dir}/{f_val[split_idx + 2:].strip()}"
            if os.access(src_path, os.R_OK):
                os.makedirs(os.path.dirname(dest_path),
                            mode=Consts.default_directory_mode(), exist_ok=True)
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
    print_info("DONE.")
    # finally mount the configs directory to corresponding directory in the target container
    add_mount_option(docker_args, conf.configs_dir, conf.target_configs_dir, "ro")


def process_env_section(env_section: SectionProxy, docker_args: list[str]) -> None:
    """
    Process the `[env]` section in the container profile to append required podman/docker
    options in the list that has been passed.

    :param env_section: an object of :class:`SectionProxy` from parsing the `[env]` section
    :param docker_args: list of podman/docker arguments to which required options as per the
                        configuration in the `[env]` section are appended
    """
    for key, val in env_section.items():
        add_env_option(docker_args, key, val)


def process_apps_section(apps_section: SectionProxy, conf: StaticConfiguration,
                         pkgmgr: SectionProxy) -> dict[str, list[str]]:
    """
    Process the `[apps]` section in the container profile to return a dictionary having packages
    to be installed mapped to the list of dependencies to be installed along with.

    :param apps_section: an object of :class:`SectionProxy` from parsing the `[apps]` section
    :param conf: the :class:`StaticConfiguration` for the container
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :return: dictionary of package names mapped to their list of dependencies as specified
             in the `[apps]` section
    """
    if len(apps_section) == 0:
        return {}
    quiet_flag = pkgmgr[PkgMgr.QUIET_FLAG.value]
    opt_dep_flag = pkgmgr[PkgMgr.OPT_DEP_FLAG.value]
    install_cmd = pkgmgr[PkgMgr.INSTALL.value].format(quiet=quiet_flag, opt_dep="")
    clean_cmd = pkgmgr[PkgMgr.CLEAN_QUIET.value]
    if not install_cmd:
        print_color("Skipping app installation since no 'pkgmgr.install' has "
                    "been defined in distro.ini or is empty",
                    fg=fgcolor.lightgray, bg=bgcolor.red)
        return {}
    # write pkgmgr.conf for entrypoint.sh
    with open(f"{conf.scripts_dir}/pkgmgr.conf", "w", encoding="utf-8") as pkg_fd:
        pkg_fd.write(f"PKGMGR_INSTALL='{install_cmd}'\n")
        pkg_fd.write(f"PKGMGR_CLEAN='{clean_cmd}'\n")
    apps_with_deps = defaultdict[str, list[str]](list[str])

    def capture_dep(match: re.Match[str]) -> str:
        dep = match.group(1)
        apps_with_deps[match.group(2)].append(dep)
        return dep

    with open(conf.app_list, "w", encoding="utf-8") as apps_fd:
        for _, val in apps_section.items():
            apps = [app.strip() for app in val.split(",")]
            deps = [capture_dep(match) for dep in apps if (match := _DEP_SUFFIX.match(dep))]
            if deps:
                apps = [app for app in apps if not _DEP_SUFFIX.match(app)]
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
    """
    Copy or create hard links to a source directory tree in the given destination directory.
    Since hard links to directories are not supported, the destination will mirror the directories
    of the source while the files inside will be either copies or hard links to the source.

    :param src: the source directory tree
    :param dest: the destination directory which should exist
    :param hardlink: if True then create hard links to the files in the source (so it should
                       be in the same filesystem) else copy the files, defaults to False
    """
    for src_dir, _, src_files in os.walk(src, followlinks=True):
        # substitute 'src' prefix with 'dest'
        dest_dir = f"{dest}{src_dir[len(src):]}"
        os.mkdir(dest_dir, mode=stat.S_IMODE(os.stat(src_dir).st_mode))
        for src_file in src_files:
            src_path = f"{src_dir}/{src_file}"
            if os.path.exists(src_path):
                if hardlink:
                    try:
                        os.link(os.path.realpath(src_path), f"{dest_dir}/{src_file}",
                                follow_symlinks=True)
                        continue
                    except OSError:
                        # in case of error (likely due to cross-device link) fallback to copying
                        pass
                shutil.copy2(src_path, f"{dest_dir}/{src_file}", follow_symlinks=True)


def setup_ybox_scripts(conf: StaticConfiguration, distro_config: ConfigParser) -> None:
    """
    Create/copy various scripts required for the ybox container including entrypoint scripts,
    Linux distribution specific scripts and other required executables (e.g. `run-in-dir`).

    :param conf: the :class:`StaticConfiguration` for the container
    :param distro_config: an object of :class:`ConfigParser` from parsing the Linux
                          distribution's `distro.ini`
    """
    # first create local mount directory having entrypoint and other scripts
    if os.path.exists(conf.scripts_dir):
        shutil.rmtree(conf.scripts_dir)
    os.makedirs(conf.scripts_dir, exist_ok=True)
    # allow for read/execute permissions for all since non-root user needs access with docker
    os.chmod(conf.scripts_dir, mode=0o755)
    copy_ybox_scripts_to_container(conf, distro_config)
    # finally write the current version to "version" file in scripts directory of the container
    write_ybox_version(conf)


def run_base_container(image_name: str, current_user: str, secondary_groups: str, docker_cmd: str,
                       conf: StaticConfiguration) -> None:
    """
    Start a minimal container for the selected Linux distribution with the smallest upstream image
    (important to save space when `base.shared_root` is provided) with `entrypoint-base.sh` as the
    entrypoint script giving user/group arguments to be same as the user as on the host machine.

    :param image_name: distribution image to use for the container as specified in `distro.ini`
    :param current_user: the current user executing the `ybox-create` script
    :param secondary_groups: secondary groups for the container user as specified in `distro.ini`
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    """
    # get current user and group details to pass to the entrypoint script
    user_entry = pwd.getpwnam(current_user)
    group_entry = grp.getgrgid(user_entry.pw_gid)
    print_warn(f"Creating container specific image having sudo user '{current_user}'")
    docker_run = [docker_cmd, "run", f"--name={conf.box_name}",
                  f"-v={conf.scripts_dir}:{conf.target_scripts_dir}:ro",
                  f"--label={YboxLabel.CONTAINER_BASE.value}",
                  f"--entrypoint={conf.target_scripts_dir}/{Consts.entrypoint_base()}",
                  image_name, "-u", current_user, "-U", str(user_entry.pw_uid),
                  "-n", user_entry.pw_gecos, "-g", group_entry.gr_name,
                  "-G", str(group_entry.gr_gid), "-s", secondary_groups]
    if conf.localtime:
        docker_run.append("-l")
        docker_run.append(conf.localtime)
    if conf.timezone:
        docker_run.append("-z")
        docker_run.append(conf.timezone)
    run_command(docker_run, error_msg="running container with base image")


def run_shared_copy_container(docker_cmd: str, image_name: str, shared_root: str,
                              shared_root_dirs: str, conf: StaticConfiguration,
                              quiet: bool) -> None:
    """
    Start a container from a base distribution image (with minimal configuration) when
    `shared_root` has been provided for the container and copy a configured set of directories
    (`shared_root_dirs` in `distro.ini`) from the container to the `shared_root` directory.
    This directory is then used as the root directory for all the final containers that share the
    same `shared_root`.

    If the provided `shared_root` directory already exists, then user is interactively asked
    whether to delete the existing directory before proceeding.

    :param docker_cmd: the podman/docker executable to use
    :param image_name: distribution image to use for the container as specified in `distro.ini`
    :param shared_root: the shared root directory to use for the container
    :param shared_root_dirs: comma-separate list of directories shared between containers having
                             the same `shared_root`
    :param conf: the :class:`StaticConfiguration` for the container
    :param quiet: if True then don't ask for user confirmation but assume a `no`
    """
    # if shared root copy exists locally, then prompt user to delete it or else exit
    if os.path.exists(shared_root):
        input_msg = f"""
            The shared root directory for '{conf.distribution}' already exists in:
                {shared_root}
            However, the corresponding ybox container image for '{conf.distribution}' does not
            exist. This can happen if an old copy of shared root directory is lying around and
            is usually safe to remove, but you should be sure that no other ybox is running
            for '{conf.distribution}' with 'shared_root' configuration that is using that
            directory. Should the root directory be removed (y/N): """
        response = "N" if quiet else input(dedent(input_msg))
        if response.strip().lower() == "y":
            try:
                shutil.rmtree(shared_root)
            except OSError:
                # try with sudo
                run_command(["/usr/bin/sudo", "/bin/rm", "-rf", shared_root],
                            error_msg="deleting directory")
        else:
            print_error(f"Aborting creation of ybox container '{conf.box_name}'")
            # remove the temporary image before exit
            remove_image(docker_cmd, image_name)
            sys.exit(1)
    os.makedirs(shared_root, mode=Consts.default_directory_mode())
    # the entrypoint-cp.sh script requires two arguments: first is the comma separated
    # list of directories to be copied, and second the target directory
    docker_full_cmd = [docker_cmd, "run", f"--name={conf.box_name}",
                       f"-v={conf.scripts_dir}:{conf.target_scripts_dir}:ro",
                       f"-v={shared_root}:{Consts.shared_root_mount_dir()}",
                       f"--label={YboxLabel.CONTAINER_COPY.value}", "--user=0",
                       f"--entrypoint={conf.target_scripts_dir}/{Consts.entrypoint_cp()}"]
    if conf.env.uses_podman:
        docker_full_cmd.append("--userns=keep-id")
    docker_full_cmd.extend((image_name, shared_root_dirs, Consts.shared_root_mount_dir()))
    run_command(docker_full_cmd, error_msg="running container for copying shared root")


def commit_container(docker_cmd: str, image_name: str, conf: StaticConfiguration) -> None:
    """
    Commit the contents of a container as a new image. This also sets up the `USER` and `WORKDIR`
    properties of the image to those of target user's name and home respectively (as detected in
    the `Environ` object).

    :param docker_cmd: the podman/docker executable to use
    :param image_name: name of the image to create
    :param conf: the :class:`StaticConfiguration` for the container
    """
    run_command([docker_cmd, "commit", "--change", f"USER {conf.env.target_user}",
                 "--change", f"WORKDIR {conf.env.target_home}", conf.box_name, image_name],
                error_msg="container commit")
    remove_container(docker_cmd, conf)


def remove_container(docker_cmd: str, conf: StaticConfiguration) -> None:
    """remove a stopped podman/docker container"""
    run_command([docker_cmd, "container", "rm", conf.box_name], error_msg="container rm")


def remove_image(docker_cmd: str, image_name: str) -> None:
    """remove an unused podman/docker image"""
    run_command([docker_cmd, "image", "rm", image_name], exit_on_error=False,
                error_msg="image remove")


def start_container(docker_full_cmd: list[str], current_user: str, shared_root: str,
                    shared_root_dirs: str, conf: StaticConfiguration) -> None:
    """
    Create and start the final ybox container applying all the provided configuration.
    The following characteristics of the container are noteworthy:
      * uses docker or podman to create the container that are required to be in `rootless` mode
      * maps the host environment user ID to the same UID in the container (`--userns=keep-id`)
        when using podman else maps to the root user for docker
      * sets the container user to host environment user using `--user=...` option but does not
        enforce the primary group in that option so that the container user can belong to other
        secondary groups that is required for some applications
      * as a result of above, applications that need user namespace support (like Steam) need
        to be started with explicit elevated capabilities e.g. using `setpriv --ambient-caps -all`
        (this can be specified in `[app_flags]` section of the container profile or when installing
         the application using `ybox-pkg install` which will add the same to the wrapper executable
         and desktop files)
      * containers with the same configured `shared_root` will share the system installation
        so any changes to system directories in one container will reflect in all others;
        such a configuration reduces memory and disk overheads of multiple containers significantly
        but users should also keep in mind that packages installed in any container will be
        visible across all containers so care should be taken to not use potentially risky
        programs from less secure containers; the `ybox-pkg` tool provided a convenient high-level
        package manager that users should use for managing packages in the containers which will
        help in exposing packages only in designated containers
      * systemd user service file can be generated for podman to start the container automatically
        on user login; docker installations run a background user service in any case which starts
        up the container without any additional setup

    :param docker_full_cmd: the `docker`/`podman run -itd` command with all the options filled
                            in from the container profile specification as a list of string
    :param current_user: the current user executing the `ybox-create` script
    :param shared_root: the shared root directory to use for the container
    :param shared_root_dirs: comma-separate list of directories shared between containers having
                             the same `shared_root`
    :param conf: the :class:`StaticConfiguration` for the container
    """
    add_mount_option(docker_full_cmd, conf.scripts_dir, conf.target_scripts_dir, "ro")
    # touch the status file and mount it
    status_path = Path(conf.status_file)
    status_path.unlink(missing_ok=True)
    status_path.touch(mode=0o600, exist_ok=False)
    add_mount_option(docker_full_cmd, conf.status_file, Consts.status_target_file())

    if shared_root:
        for shared_dir in shared_root_dirs.split(","):
            add_mount_option(docker_full_cmd, f"{shared_root}{shared_dir}", shared_dir)
    docker_full_cmd.append(f"-e=XDG_RUNTIME_DIR={conf.env.target_xdg_rt_dir}")
    docker_full_cmd.append("-e=YBOX_TARGET_SCRIPTS_DIR")  # pass this along for container scripts
    docker_full_cmd.append(f"--label={YboxLabel.CONTAINER_PRIMARY.value}")
    docker_full_cmd.append(f"--label={YboxLabel.CONTAINER_DISTRIBUTION.value}={conf.distribution}")
    docker_full_cmd.append(f"--entrypoint={conf.target_scripts_dir}/{Consts.entrypoint()}")
    # bubblewrap and thereby programs like steam do not work without --user
    # (https://github.com/containers/bubblewrap/issues/380#issuecomment-648169485)
    user_entry = pwd.getpwnam(current_user)
    user_uid = user_entry.pw_uid
    user_gid = user_entry.pw_gid
    if conf.env.uses_podman:
        docker_full_cmd.append(f"--user={user_uid}")
        docker_full_cmd.append("--userns=keep-id")
    else:
        docker_full_cmd.append("--user=0")
    docker_full_cmd.append(f"-e=YBOX_HOST_UID={user_uid}")
    docker_full_cmd.append(f"-e=YBOX_HOST_GID={user_gid}")
    docker_full_cmd.append(conf.box_image(bool(shared_root)))
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


def restart_container(docker_cmd: str, conf: StaticConfiguration) -> None:
    """restart a stopped podman/docker container"""
    if (code := int(run_command([docker_cmd, "container", "start", conf.box_name],
                                exit_on_error=False, error_msg="container restart"))) != 0:
        print_error(f"Also check 'ybox-logs {conf.box_name}' for details")
        sys.exit(code)
