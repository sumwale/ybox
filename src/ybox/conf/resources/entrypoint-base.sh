#!/bin/bash

set -e

SCRIPT="$(basename "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

user=ybox
uid=1000
name=ybox
group=ybox
gid=1000
secondary_groups=video,input,lp,mail
localtime=
timezone=

function show_usage() {
  echo
  echo "Usage: $SCRIPT [-u USER] [-U UID] [-n FULLNAME] [-g GROUP] [-G GID]"
  echo "       [-l LOCALTIME] [-z TIMEZONE] [-h]"
  echo
  echo "Options:"
  echo "  -u USER       login of the user being added"
  echo "  -U UID        UID of the user"
  echo "  -n FULLNAME   full name of the user"
  echo "  -g GROUP      primary group of the user being added"
  echo "  -G GID        GID of the primary group of the user"
  echo "  -s GROUPS     secondary groups of the user being added"
  echo "  -l LOCALTIME  the destination link for /etc/localtime"
  echo "  -z TIMEZONE   the timezone to be written in /etc/timezone"
  echo "  -h            show this help message and exit"
}

function check_space() {
  check_val="$1"
  if [[ "$check_val" = *[[:space:]]* ]]; then
    echo "$0: cannot have white space character in $2 -- $check_val"
    show_usage
    exit 1
  fi
}

function check_int() {
  check_val="$1"
  if ! [ "$check_val" -eq "$check_val" ] 2>/dev/null; then
    echo "$0: expected integer for $2 -- $check_val"
    show_usage
    exit 1
  fi
}

while getopts "u:U:n:g:G:s:l:z:h" opt; do
  case "$opt" in
    u)
      check_space "$OPTARG" USER
      user=$OPTARG
      ;;
    U)
      check_int "$OPTARG" UID
      uid=$OPTARG
      ;;
    n)
      name="$OPTARG"
      ;;
    g)
      check_space "$OPTARG" GROUP
      group=$OPTARG
      ;;
    G)
      check_int "$OPTARG" GID
      gid=$OPTARG
      ;;
    s)
      check_space "$OPTARG" GROUPS
      secondary_groups=$OPTARG
      ;;
    l)
      localtime="$OPTARG"
      ;;
    z)
      timezone="$OPTARG"
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

# run the distribution specific initialization scripts
if [ -r "$SCRIPT_DIR/init-base.sh" ]; then
  /bin/bash "$SCRIPT_DIR/init-base.sh" >/dev/null
fi

# setup timezone
if [ -n "$localtime" ]; then
  echo_color "$fg_blue" "Setting up timezone to $localtime"
  if [ -e "$localtime" ]; then
    rm -f /etc/localtime
    ln -s "$localtime" /etc/localtime
  fi
fi
if [ -n "$timezone" ]; then
  echo "$timezone" > /etc/timezone
  chmod 0644 /etc/timezone
fi

# add the user with the same UID/GID as provided which should normally be the same as the
# user running this ybox (which avoids --userns=keep-id from increasing the image size
#   else the image size may get nearly doubled)
existing_user="$(getent passwd $uid | cut -d: -f1)"
if [ -n "$existing_user" ]; then
  deluser --remove-home $existing_user
fi
existing_group="$(getent group $gid | cut -d: -f1)"
if [ -n "$existing_group" ]; then
  delgroup $existing_group
fi
groupadd -g $gid $group
echo_color "$fg_blue" "Added group '$group'"
useradd -m -g $group -G $secondary_groups \
  -u $uid -d /home/$user -s /bin/bash -c "$name" $user
usermod --lock $user

# add the given user for sudoers with NOPASSWD
sudoers_file=/etc/sudoers.d/$user
echo "$user ALL=(ALL:ALL) NOPASSWD: ALL" > $sudoers_file
chmod 0440 $sudoers_file
echo_color "$fg_purple" "Added admin user '$user' to sudoers with NOPASSWD"

# generate /etc/machine-id which is required by some apps
rm -f /etc/machine-id /var/lib/dbus/machine-id
dbus-uuidgen --ensure=/etc/machine-id
dbus-uuidgen --ensure

# change ownership of user's /run/user/<uid> tree which may have root ownership due to the
# docker bind mounts
run_dir=${XDG_RUNTIME_DIR:-/run/user/$uid}
mkdir -p $run_dir
chmod 0700 $run_dir
chown -Rf $uid:$gid $run_dir
echo_color "$fg_blue" "Created run directory for '$user' with proper permissions"

# add root user to all user groups for rootless docker that needs to run as the root user
# (which is mapped to the host's current user allowing for proper file and other permissions)
usermod -aG $group,$secondary_groups root
# the home directory of root user should be /root which is assumed to be the target directory
# by the ybox commands when using docker
root_home="$(getent passwd root | cut -d: -f6)"
if [ "$root_home" != "/root" ]; then
  echo_color "$fg_purple" "Changing home directory of root user from '$root_home' to '/root'"
  # this should be done at the very end of the entrypoint script to avoid any complications
  # due to change of root user's home directory in the middle of running commands
  mkdir -p /root
  chmod 700 /root
  sed -i "s|:$root_home:|:/root:|" /etc/passwd
  if [ "$root_home" != "/" ]; then
    cd "$root_home"
    # copy dotfiles skipping `.` and `..` which is done by setting GLOBIGNORE
    export GLOBIGNORE=.
    cp -a .* /root/.
    # not removing $root_home since it can potentially be some system directory (e.g. /usr)
  fi
fi
