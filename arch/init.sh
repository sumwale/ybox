#!/bin/sh -e

SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)

source "$SCRIPT_DIR/entrypoint-common.sh"

# pacman configuration
PAC="pacman --noconfirm"
echo_color "$fg_cyan" "Configuring pacman" >> $status_file
pacman-key --init
sed -i 's/^#Color.*/Color/;s/^NoProgressBar.*/#NoProgressBar/' /etc/pacman.conf
sed -i 's,^NoExtract[ ]*=[ ]*/\?usr/share/man.*,#\0,' /etc/pacman.conf
sed -i 's,^NoExtract[ ]*=[ ]*.*usr/share/i18n.*,#\0,' /etc/pacman.conf
if ! grep -q '^\[multilib\]' /etc/pacman.conf; then
  echo -e '[multilib]\nInclude = /etc/pacman.d/mirrorlist' >> /etc/pacman.conf
fi

echo_color "$fg_cyan" "Copying prime-run and configuring locale" >> $status_file
cp -a "$SCRIPT_DIR/prime-run" /usr/local/bin/prime-run
chmod 0755 /usr/local/bin/prime-run

# generate the configured locale and assume it is UTF-8
if [ -n "$LANG" ] && ! grep -q "^$LANG UTF-8" /etc/locale.gen; then
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
      LANG=en_US.UTF-8
      LANGUAGE="en_US:en"
      export LANG LANGUAGE
    fi
  fi
  echo "LANG=$LANG" > /etc/locale.conf
  if [ -n "$LANGUAGE" ]; then
    echo "LANGUAGE=\"$LANGUAGE\"" >> /etc/locale.conf
  fi
fi

# set fastest mirror and update the installation
if ! pacman -Q reflector 2>/dev/null >/dev/null; then
  echo_color "$fg_cyan" "Installing reflector and searching for the fastest mirrors" >> $status_file
  $PAC -Syy
  $PAC -S --needed reflector
  sed -i 's/^--latest.*/--latest 30\n--number 5\n--threads 5/' /etc/xdg/reflector/reflector.conf
  sed -i 's/^--sort.*/--sort rate/' /etc/xdg/reflector/reflector.conf
  reflector @/etc/xdg/reflector/reflector.conf 2>/dev/null
  $PAC -Syu
fi

# for some reason TERMINFO_DIRS does not work for root user, so explicitly installing terminfo
# packages for other terminal emulators available in arch which occupy only a tiny space

# install packages most users will need for working comfortably
echo_color "$fg_cyan" "Installing base set of packages" >> $status_file
$PAC -S --needed lesspipe bash-completion bc base-devel man-db man-pages \
  pulseaudio-alsa neovim eza ncdu fd bat libva-utils mesa-utils vulkan-tools tree starship \
  cantarell-fonts ttf-fira-code noto-fonts kitty-terminfo rxvt-unicode-terminfo \
  rio-terminfo wezterm-terminfo wget aria2 btop realtime-privileges shared-mime-info
$PAC -S --needed --asdeps git ed unzip fastjar python-pynvim xsel intel-media-driver \
  libva-mesa-driver vulkan-intel vulkan-mesa-layers python-pip

echo_color "$fg_cyan" "Configuring makepkg and system-wide bashrc" >> $status_file
# use reasonable MAKEFLAGS and zstd compression level for AUR packages
sed -i "s/^#MAKEFLAGS=.*/MAKEFLAGS=\"-j`/usr/bin/nproc --all`\"/" /etc/makepkg.conf
sed -i 's/^COMPRESSZST=.*/COMPRESSZST=(zstd -c -T0 -8 -)/' /etc/makepkg.conf

# common environment variables
if ! grep -q '^export LESSOPEN=' /etc/bash.bashrc; then
  echo -e '\nexport EDITOR=nvim\nexport VISUAL=nvim' >> /etc/bash.bashrc
  echo -e 'export PAGER="less -RL"\nexport LESSOPEN="|/usr/bin/lesspipe.sh %s"' >> /etc/bash.bashrc
  if [ -n "$LANG" ]; then
    grep -v '^#' /etc/locale.conf | \
      while read line; do
        echo "export $line" >> /etc/bash.bashrc
      done
  fi
fi
