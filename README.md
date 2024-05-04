## Introduction

Create and manage docker/podman containers hosting different Linux
distribution images. Manage their packages and applications directly
from your host machine and easily configure the containers with
simple INI files. It allows for set up of various aspects of
the container including support for X11, Wayland, audio, video acceleration,
NVIDIA, dbus among others. It also allows controlling various parameters
of the container including directories to be shared, logging etc.

Special emphasis is given on security where users can choose to lock down
or open up the container as required with reasonable defaults out of the
box. There is no sharing of HOME or no privileged mode container unless
explicitly configured.

Expected usage is for users to group similar applications in a container
and separate out containers depending on different needs like higher/lower
security, features off to minimum required for those set of applications.


## Features

- simple creation of docker/podman containers hosting Linux distributions (Arch Linux for now)
  using `zbox-create` with interactive menus
- special emphasis on security to lock down applications as much as possible to avoid
  "malicious" apps, backdoors etc., from affecting your main work space, so you can play/test
  software/games/... to your heart's content in these containers
- pre-built profiles for common uses, so you can just run `zbox-create`, select profile and
  be done with it; or advanced users can micro-customize a profile ini file as required
- allow for sharing root directories (like /usr, /etc) among various containers to reduce
  disk and memory usage (default behaviour in the shipped profiles)
- simple specification to list configuration files that you want to share with the containers
  in readonly mode (e.g. the basic.ini lists .bashrc, .vimrc etc.)
- completely isolated home directories in the containers, but you can still precisely control
  which directories to mount for sharing between the host and guests
- a high level generic package manager `zbox-pkg` with simple install/uninstall/... commands
  that uses the distribution package manager for the operation, creates wrapper desktop and
  executable files to invoke the container's executables, allows specifying additional
  optional dependencies you need with an application, and so on
- specify startup applications to run in a container if required (TBD)

For now only Arch Linux is supported which probably hosts the largest repository of Linux
applications with its AUR. So, for example, if you want to run the latest and greatest
Intellij IDEA community, all you need to do is:

```sh
zbox-create

zbox-pkg install intellij-idea-community-edition
```

This will automatically create a wrapper desktop file that launches from the container, so
you can simply launch it from your desktop environment's applications as usual.

In this way this acts as a complete replacement of flatpak/snap while being able to choose
from way bigger software repositories, and with applications configured the way they are
supposed to be in the original Linux distribution (which is only Arch Linux for now).
The big difference being that these are just containers where you can open a shell
(using `zbox-cmd`) and learn/play as required, or micro-configure stuff. You will not
notice much difference from a full Linux installation in a shell apart from missing
few things like systemd.


## Installation

If you have cloned the repository, then no further installation is required to run the utilities
in `src` directory which can be done directly off the repository. In the near future this will
also be published on `pypi.org`, so you will be able to install with `pip install zbox`.

As of now the following is required:

