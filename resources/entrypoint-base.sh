#!/bin/bash -e

SCRIPT=$(basename "$0")
SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)

source "$SCRIPT_DIR/entrypoint-common.sh"

user=zbox
uid=1000
name=zbox
group=zbox
gid=1000

function show_usage() {
  echo
  echo "Usage: $SCRIPT [-u USER] [-U UID] [-n FULLNAME] [-g GROUP] [-G GID] [-h]"
  echo
  echo "Options:"
  echo "  -u USER       login of the user to add"
  echo "  -U UID        UID of the user"
  echo "  -n FULLNAME   full name of the user"
  echo "  -g GROUP      primary group of the user to add"
  echo "  -G GID        GID of the primary group of the user"
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

while getopts "u:U:n:g:G:h" opt; do
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

# generate /etc/machine-id which is required by some apps
/usr/bin/dbus-uuidgen --ensure=/etc/machine-id

# add the user with the same UID/GID as provided which should normally be the same as the
# user running this zbox (which avoids --userns=keep-id from increasing the image size
#   else the image size may get nearly doubled)
groupadd -g $gid $group
echo_color "$fg_blue" "Added group '$group'"
useradd -m -g $group -G nobody,video,lp,mail \
  -u $uid -d /home/$user -s /bin/bash -c "$name" $user
usermod --lock $user

# run the distribution specific initialization scripts
if [ -r "$SCRIPT_DIR/init-base.sh" ]; then
  /bin/bash "$SCRIPT_DIR/init-base.sh" $user > /dev/null
fi

# add the given user for sudoers with NOPASSWD
sudoers_file=/etc/sudoers.d/$user
echo "$user ALL=(ALL:ALL) NOPASSWD: ALL" > $sudoers_file
chmod 0440 $sudoers_file
echo_color "$fg_purple" "Added admin user '$user' to sudoers with NOPASSWD"

# change ownership of user's /run/user/<uid> tree which may have root ownership due to the
# docker bind mounts
run_dir=${XDG_RUNTIME_DIR:-/run/user/$uid}
mkdir -p $run_dir
chmod 0700 $run_dir
chown -Rf $uid:$gid $run_dir
echo_color "$fg_blue" "Created run directory for '$user' with proper permissions"
