#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

export HOME=/root
# pacman configuration
PAC="pacman --noconfirm"
echo_color "$fg_cyan" "Configuring pacman" >> $status_file
pacman-key --init
sed -i 's/^#[ ]*Color.*/Color/;s/^[ ]*NoProgressBar.*/#NoProgressBar/' /etc/pacman.conf
sed -i 's,^[ ]*NoExtract[ ]*=[ ]*/\?usr/share/man.*,#\0,' /etc/pacman.conf
sed -i 's,^[ ]*NoExtract[ ]*=[ ]*.*usr/share/i18n.*,#\0,' /etc/pacman.conf
# disable the sandbox in the newer pacman versions that does not work in container
sed -i 's/^#[ ]*DisableSandbox/DisableSandbox/' /etc/pacman.conf
if ! grep -q '^[ ]*\[multilib\]' /etc/pacman.conf; then
  echo -e '[multilib]\nInclude = /etc/pacman.d/mirrorlist' >> /etc/pacman.conf
fi
$PAC -Sy archlinux-keyring

# generate the configured locale and assume it is UTF-8
if [ -n "$LANG" -a "$LANG" != "C.UTF-8" ] && ! grep -q "^$LANG UTF-8" /etc/locale.gen; then
  echo_color "$fg_cyan" "Configuring locale" >> $status_file
  echo "$LANG UTF-8" >> /etc/locale.gen
  # always add en_US.UTF-8 regardless since some apps seem to depend on it
  if [ "$LANG" != "en_US.UTF-8" ]; then
    echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen
  fi
  if ! locale-gen; then
    # reinstall glibc to obtain /usr/share/i18/locales/* files and try again
    $PAC -Sy
    $PAC -S glibc
    if ! locale-gen; then
      echo_color "$fg_red" "FAILED to generate locale for $LANG, fallback to en_US.UTF-8" >> $status_file
      export LANG=en_US.UTF-8
      export LANGUAGE="en_US:en"
    fi
  fi
  echo "LANG=$LANG" > /etc/locale.conf
  if [ -n "$LANGUAGE" ]; then
    echo "LANGUAGE=\"$LANGUAGE\"" >> /etc/locale.conf
  fi
fi

# setup fastest mirrors and update the installation
if [ -n "$CONFIGURE_FASTEST_MIRRORS" ] && ! pacman -Qq reflector 2>/dev/null >/dev/null; then
  echo_color "$fg_cyan" "Installing reflector and searching for the fastest mirrors" >> $status_file
  $PAC -Syy
  $PAC -S --needed reflector
  sed -i 's/^--latest.*/--latest 30\n--number 5\n--threads 5/' /etc/xdg/reflector/reflector.conf
  sed -i 's/^--sort.*/--sort rate/' /etc/xdg/reflector/reflector.conf
  reflector @/etc/xdg/reflector/reflector.conf || true
fi
$PAC -Syu

# install packages most users will need for working comfortably
echo_color "$fg_cyan" "Installing base set of packages" >> $status_file
$PAC -S --needed $REQUIRED_PKGS $RECOMMENDED_PKGS $SUGGESTED_PKGS
$PAC -S --needed --asdeps $REQUIRED_DEPS $RECOMMENDED_DEPS $SUGGESTED_DEPS

echo_color "$fg_cyan" "Configuring makepkg and system-wide bashrc" >> $status_file
# use reasonable MAKEFLAGS and zstd compression level for AUR packages
sed -i "s/^#MAKEFLAGS=.*/MAKEFLAGS=\"-j`/usr/bin/nproc --all`\"/" /etc/makepkg.conf
sed -i 's/^COMPRESSZST=.*/COMPRESSZST=(zstd -c -T0 -8 -)/' /etc/makepkg.conf
# remove debug from options
sed -i 's/^OPTIONS\(.*\b[^!]\)debug/OPTIONS\1!debug/' /etc/makepkg.conf

# common environment variables
if ! grep -q '^export EDITOR=' /etc/bash.bashrc && $PAC -Qq neovim 2>/dev/null >/dev/null; then
  echo -e '\nexport EDITOR=nvim\nexport VISUAL=nvim' >> /etc/bash.bashrc
fi
if ! grep -q '^export LESSOPEN=' /etc/bash.bashrc && $PAC -Qq lesspipe 2>/dev/null >/dev/null; then
  echo -e '\nexport PAGER="less -RL"\nexport LESSOPEN="|/usr/bin/lesspipe.sh %s"' >> /etc/bash.bashrc
fi
if ! grep -q '^export LANG=' /etc/bash.bashrc && [ -n "$LANG" -a "$LANG" != "C.UTF-8" ]; then
  echo -e "\nexport LANG=$LANG" >> /etc/bash.bashrc
  if [ -n "$LANGUAGE" ]; then
    echo "export LANGUAGE=\"$LANGUAGE\"" >> /etc/bash.bashrc
  fi
fi
