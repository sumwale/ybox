#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

echo_color "$fg_cyan" "Configuring apt" >> $status_file
export HOME=/root
export DEBIAN_FRONTEND=noninteractive
# don't install recommended and suggested packages by default
cat > /etc/apt/apt.conf.d/10-ybox << EOF
APT::Get::Install-Recommends "0";
APT::Get::Install-Suggests "0";
APT::Install-Recommends "0";
APT::Install-Suggests "0";
EOF

if [ -f /etc/dpkg/dpkg.cfg.d/excludes ]; then
  echo_color "$fg_cyan" "Removing dpkg excludes" >> $status_file
  mv /etc/dpkg/dpkg.cfg.d/excludes /etc/dpkg/dpkg.cfg.d/excludes.dpkg-tmp
elif [ -f /etc/dpkg/dpkg.cfg.d/docker ]; then
  echo_color "$fg_cyan" "Removing dpkg docker excludes" >> $status_file
  mv /etc/dpkg/dpkg.cfg.d/docker /etc/dpkg/dpkg.cfg.d/docker.dpkg-tmp
fi

apt-get update
apt-get install -y lsb-release

if [ "$(lsb_release -is 2>/dev/null)" = "Ubuntu" ]; then
  rel_name="$(lsb_release -cs 2>/dev/null)"
  # switch to the US mirror because fastest mirrors determined automatically occasionally break
  for f in /etc/apt/sources.list.d/ubuntu.sources \
           /etc/apt/sources.list.d/offical-package-repositories.list \
           /etc/apt/sources.list; do
    if [ -f $f ]; then
      source_file=$f
      break
    fi
  done
  if [ -n "$source_file" ]; then
    cp $source_file ${source_file}.bak
    sed -i 's,https\?://[^[:space:]]*ubuntu.com[^[:space:]]*,http://us.archive.ubuntu.com/ubuntu/,' $source_file
  fi
else
  rel_name=jammy # use jammy for apt-get install which works on all recent Debian releases
fi

echo_color "$fg_cyan" "Setting up apt-fast" >> $status_file
apt-get update
apt-get install --install-recommends -y curl gnupg
echo -e "deb [signed-by=/etc/apt/keyrings/apt-fast.gpg] http://ppa.launchpad.net/apt-fast/stable/ubuntu $rel_name main" \
    > /etc/apt/sources.list.d/apt-fast.list
mkdir -p /etc/apt/keyrings $HOME/.gnupg && chmod 0700 $HOME/.gnupg
GPG_CMD="gpg --no-default-keyring --keyring /tmp/apt-fast-keyring.gpg"
$GPG_CMD --keyserver $DEFAULT_GPG_KEY_SERVER --recv-key 0xBC5934FD3DEBD4DAEA544F791E2824A7F22B44BD
$GPG_CMD --output /etc/apt/keyrings/apt-fast.gpg --export && rm -f /tmp/apt-fast-keyring.gpg
apt-get update
apt-get install -y apt-fast
# update couple of apt-fast defaults (both conf file and debconf selection need to be changed)
sed -i 's/^_APTMGR=.*/_APTMGR=apt/' /etc/apt-fast.conf
sed -i 's/^_MAXNUM=.*/_MAXNUM=8/' /etc/apt-fast.conf
echo "apt-fast apt-fast/aptmanager select apt" | debconf-set-selections
echo "apt-fast apt-fast/maxdownloads select 8" | debconf-set-selections
DOWNLOADBEFORE=true apt-fast full-upgrade -y

if type unminimize 2>/dev/null >/dev/null; then
  echo_color "$fg_cyan" "Running unminimize" >> $status_file
  yes | unminimize
fi

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
