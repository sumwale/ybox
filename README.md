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
  using `ybox-create` with interactive menus
- special emphasis on security to lock down applications as much as possible to avoid
  "malicious" apps, backdoors etc., from affecting your main work space, so you can play/test
  software/games/... to your heart's content in these containers
- pre-built profiles for common uses, so you can just run `ybox-create`, select profile and
  be done with it; or advanced users can micro-customize a profile ini file as required
- allow for sharing root directories (like /usr, /etc) among various containers to reduce
  disk and memory usage (default behaviour in the shipped profiles)
- simple specification to list configuration files that you want to share with the containers
  in readonly mode (e.g. the basic.ini lists .bashrc, .vimrc etc.)
- completely isolated home directories in the containers, but you can still precisely control
  which directories to mount for sharing between the host and guests
- a high level generic package manager `ybox-pkg` with simple install/uninstall/... commands
  that uses the distribution package manager for the operation, creates wrapper desktop and
  executable files to invoke the container's executables, allows specifying additional
  optional dependencies you need with an application, and so on
- specify startup applications to run in a container if required (TBD)

For now only Arch Linux is supported which probably hosts the largest repository of Linux
applications with its AUR. So, for example, if you want to run the latest and greatest
Intellij IDEA community, all you need to do is:

```sh
ybox-create

ybox-pkg install intellij-idea-community-edition
```

This will automatically create a wrapper desktop file that launches from the container, so
you can simply launch it from your desktop environment's applications as usual.

In this way this acts as a complete replacement of flatpak/snap while being able to choose
from way bigger software repositories, and with applications configured the way they are
supposed to be in the original Linux distribution (which is only Arch Linux for now).
The big difference being that these are just containers where you can open a shell
(using `ybox-cmd`) and learn/play as required, or micro-configure stuff. You will not
notice much difference from a full Linux installation in a shell apart from missing
few things like systemd.


## Installation

If you have cloned the repository, then no further installation is required to run the utilities
in `src` directory which can be done directly off the repository. In the near future this will
also be published on `pypi.org`, so you will be able to install with `pip install ybox-py`.

As of now the following is required:

