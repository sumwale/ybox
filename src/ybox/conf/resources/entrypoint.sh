#!/bin/bash

set -e

SCRIPT="$(basename "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

config_list=
config_dir=
app_list=
pkgmgr_conf="$SCRIPT_DIR/pkgmgr.conf"
startup_list=
run_user_bash_cmd=/usr/local/bin/run-user-bash-cmd

# first clear the status_file
echo -n > $status_file

# for docker the container runs as root user but some actions need to be performed as normal
# user (like installing AUR packages in Arch), so the status file is made writable by both
# the current user as well as the group of the normal user
uid="$(id -u)"
gid="$(id -g)"
chown $uid:${YBOX_HOST_GID:-$gid} $status_file
chmod 0660 $status_file
if [ "$uid" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo -E"
fi

function show_usage() {
  echo
  echo "Usage: $SCRIPT [-c CONFIG_LIST] [-d CONFIG_DIR] [-a APP_LIST]"
  echo "       [-s STARTUP_LIST] [-h] BOX_NAME"
  echo
  echo "Arguments:"
  echo "  BOX_NAME         name of the ybox container being created"
  echo
  echo "Options:"
  echo "  -c CONFIG_LIST   file having list of configuration files to be setup in user's HOME"
  echo "  -d CONFIG_DIR    target directory having the configuration files"
  echo "  -a APP_LIST      file having list of applications to be installed"
  echo "                   (each line should start with any additional package manager flags)"
  echo "  -s STARTUP_LIST  file containing list of startup applications for the container"
  echo "  -h               show this help message and exit"
}

# copy/link the configuration files in HOME to the target directory having the required files
function replicate_config_files() {
  # line is of the form <src> -> <dest>; pattern below matches this while trimming spaces
  echo_color "$fg_orange" "Linking configuration files from $config_dir to user's home" >> $status_file
  pattern='(COPY|LINK_DIR|LINK):(.*)'
  while read -r config; do
    if [[ "$config" =~ $pattern ]]; then
      home_file="$HOME/${BASH_REMATCH[2]}"
      dest_file="$config_dir/${BASH_REMATCH[2]}"
      # only replace the file if it is already a link (assuming the link target may
      #   have changed in the config_list file), or a directory containing only links
      if [ -e "$dest_file" ]; then
        if [ -L "$home_file" ]; then
          rm -f "$home_file"
        elif [ -d "$home_file" ]; then
          if [ -z $(find "$home_file" -type f -print -quit) ]; then
            rm -rf "$home_file"
          fi
        fi
        home_filedir="$(dirname "$home_file")"
        if [ ! -e "$home_filedir" ]; then
          mkdir -p "$home_filedir"
        fi
        if [ ! -e "$home_file" ]; then
          if [ "${BASH_REMATCH[1]}" = "COPY" ]; then
            cp -r "$dest_file" "$home_file"
          elif [ "${BASH_REMATCH[1]}" = "LINK_DIR" ]; then
            # if dest_file is a directory, then replicate the directory structure in home and
            # symlink individual files which is accomplished with "cp -sr"
            cp -sr "$dest_file" "$home_file"
          else  # "${BASH_REMATCH[1]}" = "LINK"
            ln -s "$dest_file" "$home_file"
          fi
        fi
      fi
    else
      echo_color "$fg_red" "Skipping config line having unknown format: $config" >> $status_file
    fi
  done < "$config_list"
}

# install applications listed in the given file with the configured package manager commands
function install_apps() {
  # source PKGMGR_* variables from the configuration file created by 'ybox-create'
  source "$pkgmgr_conf"
  if [ -z "$PKGMGR_INSTALL" -o -z "$PKGMGR_CLEAN" ]; then
    echo_color "$fg_red" "$pkgmgr_conf should define PKGMGR_INSTALL and PKGMGR_CLEAN" >> $status_file
    exit 1
  fi
  # install packages line by line
  while read -r pkg_line; do
    echo_color "$fg_orange" "Installing: ${pkg_line:0:40} ..." >> $status_file
    $run_user_bash_cmd "$PKGMGR_INSTALL $pkg_line"
    echo_color "$fg_green" "Done." >> $status_file
  done < "$app_list"
  echo_color "$fg_green" "Cleaning up." >> $status_file
  $run_user_bash_cmd "$PKGMGR_CLEAN"
}

# invoke the startup apps as listed in the container configuration file
function invoke_startup_apps() {
  log_dir="$HOME/.local/share/ybox/logs"
  log_no=1
  mkdir -p "$log_dir"
  # start apps in the order listed in the file
  while read -r app_line; do
    echo_color "$fg_orange" "Starting: ${app_line:0:40} ..." >> $status_file
    nohup $app_line >> "$log_dir/app-${log_no}_out.log" 2>> "$log_dir/app-${log_no}_err.log" &
    ((log_no++))
    sleep 1
  done < "$startup_list"
}


while getopts "c:d:a:s:h" opt; do
  case "$opt" in
    c)
      config_list="$OPTARG"
      ;;
    d)
      config_dir="$OPTARG"
      ;;
    a)
      app_list="$OPTARG"
      # assume package manager configuration to be in pkgmgr.conf in same dir as this script
      if [ ! -r "$pkgmgr_conf" ]; then
        echo "Cannot find $pkgmgr_conf to apply the given APP_LIST"
        exit 1
      fi
      ;;
    s)
      startup_list="$OPTARG"
      ;;
    h)
      show_usage
      exit 0
      ;;
    ?)
      show_usage
      exit 1
      ;;
  esac
