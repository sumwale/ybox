#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

echo_color "$fg_cyan" "Configuring apt" >> $status_file
export DEBIAN_FRONTEND=noninteractive
# don't install recommended and suggested packages by default
cat > /etc/apt/apt.conf.d/10-ybox << EOF
APT::Get::Install-Recommends "0";
APT::Get::Install-Suggests "0";
APT::Install-Recommends "0";
APT::Install-Suggests "0";
EOF

apt-get update
apt-get install -y lsb-release
rel_name=$(lsb_release -cs)

mv /etc/apt/sources.list /etc/apt/sources.list.bak
cat > /etc/apt/sources.list << EOF
deb http://us.archive.ubuntu.com/ubuntu/ $rel_name main restricted universe multiverse
deb http://us.archive.ubuntu.com/ubuntu/ $rel_name-updates main restricted universe multiverse
deb http://us.archive.ubuntu.com/ubuntu/ $rel_name-backports main restricted universe multiverse
deb http://us.archive.ubuntu.com/ubuntu/ $rel_name-security main restricted universe multiverse
EOF

echo_color "$fg_cyan" "Setting up apt-fast" >> $status_file
apt-get update
apt-get install --install-recommends -y curl gnupg
echo -e "deb [signed-by=/etc/apt/keyrings/apt-fast.gpg] http://ppa.launchpad.net/apt-fast/stable/ubuntu $rel_name main" \
    > /etc/apt/sources.list.d/apt-fast.list
mkdir -p /etc/apt/keyrings
curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xA2166B8DE8BDC3367D1901C11EE2FF37CA8DA16B" | \
    gpg --dearmor -o /etc/apt/keyrings/apt-fast.gpg
apt-get update
apt-get install -y apt-fast
DOWNLOADBEFORE=true apt-fast full-upgrade -y

echo_color "$fg_cyan" "Running unminimize" >> $status_file
yes | unminimize

# generate the configured locale and assume it is UTF-8
echo_color "$fg_cyan" "Configuring locale" >> $status_file
DOWNLOADBEFORE=true apt-fast install -y locales
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
DOWNLOADBEFORE=true apt-fast install -y $REQUIRED_PKGS $RECOMMENDED_PKGS $SUGGESTED_PKGS \
                                        $REQUIRED_DEPS $RECOMMENDED_DEPS $SUGGESTED_DEPS
apt-mark auto $REQUIRED_DEPS $RECOMMENDED_DEPS $SUGGESTED_DEPS
apt-fast clean
apt-get clean

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

echo_color "$fg_cyan" "Installing starship for fancy bash prompt" >> $status_file
curl -sSL https://starship.rs/install.sh -o starship-install.sh && \
  /bin/sh starship-install.sh -y && rm -f starship-install.sh
echo -e 'eval "$(starship init bash)"' >> /etc/bash.bashrc
