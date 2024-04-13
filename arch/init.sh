#!/bin/sh -e

export LANG=en_US.UTF-8
export LANGUAGE=en_US:en
export LC_ALL=en_US.UTF-8

SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)

source "$SCRIPT_DIR/entrypoint-common.sh"

echo_color "$fg_cyan" "Copying prime-run and setting up base en_US locale" >> $status_file
cp -a "$SCRIPT_DIR/prime-run" /usr/local/bin/prime-run
chmod 0755 /usr/local/bin/prime-run

# for some reason TERMINFO_DIRS does not work for root user, so explicitly installing terminfo
# packages for other terminal emulators available in arch which occupy only a tiny space

# generate basic UTF-8 locale
echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen
locale-gen en_US.UTF-8
echo -e "LANG=$LANG\nLANGUAGE=$LANGUAGE\nLC_ALL=$LC_ALL" > /etc/locale.conf

# pacman configuration
echo_color "$fg_cyan" "Configuring pacman" >> $status_file
pacman-key --init
sed -i 's/^#Color.*/Color/;s/^NoProgressBar.*/#NoProgressBar/' /etc/pacman.conf
sed -i 's,^NoExtract[ ]*=[ ]*/\?usr/share/man.*,#\0,' /etc/pacman.conf
echo -e '[multilib]\nInclude = /etc/pacman.d/mirrorlist' >> /etc/pacman.conf

# set fastest mirror and update the installation
echo_color "$fg_cyan" "Installing reflector and updating fastest mirror list" >> $status_file
PAC="pacman --noconfirm"
$PAC -Syy
$PAC -S --needed reflector
sed -i 's/^--latest.*/--latest 30\n--number 5\n--threads 5/' /etc/xdg/reflector/reflector.conf
sed -i 's/^--sort.*/--sort rate/' /etc/xdg/reflector/reflector.conf
reflector @/etc/xdg/reflector/reflector.conf 2>/dev/null
$PAC -Syu

# install packages most users will need for working comfortably
echo_color "$fg_cyan" "Installing base set of packages for comfortable usage" >> $status_file
$PAC -S --needed lesspipe bash-completion bc base-devel man-db man-pages \
  pulseaudio-alsa neovim eza ncdu fd bat libva-utils mesa-utils vulkan-tools \
  cantarell-fonts ttf-fira-code noto-fonts kitty-terminfo rxvt-unicode-terminfo \
  rio-terminfo wezterm-terminfo wget aria2 btop realtime-privileges shared-mime-info
$PAC -S --needed --asdeps git ed unzip fastjar python-pynvim xsel intel-media-driver \
  libva-mesa-driver vulkan-intel vulkan-mesa-layers python-pip
rm -rf .cache

echo_color "$fg_cyan" "Configuring makepkg and system-wide bashrc" >> $status_file
# use reasonable MAKEFLAGS and zstd compression level for AUR packages
sed -i "s/^#MAKEFLAGS=.*/MAKEFLAGS=\"-j`/usr/bin/nproc --all`\"/" /etc/makepkg.conf
sed -i 's/^COMPRESSZST=.*/COMPRESSZST=(zstd -c -T0 -8 -)/' /etc/makepkg.conf

# common environment variables
echo -e '\nexport EDITOR=nvim\nexport VISUAL=nvim' >> /etc/bash.bashrc
echo -e 'export PAGER="less -RL"\nexport LESSOPEN="|/usr/bin/lesspipe.sh %s"' >> /etc/bash.bashrc
echo -e "LANG=$LANG\nLANGUAGE=$LANGUAGE\nLC_ALL=$LC_ALL" >> /etc/bash.bashrc
