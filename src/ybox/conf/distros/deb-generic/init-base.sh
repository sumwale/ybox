#!/bin/bash

set -e

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y apt-utils procps
apt-get install -y sudo dbus perl
addgroup --quiet --system input
apt-get clean
