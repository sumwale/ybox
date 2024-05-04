# ensure that system path is always searched first for all the system utilities
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

status_file=/usr/local/ybox-status

fg_red='\033[31m'
fg_green='\033[32m'
fg_orange='\033[33m'
fg_blue='\033[34m'
fg_purple='\033[35m'
fg_cyan='\033[36m'
fg_reset='\033[00m'

function echo_color() {
  args=
  while [[ $1 = -* ]]; do
    args="$args $1"
    shift
  done
  color="$1"
  shift
  echo -e $args "$color$@" $fg_reset
}