done

if [ -n "$config_list" -a -z "$config_dir" ]; then
  echo "$0: missing '-d CONFIG_DIR' option for given CONFIG_LIST -- $config_list"
  show_usage
  exit 1
fi

# handle positional arguments
if [ $(("$#" - "$OPTIND")) -ne 0 ]; then
  echo "$0: incorrect number of required arguments"
  show_usage
  exit 1
fi
box_name="${@:$OPTIND:1}"

# create/update some common directories that are mounted and may have root permissions
dir_init=". .cache .cache/fontconfig .config .config/pulse .local .local/share"
dir_init+=" .local/share/ybox .local/share/ybox/$box_name Downloads"
echo_color "$fg_orange" "Ensuring proper permissions for user directories" >> $status_file
for d in $dir_init; do
  dir=$HOME/$d
  $SUDO mkdir -p $dir || true
  $SUDO chown $uid:$gid $dir || true
done
# change ownership of user's /run/user/<uid> tree which may have root ownership due to the
# docker bind mounts
run_dir=${XDG_RUNTIME_DIR:-/run/user/$uid}
host_run_dir=${run_dir}-host
if [ -d $run_dir ]; then
  $SUDO chown $uid:$gid $run_dir 2>/dev/null || true
fi
if compgen -G "$run_dir/*" >/dev/null; then
  $SUDO chown $uid:$gid $run_dir/* 2>/dev/null || true
fi

# link wayland sockets/locks if enabled
if [ "$ENABLE_WAYLAND" = true ] && compgen -G "$host_run_dir/wayland-*" >/dev/null; then
  ln -sf $host_run_dir/wayland-* $run_dir/.
fi

# run actions requiring root access
$SUDO /bin/bash "$SCRIPT_DIR/entrypoint-root.sh"

# run the distribution specific initialization scripts
if [ ! -e "$SCRIPT_DIR/ybox-init.done" ]; then
  if [ -r "$SCRIPT_DIR/init.sh" ]; then
    echo_color "$fg_orange" "Running distribution's system initialization script" >> $status_file
    $SUDO /bin/bash "$SCRIPT_DIR/init.sh"
  fi
  if [ -r "$SCRIPT_DIR/init-user.sh" ]; then
    echo_color "$fg_orange" "Running user initialization scripts" >> $status_file
    # run the common user initialization script for both the root and non-root user
    $SUDO /bin/bash "$SCRIPT_DIR/entrypoint-user.sh"
    $run_user_bash_cmd "/bin/bash \"$SCRIPT_DIR/entrypoint-user.sh\""
    # run the distribution's user initialization script for the non-root user
    $run_user_bash_cmd "/bin/bash \"$SCRIPT_DIR/init-user.sh\""
  fi
  $SUDO rm -rf /root/.cache/*
  # Update the status file to indicate the stoppage and exit because system libraries
  # may have been installed/updated by the above scripts.
  # Caller will restart the container after removing the init scripts.
  echo stopped >> $status_file
  sync $status_file
  exit 0
fi

# process config files, application installs and invoke startup apps
if [ -n "$config_list" -a -s "$config_list" ]; then
  replicate_config_files
fi
if [ -n "$app_list" -a -s "$app_list" ]; then
  install_apps
fi
if [ -n "$startup_list" -a -s "$startup_list" ]; then
  invoke_startup_apps
fi
# update the status file to indicate successful startup
echo started >> $status_file

# finally go into infinite wait using tail on /dev/null but handle TERM signal for clean exit
tail -s10 -f /dev/null &
childPID=$!

function cleanup() {
  # clear status file first just in case other operations do not finish before SIGKILL comes
  echo -n > $status_file
  # first send SIGTERM to all "docker exec" processes that will have parent PID as 0 or 1
  kill_sent=0
  exec_pids="$(ps -e -o ppid=,pid= | \
    awk '{ if (($1 == 0 || $1 == 1) && $2 != 1 && $2 != '$childPID') print $2 }')"
  for pid in $exec_pids; do
    if kill -TERM $pid 2>/dev/null; then
      kill_sent=1
      echo "Sent SIGTERM to $pid"
    fi
  done
  # sleep a bit for $exec_pids to finish
  [ $kill_sent -eq 1 ] && sleep 3
  # lastly kill the infinite tail process
  kill -TERM $childPID
}

# truncate status file and cleanly kill the processes on SIGHUP and SIGTERM
trap "cleanup" 1 15

wait $childPID
