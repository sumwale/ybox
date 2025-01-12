#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

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

if [ "$(sed -n 's/^ID=//p' /etc/os-release)" = "ubuntu" ]; then
  apt_fast_rel="$(sed -n 's/^VERSION_CODENAME=//p' /etc/os-release)"
else
  apt_fast_rel=focal # use focal for apt-fast install which works on all recent Debian releases
  # enable contrib and non-free repositories for debian
  if [ -f /etc/apt/sources.list.d/debian.sources ]; then
    sed -i 's/^Components: main[ ]*$/Components: main contrib non-free non-free-firmware/' \
        /etc/apt/sources.list.d/debian.sources
  else
    sed -i 's/ main[ ]*$/ main contrib non-free/' /etc/apt/sources.list
  fi
fi
apt-get update

echo_color "$fg_cyan" "Setting up apt-fast" >> $status_file
apt-get install --install-recommends -y curl gnupg lsb-release
keyring_file=/etc/apt/keyrings/apt-fast.gpg
rm -f $keyring_file
echo -e "deb [signed-by=$keyring_file] http://ppa.launchpad.net/apt-fast/stable/ubuntu $apt_fast_rel main" \
    > /etc/apt/sources.list.d/apt-fast.list
mkdir -p /etc/apt/keyrings
bash "$SCRIPT_DIR/fetch-gpg-key-id.sh" 0xBC5934FD3DEBD4DAEA544F791E2824A7F22B44BD \
     "$DEFAULT_GPG_KEY_SERVER" $keyring_file

apt-get update
apt-get install -y apt-fast
# update couple of apt-fast defaults (both conf file and debconf selection need to be changed)
sed -i 's/^_APTMGR=.*/_APTMGR=apt/' /etc/apt-fast.conf
sed -i 's/^_MAXNUM=.*/_MAXNUM=6/' /etc/apt-fast.conf
echo "apt-fast apt-fast/aptmanager select apt" | debconf-set-selections
echo "apt-fast apt-fast/maxdownloads select 6" | debconf-set-selections

echo_color "$fg_cyan" "Upgrading all packages" >> $status_file
export DOWNLOADBEFORE=true
apt-fast full-upgrade -y --autoremove

# skip unminimize if not installing any recommended packages which should happen only in testing
if [ -n "$RECOMMENDED_PKGS" ]; then
  unminimize_path="$(type -p unminimize 2>/dev/null || true)"
  if [ -z "$unminimize_path" ]; then
    apt-get install -y unminimize 2>/dev/null || true
  fi
  unminimize_path="$(type -p unminimize 2>/dev/null || true)"
  if [ -n "$unminimize_path" ]; then
    echo_color "$fg_cyan" "Running unminimize" >> $status_file
    sed -i 's/apt-get/apt-fast/g' "$unminimize_path"
    yes | "$unminimize_path"
    apt-get remove --purge -y unminimize 2>/dev/null || true
  fi
fi

# packages can be marked as manually installed in the base image, so mark most of them as auto
apt-mark auto $(apt-mark showinstall) >/dev/null
apt-mark manual procps sudo curl gnupg lsb-release apt-fast

# generate the configured locale and assume it is UTF-8
echo_color "$fg_cyan" "Configuring locale" >> $status_file
apt-fast install -y locales
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
apt-fast install -y $REQUIRED_PKGS $RECOMMENDED_PKGS $SUGGESTED_PKGS \
                    $REQUIRED_DEPS $RECOMMENDED_DEPS $SUGGESTED_DEPS
apt-mark auto $REQUIRED_DEPS $RECOMMENDED_DEPS $SUGGESTED_DEPS
apt-fast clean
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

# skip starship if not installing any recommended packages which should happen only in testing
if [ -n "$RECOMMENDED_PKGS" ]; then
  echo_color "$fg_cyan" "Installing starship for fancy bash prompt" >> $status_file
  curl -sSL https://starship.rs/install.sh -o starship-install.sh && \
    /bin/sh starship-install.sh -y && rm -f starship-install.sh /tmp/tmp.*
  echo -e 'eval "$(starship init bash)"' >> /etc/bash.bashrc
fi
