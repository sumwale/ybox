"""
Methods for repository management including adding, removing and listing repositories.
"""

import argparse
import re
import subprocess
import sys
from configparser import SectionProxy
from typing import Iterable, Sequence

from ybox.cmd import (PkgMgr, RepoCmd, build_shell_command, page_output,
                      run_command)
from ybox.config import Consts, StaticConfiguration
from ybox.print import fgcolor as fg
from ybox.print import print_error, print_info, print_warn
from ybox.state import RuntimeConfiguration, YboxStateManagement
from ybox.util import FormatTable


def repo_add(args: argparse.Namespace, pkgmgr: SectionProxy, repo: SectionProxy,
             docker_cmd: str, conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
             state: YboxStateManagement) -> int:
    """
    Add a new named repository given server URL(s) and optionally a verification key
    (usually a GPG/PGP key) to the underlying distribution's package manager.
    This method will also update the package metadata cache to reflect the change.

    :param args: arguments having `name`, `urls` and all other attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param repo: the `[repo]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :return: integer exit status of repo-add command where 0 represents success
    """
    name: str = args.name
    urls = ",".join(args.urls)
    # register_repository expects a valid string hence replace with empty string if `None`
    key: str = args.key or ""
    options: str = args.options or ""
    with_source_repo: bool = args.add_source_repo
    # register in the state database to check if there is no existing entry (the changes
    #   will be rolled back in case of failure later)
    shared_root = runtime_conf.shared_root
    container_or_shared_root = shared_root or conf.box_name
    if not state.register_repository(name, container_or_shared_root, urls, key, options,
                                     with_source_repo, update=False):
        shared_root_msg = f" (on shared root {shared_root})" if shared_root else ""
        print_error(f"Repository with name '{name}' already registered for the container "
                    f"'{conf.box_name}'{shared_root_msg}")
        return 1

    exists_cmd = repo[RepoCmd.EXISTS.value].format(name=name)
    if (code := int(run_command(build_shell_command(docker_cmd, conf.box_name, exists_cmd),
                    exit_on_error=False, error_msg="SKIP"))) == 0:
        print_error(f"Repository with name '{name}' already present in the package manager "
                    f"for the container '{conf.box_name}' [distribution: {conf.distribution}]")
        return 1

    # first fetch and register the key if specified
    if key:
        print_info(f"Fetching and registering key '{key}'")
        key_server = str(args.key_server or repo.get(RepoCmd.DEFAULT_GPG_KEY_SERVER.value,
                                                     fallback=Consts.default_key_server()))
        if re.match(r"^\S*?://", key):
            add_key_cmd = repo[RepoCmd.ADD_KEY.value].format(url=key, name=name)
            print_info(f"Registering key from URL '{key}'")
            with subprocess.Popen(build_shell_command(docker_cmd, conf.box_name, add_key_cmd),
                                  stdout=subprocess.PIPE) as key_result:
                # fetch the key ID from the output to register it
                keyid_tag = "KEYID="
                assert key_result.stdout is not None
                while line := key_result.stdout.readline():
                    key_out = line.decode("utf-8").strip()
                    if key_out.startswith(keyid_tag):
                        if (keyid := key_out[len(keyid_tag):]) != key:
                            key = keyid
                            print_info(f"Registered key '{key}'")
                            state.register_repository(name, container_or_shared_root, urls, key,
                                                      options, with_source_repo, update=True)
                    else:
                        sys.stdout.buffer.write(line)
                        sys.stdout.flush()
                if (code := key_result.wait(60)) != 0:
                    print_error(f"FAILED to register key '{key}' for repository '{name}' -- "
                                "see the output above for details.")
                    return code
        else:
            add_key_cmd = repo[RepoCmd.ADD_KEY_ID.value].format(key=key, server=key_server,
                                                                name=name)
            print_info(f"Registering key '{key}'")
            if (code := int(run_command(build_shell_command(
                    docker_cmd, conf.box_name, add_key_cmd), exit_on_error=False,
                    error_msg="registering repository key"))) != 0:
                return code

    # in case of failures, unregister key and/or repository at the end
    add_cmd = repo[RepoCmd.ADD.value].format(name=name, urls=urls, options=options)
    success = False
    repo_added = False
    src_added = False
    try:
        # next add the repository
        print_info(f"Registering repository '{name}'")
        if (code := int(run_command(build_shell_command(docker_cmd, conf.box_name, add_cmd),
                                    exit_on_error=False, error_msg="adding repository"))) != 0:
            return code
        repo_added = True
        # add the source code repository if specified
        if with_source_repo and (add_src_cmd := repo.get(RepoCmd.ADD_SOURCE.value, fallback="")):
            print_info(f"Registering source code repository '{name}'")
            add_src_cmd = add_src_cmd.format(name=name, urls=urls, options=options)
            if (code := int(run_command(build_shell_command(
                    docker_cmd, conf.box_name, add_src_cmd), exit_on_error=False,
                    error_msg="adding source repository"))) != 0:
                return code
            src_added = True

        # finally update the package metadata for the change in repositories
        code = _refresh_package_metadata(pkgmgr, docker_cmd, conf)
        success = code == 0
        return code
    finally:
        # remove the added key and/or repository in case of failure
        if not success:
            if repo_added:
                print_info(f"Trying to unregister failed repository '{name}'")
                remove_cmd = repo[RepoCmd.REMOVE.value].format(name=name, remove_source=src_added)
                run_command(build_shell_command(docker_cmd, conf.box_name, remove_cmd),
                            exit_on_error=False, error_msg=f"unregistering repository '{name}'")
            if key:
                print_info(f"Trying to unregister key for failed repository '{name}'")
                remove_key_cmd = repo[RepoCmd.REMOVE_KEY.value].format(key=key, name=name)
                run_command(build_shell_command(docker_cmd, conf.box_name, remove_key_cmd),
                            exit_on_error=False, error_msg=f"unregistering key '{key}'")