- clone the repo: `git clone https://github.com/sumwale/ybox.git`
- rootless podman or docker
  * for podman this needs installation of `podman` and `slirp4netns` packages (`buildah` optional),
    then setup /etc/subuid and /etc/subgid as noted here:
    [/etc/subuid and /etc/subgid configuration](https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md#etcsubuid-and-etcsubgid-configuration)
    (ubuntu, for example will also set up subuid/subgid for current user automatically;
     for ubuntu 24.04 you may also need an apparmor profile as noted in the docker docs next)
  * for docker follow the instructions in the official [docs](https://docs.docker.com/engine/security/rootless/)
- python version 3.9 or higher -- all fairly recent Linux distributions should satisfy this
  but still confirm with `python3 --version`
- install [simple-term-menu](https://pypi.org/project/simple-term-menu/) and
  [packaging](https://pypi.org/project/packaging/) either from your distribution
  repository, if available, else: `pip install simple-term-menu packaging` (obviously
      you will need `pip` itself to be installed which should be in your distribution
      repositories e.g. ubuntu/debian have it as `python3-pip`)

In the future, installer will take care of setting all of these up.

Now you can simply go to the repository and run the `ybox-create` and other utilities from
the `src` directory of the repository checkout. For convenience, you can symlink these to
your `~/.local/bin` directory which should be in PATH in modern Linux distributions:

```sh
ln -s <full path of checkout ybox directory>/src/ybox-* ~/.local/bin/
```

All the `ybox-*` utilities will show detailed help with the `-h`/`--help` option.


## Usage

The basic workflow consists of setting up one or more containers, installing/removing/...
packages in those containers and opening a shell into a container for more "direct" usage.

You can also destroy the containers, list them, see their logs, or restart them using
convenient utilities.

### Create a new ybox container

```sh
ybox-create
```

This will allow choosing from the available profiles. You can start with the basic `apps.ini`
to try it out. The container will have a name like `ybox-<distro>_<profile>` by default like
`ybox-arch_apps` for the `apps.ini` profile.

The `$HOME` directory of the container can be found in `~/.local/share/ybox/<container>/home`
e.g. `~/.local/share/ybox/ybox-arch_apps/home` for the above example.

When shared root directory is enabled (which is the default in the shipped profiles), then
it uses the common distribution path in `~/.local/share/ybox/SHARED_ROOTS/<distribution>`
by default i.e. `~/.local/share/ybox/SHARED_ROOTS/arch` for the Arch Linux guests.

For more advanced usage, you can copy from the available profiles in `src/ybox/conf/profiles`
into `~/.config/ybox/profiles`, then edit as required. The `basic.ini` profile lists
all the available options with detailed comments. There are a few more detailed examples
in the `src/ybox/conf/profiles/examples` directory.


### Install/uninstall/list/search packages

Install a new package with `ybox-pkg` like firefox below:

```sh
ybox-pkg install firefox
```

If you have created multiples containers, then this will allow you to choose one among
them for the installation. After the main package installation, it will also list
the optional dependencies of the installed package (only till second level) and allow you
to choose from among them which may add additional features to the package.

The installation will also create wrapper desktop files in `~/.local/share/applications`
and executables in `~/.local/bin` with man pages linked in `~/.local/share/man` so you can execute
the newly install application binaries from your desktop environment's application menu and/or
from command-line having corresponding man pages.

Likewise, you can uninstall all the changes (including the optional packages chosen before):

```sh
ybox-pkg uninstall firefox
```

List the explicitly installed packages using `ybox-pkg`:

```sh
ybox-pkg list
```
This will show the chosen dependent packages in addition to the explicitly installed ones.

```sh
ybox-pkg list -a
```
This will list all the distribution packages in the container including those not installed
by `ybox-pkg` (either installed in the base image, or installed later using the distribution
    package manager directly) -- combine with `-a` to also list all dependent packages.

```sh
ybox-pkg list -o
```
To show more details of the packages (combine with -a/-o as required):
```sh
ybox-pkg list -o
```

Search the repositories for packages with names matching search terms:

```sh
ybox-pkg search intellij
```

Search the repositories for packages with names or descriptions matching search terms:

```sh
ybox-pkg search intellij -a
```

You can also restrict the search to full word matches (can be combined with `-a`):

```sh
ybox-pkg search intellij -w
```


### List the available containers

```sh
ybox-ls
```

will list the active ybox containers

```sh
ybox-ls -a
```

will list all ybox containers including stopped ones


### Destroy a container

```sh
ybox-destroy ybox-arch_apps
```

Will destroy the `apps` container created in the example before. This does not delete the
$HOME files, nor does it delete the shared root directory (if enabled). Hence, if you create
a new container having the same shared root, then it will inherit everything installed
previously. Likewise, if you create the container with the same profile again, then it
will also have the $HOME as before if you do not explicitly delete the directories
in `~/.local/share/ybox`.


**NOTE:** an auto-complete file for fish shell has been provided in
`src/ybox/conf/completions/ybox.fish`, so you can link that to your fish config:
```sh
ln -s <full path of checkout ybox directory>/src/ybox/conf/completions/ybox.fish ~/.config/fish/conf.d/
```
This will allow auto complete for ybox container names, profiles among others.
Auto-complete for bash/zsh will be added in the future.


### Running a command in a container

The `ybox-cmd` runs `/bin/bash` in the container by default:

```sh
ybox-cmd ybox-arch_apps
```

You can run other commands instead of bash shell, but if those commands require options
starting with a hyphen, then first end the options to `ybox-cmd` with a double hyphen:

```sh
ybox-cmd ybox-arch_apps -- ls -l
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
ybox-logs ybox-arch_apps
```

Follow the logs like `tail -f`:

```sh
ybox-logs ybox-arch_apps -f
```

In the shipped profiles, the container logs go to `~/.local/share/ybox/<container>/logs/`
directory instead of polluting your journald logs as the docker/podman do by default.
You can delete old log files there safely if they start taking a lot of disk space.


### Restart a container

A container may get stopped after a reboot if systemd/... is not configured to auto-start
the docker/podman containers. Or you can explicitly stop a container using docker/podman.
You can check using `ybox-ls -a` and restart any stopped containers as below:

```sh
ybox-restart ybox-arch_apps
```


### Auto-starting containers

Containers can be auto-started as per the usual way for rootless docker/podman services.
This is triggered by systemd on user login which is exactly what we want for ybox
containers so that the container applications are available on login and are stopped on
session logout. For docker the following should suffice:

```sh
systemctl --user enable docker
```

See [docker docs](https://docs.docker.com/engine/security/rootless/#daemon) for details.

For podman you will need to explicitly generate systemd service file for each container and
copy to your systemd configuration directory since podman does not use a background daemon.
For the `ybox-arch_apps` container in the examples before:

```sh
mkdir -p ~/.config/systemd/user/
podman generate systemd --name ybox-arch_apps > ~/.config/systemd/user/container-ybox-arch_apps.service
systemctl --user enable container-ybox-arch_apps.service
```


## Development

Virtual environment setups have been provided for consistent development, test and build
with multiple python versions. The minimum python version required is 3.9 and tests are
run against all major python versions higher than that (i.e. 3.10, 3.11, 3.12 and others
in future).

As of now pyenv with venv is the actively maintained one which can be used for development
with IDEA/PyCharm, running tests against all supported python versions using `tox` etc.
While conda environment setup scripts are still provided, they are no longer maintained.

### pyenv with venv

Scripts to set up a pyenv with venv environment for a consistent development and build have
been provided in the `pyenv` directory which creates a `venv` environment in `.venv` directory
of the checkout.

If you do not have `pyenv` installed and configured, then you can install it using:

```sh
pyenv/install.sh
```

**NOTE:** this script will delete any existing `pyenv` artifacts in `$HOME/.pyenv`, so use
it only if you have never installed `pyenv` before.

The script will try to handle installation of required packages on most modern Linux
distributions (Ubuntu/Debian, Fedora, Arch Linux, OpenSUSE, macOS with homebrew), but if
yours is a different one, then check [pyenv wiki](https://github.com/pyenv/pyenv/wiki) or
your distribution docs/forums.

Next you can install the required python versions and venv environment:

```sh
pyenv/setup-venv.sh
```

Finally, you can activate it in bash/zsh:

```sh
source pyenv/activate.sh
source .venv/bin/activate
```

Or in fish shell:

```
source pyenv/activate.fish
source .venv/bin/activate.fish
```

**NOTE:** while the pyenv installation and venv set up needs to be done only once, the last
steps of `source` of the two files will need to be done for every shell. Hence, you can consider
placing those in your bashrc/zshrc or fish conf.d so that they get applied in every interactive
shell automatically.

You can open the checkout directory as an existing project in Intellij IDEA/PyCharm and then
add Python SDK (File -> Project Settings -> Project -> SDK -> Add Python SDK...).
Choose an existing environment in Virtualenv environment and select the
`<checkout dir>/.venv/bin/python3` for the interpreter.


### Conda

**NOTE:** this set up is no longer actively maintained.

This set up does not support multiple python environments as required by `tox` but
should be fine for development, IDE and running tests using `run-tests.sh`.

Scripts to set up a conda environment appropriate for the project have been provided
in the 'conda' directory which creates an environment in 'conda/.conda' directory
of the checkout. To set it up run:

```sh
conda/setup-conda.sh
```

Then you can activate it in bash:

```sh
source conda/activate-conda.bash
```

Or in fish shell:

```
source conda/activate-conda.fish
```

Script for zsh has also been provided:

```
source conda/activate-conda.zsh
```

You can open the checkout directory as an existing project in Intellij IDEA/PyCharm and then
add Python SDK (File -> Project Settings -> Project -> SDK -> Add Python SDK...).
Choose an existing environment in Conda environment where the path to conda should already
be selected correctly (`<checkout dir>/conda/.conda/bin/conda`) while for interpreter
choose `<checkout dir>/conda/.conda/envs/ybox/bin/python3`.

### Running the test suite

Once pyenv+venv set up is working, you can run the entire test suite and other checks
using `tox` in the checkout directory, or `tox -p` for parallel run. It will run with
all supported python versions (i.e. from 3.9 onwards).

There is also a simple script `run-tests.sh` in the top-level directory which can be used
to run just the tests with the current python version. This will skip other stuff like
`pyright`, for example, which is invoked by `tox`.

See `tox` and `unittest` documentation for more details like running individual tests.
