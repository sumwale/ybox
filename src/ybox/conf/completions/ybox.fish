# Completions for ybox commands, a "Manage containers hosting Linux distributions and apps"

function __fish_ybox_complete_containers
  /usr/bin/python3 (type -p ybox-ls) --format="{{ .Names }}"
end

function __fish_ybox_complete_all_containers
  /usr/bin/python3 (type -p ybox-ls) --all --format="{{ .Names }}"
end

function __fish_ybox_complete_stopped_containers
  /usr/bin/python3 (type -p ybox-ls) --filter="status=exited" --format="{{ .Names }}"
end

function __fish_ybox_complete_distributions
  set user_supported ~/.config/ybox/distros/supported.list
  set sys_supported ~/.local/lib/python3*/site-packages/ybox/conf/distros/supported.list
  set local_supported src/ybox/conf/distros/supported.list
  if test -r "$user_supported"
    /usr/bin/cat $user_supported
  else if test -r "$sys_supported" 2>/dev/null
    /usr/bin/cat $sys_supported
  else if test -r "$local_supported" 2>/dev/null
    /usr/bin/cat $local_supported
  end
end


complete -f -c ybox-create -s h -l help -d "show help"
complete -c ybox-create -s n -l name -d "name of the ybox container" -r
complete -f -c ybox-create -s F -l force-own-orphans -d "force ownership of orphans on shared root"
complete -f -c ybox-create -s C -l distribution-config -d "path to custom distribution configuration file"
complete -f -c ybox-create -l distribution-image -d "custom container image"
complete -f -c ybox-create -s q -l quiet -d "skip interactive questions"
complete -f -c ybox-create -n "not __fish_seen_subcommand_from (__fish_ybox_complete_distributions)" -a "(__fish_ybox_complete_distributions)"


complete -f -c ybox-destroy -s h -l help -d "show help"
complete -f -c ybox-destroy -s f -l force -d "force destroy the container using SIGKILL if required"
complete -f -c ybox-destroy -n "not __fish_seen_subcommand_from (__fish_ybox_complete_all_containers)" -a "(__fish_ybox_complete_all_containers)"

complete -f -c ybox-logs -s h -l help -d "show help"
complete -f -c ybox-logs -s f -l follow -d "follow log output like 'tail -f'"
complete -f -c ybox-logs -n "not __fish_seen_subcommand_from (__fish_ybox_complete_all_containers)" -a "(__fish_ybox_complete_all_containers)"


complete -f -c ybox-ls -s h -l help -d "show help"
complete -f -c ybox-ls -s a -l all -d "show all containers including stopped"
complete -f -c ybox-ls -s f -l filter -d "filter in <key>=<value> format" -r
complete -f -c ybox-ls -s s -l format -d "format output using a JSON/Go template string" -r
complete -f -c ybox-ls -s l -l long-format -d "show more extended information"


complete -c ybox-cmd -s h -l help -d "show help"
complete -c ybox-cmd -n "not __fish_seen_subcommand_from (__fish_ybox_complete_containers)" -a "(__fish_ybox_complete_containers)" -f


# define subcommands for ybox-control
set -l control_commands start stop restart status
complete -c ybox-control -f
# common options for all ybox-control subcommands
complete -c ybox-control -s h -l help -d "show help"
# available subcommands for ybox-control with descriptions
complete -c ybox-control -n "not __fish_seen_subcommand_from $control_commands" -a start -d "start an inactive ybox container"
complete -c ybox-control -n "not __fish_seen_subcommand_from $control_commands" -a stop -d "stop an active ybox container"
complete -c ybox-control -n "not __fish_seen_subcommand_from $control_commands" -a restart -d "restart a ybox container"
complete -c ybox-control -n "not __fish_seen_subcommand_from $control_commands" -a status -d "show status of a ybox container"
# define arguments for individual subcommands using the "-n" option for the subcommand
complete -c ybox-control -n "__fish_seen_subcommand_from start" -a "(__fish_ybox_complete_stopped_containers)"
complete -c ybox-control -n "__fish_seen_subcommand_from stop" -a "(__fish_ybox_complete_containers)"
complete -c ybox-control -n "__fish_seen_subcommand_from restart" -a "(__fish_ybox_complete_all_containers)"
complete -c ybox-control -n "__fish_seen_subcommand_from status" -a "(__fish_ybox_complete_all_containers)"


# define subcommands for ybox-pkg
set -l pkg_commands install uninstall update list list-files info search mark clean repair
complete -c ybox-pkg -f
# common options for all ybox-pkg subcommands
complete -c ybox-pkg -s h -l help -d "show help"
complete -c ybox-pkg -s z -l ybox -d "ybox container to use for package operation" -rfa "(__fish_ybox_complete_containers)"
complete -c ybox-pkg -s C -l distribution-config -d "path to distribution configuration file" -rF
complete -c ybox-pkg -s q -l quiet -d "proceed without asking any questions using defaults"
# available subcommands for ybox-pkg with descriptions
complete -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a install -d "install a package with dependencies"
complete -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a uninstall -d "uninstall a package and optionally its dependencies"
complete -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a update -d "update some or all packages"
complete -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a list -d "list installed packages"
complete -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a list-files -d "list files of an installed package"
complete -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a info -d "show detailed information of package(s)"
complete -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a search -d "search repositories"
complete -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a mark -d "mark package as dependency or explicitly installed"
complete -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a clean -d "clean package cache"
complete -c ybox-pkg -n "not __fish_seen_subcommand_from $pkg_commands" -a repair -d "try to repair package state"
# define arguments for individual subcommands using the "-n" option for the subcommand
complete -c ybox-pkg -n "__fish_seen_subcommand_from install" -s o -l skip-opt-deps -d "skip optional dependencies"
