#!/bin/sh

# Script to list all matches for an installed package (or virtual package), and sort them by
# installation time with most recently installed packages first.

set -e

# dash is faster than bash, hence there are no bashisms in this script
# (e.g. uses `echo "$var" |` instead of `<<< "$var"`)

# Check if all arguments are provided
if [ "$1" = "installed" ]; then
  grep_cmd=grep-status
elif [ "$1" = "available" ]; then
  grep_cmd=grep-aptavail
fi
if [ $# -ne 2 -o -z "$grep_cmd" ]; then
  echo "Usage: $0 (installed|available) <package>"
  exit 1
fi

# ensure that only system paths are searched for all the system utilities
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"

sys_arch="$(dpkg --print-architecture)"
# if package name has architecture, remove it for the command and match against the `Architecture`
# field in its output instead (or allow for `all` architecture)
echo "$2" | {
  if IFS=':' read -r name expected_arch; then
    pkgs="$($grep_cmd -FPackage,Provides -sPackage,Architecture -n -w "$name")"
    if [ -z "$pkgs" ]; then
      exit 1
    fi
    # if architecture is not provided for the package, then its the system architecture
    expected_arch="${expected_arch:-$sys_arch}"
    echo "$pkgs" | {
      # output is in the format: package\narchitecture\n\n
      while read -r pkg; do
        read -r arch
        read -r empty || true
        if [ "$arch" = "$expected_arch" -o "$arch" = "all" ]; then
          if [ "$arch" = "$sys_arch" -o "$arch" = "all" ]; then
            pkg_files="/var/lib/dpkg/info/$pkg.list /var/lib/dpkg/info/$pkg:$arch.list"
          else
            pkg_files="/var/lib/dpkg/info/$pkg:$arch.list"
          fi
          if [ "$1" = "installed" ]; then
            pkg_list="$pkg_list $pkg_files"
          else
            # skip installed packages when listing available packages
            if [ -n "$(/bin/ls -1U $pkg_files 2>/dev/null || true)" ]; then
              continue
            fi
            if [ "$arch" = "$sys_arch" ]; then
              available_pkgs="$available_pkgs$pkg\n"
            else
              available_pkgs="$available_pkgs$pkg:$arch\n"
            fi
          fi
        fi
      done
      if [ -z "$pkg_list" -a -z "$available_pkgs" ]; then
        exit 1
      fi
      if [ "$1" = "installed" ]; then
        # sort by installation time and remove system architecture name if present
        /bin/ls -1t $pkg_list 2>/dev/null | sed "s|^.*/||;s|\(:$sys_arch\)\?.list$||"
      else
        /bin/echo -ne "$available_pkgs"  # this prints newlines in dash as well as bash
      fi
    }
  else
    exit 1
  fi
}

exit 0
