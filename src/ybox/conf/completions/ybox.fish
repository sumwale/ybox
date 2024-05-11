# Completions for ybox commands, a "Manage containers hosting Linux distributions and apps"

function __fish_ybox_complete_containers
  ybox-ls --format="{{ .Names }}"
end

function __fish_ybox_complete_all_containers
  ybox-ls --all --format="{{ .Names }}"
end

function __fish_ybox_complete_distributions
  set user_supported ~/.config/ybox/distros/supported.list
  set sys_supported ~/.local/lib/python3*/site-packages/ybox/conf/distros/supported.list
  set conda_supported conda/.conda/envs/ybox/lib/python3*/site-packages/ybox/conf/distros/supported.list
  set local_supported src/ybox/conf/distros/supported.list
  if test -r "$user_supported"
    /usr/bin/cat $user_supported
  else if test -r "$sys_supported" 2>/dev/null
    /usr/bin/cat $sys_supported
  else if test -r "$conda_supported" 2>/dev/null
    /usr/bin/cat $conda_supported
  else if test -r "$local_supported" 2>/dev/null
    /usr/bin/cat $local_supported
  end
end

complete -f -c ybox-create -s h -l help -d "show help"
complete -c ybox-create -s n -l name -d "name of the ybox container" -r
complete -c ybox-create -s d -l docker-path -d "path of docker/podman if not in /usr/bin" -r
complete -f -c ybox-create -s F -l force-own-orphans -d "force ownership of orphans on shared root"
complete -f -c ybox-create -s q -l quiet -d "skip interactive questions"
complete -f -c ybox-create -n "not __fish_seen_subcommand_from (__fish_ybox_complete_distributions)" -a "(__fish_ybox_complete_distributions)"

complete -f -c ybox-destroy -s h -l help -d "show help"
complete -f -c ybox-destroy -s f -l force -d "force destroy the container using SIGKILL if required"
complete -c ybox-destroy -s d -l docker-path -d "path of docker/podman if not in /usr/bin" -r
complete -f -c ybox-destroy -n "not __fish_seen_subcommand_from (__fish_ybox_complete_all_containers)" -a "(__fish_ybox_complete_all_containers)"

complete -f -c ybox-logs -s h -l help -d "show help"
complete -f -c ybox-logs -s f -l follow -d "follow log output like 'tail -f'"
complete -c ybox-logs -s d -l docker-path -d "path of docker/podman if not in /usr/bin" -r
complete -f -c ybox-logs -n "not __fish_seen_subcommand_from (__fish_ybox_complete_all_containers)" -a "(__fish_ybox_complete_all_containers)"

complete -f -c ybox-ls -s h -l help -d "show help"
complete -f -c ybox-ls -s a -l all -d "show all containers including stopped"
complete -c ybox-ls -s d -l docker-path -d "path of docker/podman if not in /usr/bin" -r
complete -f -c ybox-ls -s f -l filter -d "filter in <key>=<value> format" -r
complete -f -c ybox-ls -s s -l format -d "format output using a JSON/Go template string" -r
complete -f -c ybox-ls -s l -l long-format -d "show more extended information"

complete -f -c ybox-restart -s h -l help -d "show help"
complete -c ybox-restart -s d -l docker-path -d "path of docker/podman if not in /usr/bin" -r
complete -f -c ybox-restart -n "not __fish_seen_subcommand_from (__fish_ybox_complete_containers)" -a "(__fish_ybox_complete_all_containers)"

complete -f -c ybox-cmd -s h -l help -d "show help"
complete -c ybox-cmd -s d -l docker-path -d "path of docker/podman if not in /usr/bin" -r
complete -f -c ybox-cmd -n "not __fish_seen_subcommand_from (__fish_ybox_complete_containers)" -a "(__fish_ybox_complete_containers)"


set -l pkg_commands install uninstall update list info search mark clean repair

complete -f -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a install -d "install a package with dependencies"
complete -f -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a uninstall -d "uninstall a package and optionally its dependencies"
complete -f -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a update -d "update some or all packages"
complete -f -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a list -d "list installed packages"
complete -f -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a search -d "search repositories"
