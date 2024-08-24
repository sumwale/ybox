#!/bin/bash

set -e

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y apt-utils procps
# packages can be marked as manually installed in the base image, so mark most of them as auto
apt-mark auto '*' >/dev/null
apt-mark manual procps usrmerge
apt-get install -y sudo dbus
addgroup --quiet --system input
apt-get clean
