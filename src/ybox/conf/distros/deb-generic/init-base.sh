#!/bin/bash

set -e

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y apt-utils procps
apt-get install -y sudo dbus perl
# switch to sudo.ws in newer Ubuntu releases since sudo-rs does not support "sudo -E"
if update-alternatives --query sudo 2>/dev/null | grep -q '^[[:space:]]*Value:[[:space:]]*/usr/lib/cargo/bin/sudo'; then
  update-alternatives --set sudo /usr/bin/sudo.ws
fi
addgroup --quiet --system input
apt-get clean
