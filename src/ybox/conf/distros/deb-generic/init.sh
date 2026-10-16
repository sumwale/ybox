#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

# switch to sudo.ws in newer Ubuntu releases since sudo-rs does not support "sudo -E"
if update-alternatives --query sudo 2>/dev/null | grep -q '^[[:space:]]*Value:[[:space:]]*/usr/lib/cargo/bin/sudo'; then
  update-alternatives --set sudo /usr/bin/sudo.ws
fi

if [ -f /etc/dpkg/dpkg.cfg.d/excludes ]; then
  echo_color "$fg_cyan" "Removing dpkg excludes" >> $status_file
  mv /etc/dpkg/dpkg.cfg.d/excludes /etc/dpkg/dpkg.cfg.d/excludes.dpkg-tmp
elif [ -f /etc/dpkg/dpkg.cfg.d/docker ]; then
  echo_color "$fg_cyan" "Removing dpkg docker excludes" >> $status_file
  mv /etc/dpkg/dpkg.cfg.d/docker /etc/dpkg/dpkg.cfg.d/docker.dpkg-tmp
fi

echo_color "$fg_cyan" "Configuring apt and updating package list" >> $status_file
export HOME=/root
export DEBIAN_FRONTEND=noninteractive
# don't install recommended and suggested packages by default but keep them if they are
# deliberately marked as dependencies
cat > /etc/apt/apt.conf.d/10-ybox << EOF
APT::Install-Recommends "false";
APT::Install-Suggests "false";
APT::AutoRemove::RecommendsImportant "true";
APT::AutoRemove::SuggestsImportant "true";
EOF
# allow language translations in apt for non english locales
if [[ -n "$LANG" && ! "$LANG" =~ ^C(\..+)?$ && "$LANG" != "POSIX" && ! "$LANG" == en_* ]]; then
  rm -f /etc/apt/apt.conf.d/docker-no-languages
fi

echo_color "$fg_cyan" "Setting up upstream mozilla repo for firefox and thunderbird" >> $status_file
install -d -m 0755 /etc/apt/keyrings
wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O /etc/apt/keyrings/packages.mozilla.org.asc
cat > /etc/apt/sources.list.d/mozilla.sources << EOF
Types: deb
URIs: https://packages.mozilla.org/apt
Suites: mozilla thunderbird-deb
Components: main
Signed-By: /etc/apt/keyrings/packages.mozilla.org.asc
EOF
cat > /etc/apt/preferences.d/mozilla << EOF
Package: *
Pin: origin packages.mozilla.org
Pin-Priority: 600
EOF

echo_color "$fg_cyan" "Setting up nala" >> $status_file
apt-get update
apt-get install --install-recommends -y curl gnupg lsb-release nala

echo_color "$fg_cyan" "Upgrading all packages" >> $status_file
nala upgrade --full --purge -y

# skip unminimize if not installing any recommended packages which should happen only in testing
if [ -n "$RECOMMENDED_PKGS" ]; then
  unminimize_path="$(type -p unminimize 2>/dev/null || true)"
  if [ -z "$unminimize_path" ]; then
    apt-get install -y unminimize 2>/dev/null || true
  fi
  unminimize_path="$(type -p unminimize 2>/dev/null || true)"
  if [ -n "$unminimize_path" ]; then
    echo_color "$fg_cyan" "Running unminimize" >> $status_file
    yes | "$unminimize_path"
    apt-get remove --purge -y unminimize 2>/dev/null || true
  fi
fi

# packages can be marked as manually installed in the base image, so mark most of them as auto
apt-mark auto $(apt-mark showinstall) >/dev/null
apt-mark manual procps sudo curl gnupg lsb-release nala wget

# generate the configured locale and assume it is UTF-8
echo_color "$fg_cyan" "Configuring locale" >> $status_file
nala install --no-update --no-autoremove -y locales
if [ -n "$LANG" -a "$LANG" != "C.UTF-8" ] && ! grep -q "^$LANG UTF-8" /etc/locale.gen; then
  echo "$LANG UTF-8" >> /etc/locale.gen
  # always add en_US.UTF-8 regardless since some apps seem to depend on it
  if [ "$LANG" != "en_US.UTF-8" ]; then
    echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen
  fi
  if ! locale-gen; then
    echo_color "$fg_red" "FAILED to generate locale for $LANG, fallback to en_US.UTF-8" >> $status_file
    export LANG=en_US.UTF-8
    export LANGUAGE="en_US:en"
  fi
  echo "LANG=$LANG" > /etc/default/locale
  if [ -n "$LANGUAGE" ]; then
    echo "LANGUAGE=\"$LANGUAGE\"" >> /etc/default/locale
  fi
fi

echo_color "$fg_cyan" "Installing base set of packages" >> $status_file
nala install --no-update -y $REQUIRED_PKGS $RECOMMENDED_PKGS $SUGGESTED_PKGS \
                            $REQUIRED_DEPS $RECOMMENDED_DEPS $SUGGESTED_DEPS
apt-mark auto $REQUIRED_DEPS $RECOMMENDED_DEPS $SUGGESTED_DEPS
nala autopurge
apt clean

# common environment variables
if ! grep -q '^export EDITOR=' /etc/bash.bashrc && dpkg --no-pager -l neovim 2>/dev/null >/dev/null; then
  echo -e '\nexport EDITOR=nvim\nexport VISUAL=nvim' >> /etc/bash.bashrc
fi
if ! grep -q '^export LESSOPEN=' /etc/bash.bashrc && dpkg --no-pager -l lesspipe 2>/dev/null >/dev/null; then
  echo -e '\nexport PAGER="less -RL"' >> /etc/bash.bashrc
  lesspipe >> /etc/bash.bashrc
fi
if ! grep -q '^export LANG=' /etc/bash.bashrc && [ -n "$LANG" -a "$LANG" != "C.UTF-8" ]; then
  echo -e "\nexport LANG=$LANG" >> /etc/bash.bashrc
  if [ -n "$LANGUAGE" ]; then
    echo "export LANGUAGE=\"$LANGUAGE\"" >> /etc/bash.bashrc
  fi
fi