- clone the repo: `git clone https://github.com/sumwale/zbox.git`
- rootless podman or docker
  * for podman this only needs installation of `podman`, `slirp4netns` and `buildah` packages,
    then setup /etc/subuid and /etc/subgid as noted here:
    [/etc/subuid and /etc/subgid configuration](https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md#etcsubuid-and-etcsubgid-configuration)
    (ubuntu, for example will also set up subuid/subgid for current user automatically;
     for ubuntu 24.04 you may also need an apparmor profile as noted in the docker docs next)
  * for docker follow the instructions in the official [docs](https://docs.docker.com/engine/security/rootless/)
- python version 3.9 or higher -- all fairly recent Linux distributions should satisfy this
  but still confirm with `python3 --version`
- install [simple-term-menu](https://pypi.org/project/simple-term-menu/) either from your
  distribution repository, if available, else: `pip install simple-term-menu` (obviously
      you will need `pip` itself to be installed which should be in your distribution
      repositories e.g. ubuntu/debian have it as `python3-pip`)
- (optional) NVIDIA acceleration: if you intend to run games/video editors/... that need
  access to NVIDIA GPU acceleration, then you need to install
  [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html); for example on ubuntu with podman configure the apt repository
  and install the package as noted in the link, then run `sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml` (this will need to be repeated if nvidia driver version is upgraded)

In the future, installer will take care of setting all of these up.

Now you can simply go to the repository and run the `zbox-create` and other utilities from
the `src` directory of the repository checkout. For convenience, you can symlink these to
your `~/.local/bin` directory which should be in PATH in modern Linux distributions:

```sh
ln -s <full path of checkout zbox directory>/src/zbox-* ~/.local/bin/
```

All the `zbox-*` utilities will show detailed help with the `-h`/`--help` option.


## Usage

The basic workflow consists of setting up one or more containers, installing/removing/...
packages in those containers and opening a shell into a container for more "direct" usage.

You can also destroy the containers, list them, see their logs, or restart them using
convenient utilities.

### Create a new zbox container

```sh
zbox-create
```

This will allow choosing from the available profiles. You can start with the basic `apps.ini`
to try it out. The container will have a name like `zbox-<distro>_<profile>` by default like
`zbox-arch_apps` for the `apps.ini` profile.

The `$HOME` directory of the container can be found in `~/.local/share/zbox/<container>/home`
e.g. `~/.local/share/zbox/zbox-arch_apps/home` for the above example.

When shared root directory is enabled (which is the default in the shipped profiles), then
it uses the common distribution path in `~/.local/share/zbox/ROOTS/<distribution>`
i.e. `~/.local/share/zbox/ROOTS/arch` for the Arch Linux guests.

For more advanced usage, you can copy from the available profiles in `src/zbox/conf/profiles`
into `~/.config/zbox/profiles`, then edit as required. The `basic.ini` profile lists
all the available options with detailed comments. There are a few more detailed examples
in the `src/zbox/conf/profiles/examples` directory.


### Install/uninstall/list/search packages

Install a new package with `zbox-pkg` like firefox below:

```sh
zbox-pkg install firefox
```

If you have created multiples containers, then this will allow you to choose one among
them for the installation. After the main package installation, it will also list
the optional dependencies of the installed package (only till second level) and allow you
to choose from among them which may add additional features to the package.

The installation will also create wrapper desktop files in `~/.local/share/applications`
and executables in `~/.local/bin` so you can execute the newly install application binaries
from your desktop environment's application menu and/or from command-line.

Likewise, you can uninstall all the changes (including the optional packages chosen before):

```sh
zbox-pkg uninstall firefox
```

List the installed packages:

```sh
zbox-pkg list
```
This will list all the packages explicitly installed using `zbox-pkg`.

```sh
zbox-pkg list -s
```
This will show the dependent packages chosen in addition to the main packages.

```sh
zbox-pkg list -a
```
Will list all the distribution packages in the container including those not installed by
`zbox-pkg` (either installed in the base image, or installed later using the distribution
    package manager directly)

```sh
zbox-pkg list -v
```
Will show more details of the packages (combine with -a/-s as required)

Search the repositories for packages with names matching search terms:

```sh
zbox-pkg search intellij
```

Search the repositories for packages with names or descriptions matching search terms:

```sh
zbox-pkg search intellij -f
```

You can also restrict the search to full word matches (can be combined with -f if required):

```sh
zbox-pkg search intellij -w
```


### List the available containers

```sh
zbox-ls
```

will list the active zbox containers

```sh
zbox-ls -a
```

will list all zbox containers including stopped ones


### Destroy a container

```sh
zbox-destroy zbox-arch_apps
```

Will destroy the `apps` container created in the example before. This does not delete the
$HOME files, nor does it delete the shared root directory (if enabled). Hence, if you create
a new container having the same shared root, then it will inherit everything installed
previously. Likewise, if you create the container with the same profile again, then it
will also have the $HOME as before if you do not explicitly delete the directories
in `~/.local/share/zbox`.


**NOTE:** an auto-complete file for fish shell has been provided in
`src/zbox/conf/completions/zbox.fish`, so you can link that to your fish config:
```sh
ln -s <full path of checkout zbox directory>/src/zbox/conf/completions/zbox.fish ~/.config/fish/conf.d/
```
This will allow auto complete for zbox container names, profiles among others.
Auto-complete for bash/zsh will be added in the future.


### Running a command in a container

The `zbox-cmd` runs `/bin/bash` in the container by default:

```sh
zbox-cmd zbox-arch_apps
```

You can run other commands instead of bash shell, but if those commands require options starting
with a hyphen, then first end the options to `zbox-cmd` with a double hyphen:

```sh
zbox-cmd zbox-arch_apps -- ls -l
```

The default profiles also link the .bashrc and starship configuration files from your host
$HOME directory by default, so you should see the same bash shell configuration as in your
host. These are linked in read-only mode, so if you want to change these auto-linked
configuration files inside the container, then you will need to create a copy from the symlink
first (but then it will lose the link from the host $HOME).

A shell on a container will act like a native Linux distribution environment for most purposes.
The one prominent missing thing is systemd which is not enabled deliberately since it requires
highly elevated privileges. It is strongly recommended not to try and somehow enable systemd
in the containers lest it will bypass most of the security provided by a container environment.
Instead, you should just start any daemons the normal way as required. You will also need
to ensure that the daemons don't try and use journald for the logging, rather use the
normal /var/log based logging. Overall these containers are not meant for running system
daemons and similar low level utilities which should be the job of your host system.


### Show the container logs

```sh
zbox-logs zbox-arch_apps
```

Follow the logs like `tail -f`:

```sh
zbox-logs zbox-arch_apps -f
```

In the shipped profiles, the container logs go to `~/.local/share/zbox/<container>/logs/`
directory instead of polluting your journald logs as the docker/podman do by default.
You can delete old log files there safely if they start taking a lot of disk space.


### Restart a container

A container may get stopped after a reboot if systemd/... is not configured to auto-start
the docker/podman containers. You can check using `zbox-ls -a` and restart any stopped
containers as below:

```sh
zbox-restart zbox-arch_apps
```