def repo_remove(args: argparse.Namespace, pkgmgr: SectionProxy, repo: SectionProxy,
                docker_cmd: str, conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
                state: YboxStateManagement) -> int:
    """
    Remove an existing named repository from the underlying distribution's package manager.
    This method will also update the package metadata cache to reflect the change.

    :param args: arguments having `name` and all other attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param repo: the `[repo]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :return: integer exit status of repo-remove command where 0 represents success
    """
    # unregister from the state database to check if there is no existing entry (the changes
    #   will be rolled back in case of failure later)
    name: str = args.name
    shared_root = runtime_conf.shared_root
    container_or_shared_root = shared_root or conf.box_name
    if not (result := state.unregister_repository(name, container_or_shared_root)):
        shared_root_msg = f" (on shared root {shared_root})" if shared_root else ""
        print_error(f"No such repository with name '{name}' registered for the container "
                    f"'{conf.box_name}'{shared_root_msg}")
        return 1
    key, with_source_repo = result
    # first unregister the repository key, if any
    if key:
        print_info(f"Unregistering repository key '{key}'")
        remove_key_cmd = repo[RepoCmd.REMOVE_KEY.value].format(key=key, name=name)
        if (code := int(run_command(build_shell_command(
                docker_cmd, conf.box_name, remove_key_cmd), exit_on_error=False,
                error_msg=f"unregistering key '{key}'"))) != 0 and not args.force:
            return code
    # next remove the repository
    print_info(f"Unregistering repository '{name}'")
    remove_cmd = repo[RepoCmd.REMOVE.value].format(name=name, remove_source=with_source_repo)
    if (code := int(run_command(build_shell_command(
            docker_cmd, conf.box_name, remove_cmd), exit_on_error=False,
            error_msg=f"unregistering repository '{name}'"))) != 0 and not args.force:
        return code
    # finally update package metadata
    code = _refresh_package_metadata(pkgmgr, docker_cmd, conf)
    return 0 if args.force else code


def _refresh_package_metadata(pkgmgr: SectionProxy, docker_cmd: str,
                              conf: StaticConfiguration) -> int:
    """
    Refresh package metadata cache to reflect the change in the registered repositories.

    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :return: integer exit status of package refresh command where 0 represents success
    """
    print_info("Refreshing package metadata")
    update_meta_cmd = pkgmgr[PkgMgr.UPDATE_META.value]
    return int(run_command(build_shell_command(docker_cmd, conf.box_name, update_meta_cmd),
                           exit_on_error=False, error_msg="updating package metadata"))


# noinspection PyUnusedLocal
def repo_list(args: argparse.Namespace, pkgmgr: SectionProxy, repo: SectionProxy,
              docker_cmd: str, conf: StaticConfiguration, runtime_conf: RuntimeConfiguration,
              state: YboxStateManagement) -> int:
    # pylint: disable=unused-argument
    """
    List the repositories registered using :func:`repo-add`.

    :param args: arguments having all attributes passed by the user
    :param pkgmgr: the `[pkgmgr]` section from `distro.ini` configuration file of the distribution
    :param repo: the `[repo]` section from `distro.ini` configuration file of the distribution
    :param docker_cmd: the podman/docker executable to use
    :param conf: the :class:`StaticConfiguration` for the container
    :param runtime_conf: the `RuntimeConfiguration` of the container
    :param state: instance of `YboxStateManagement` having the state of all ybox containers
    :return: integer exit status of repo-list command where 0 represents success
    """
    separator: str = args.plain_separator or ""

    def plain_output(tbl: Iterable[Iterable[str]], hdr: Sequence[str]) -> str:
        return "\n".join((separator.join(hdr), *(separator.join(line) for line in tbl)))

    repos = state.get_repositories(runtime_conf.shared_root or conf.box_name)
    if not repos:
        print_warn(f"No external repositories have been registered in container '{conf.box_name}'")
        return 1
    fg_name = fg.lightgray
    fg_urls = fg.orange
    if args.verbose:
        table = ((name, urls, key, options, "true" if with_source_repo else "false")
                 for name, urls, key, options, with_source_repo in repos)
        headers = ("Name", "Servers", "Key", "Options", "Source")
        if separator:
            out = plain_output(table, headers)
        else:
            # using ratio of 4:16:11:6:3 (out of 40) for the widths of the five columns
            out = FormatTable(table, headers, (fg_name, fg_urls, fg.cyan, fg.green, fg.blue),
                              "rounded_grid", (4.0, 16.0, 11.0, 6.0, 3.0)).show()
    else:
        table = ((name, urls) for name, urls, _, _, _ in repos)
        headers = ("Name", "Servers")
        if separator:
            out = plain_output(table, headers)
        else:
            out = FormatTable(table, headers, (fg_name, fg_urls),
                              "rounded_grid", (2.0, 8.0)).show()
    # empty pager argument is a valid one and indicates no pagination, hence the `is None` check
    pager: str = (args.pager or "") if args.pager is not None or separator else conf.pager
    return page_output((out.encode("utf-8"),), pager)
