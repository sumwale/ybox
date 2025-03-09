## Introduction

Create and manage podman/docker containers hosting different Linux
distribution images. Manage their packages and applications directly
from your host machine and easily configure the containers with
simple INI files. It allows for set up of various aspects of
the container including support for X11, Wayland, audio, video acceleration,
NVIDIA, dbus among others. It also allows controlling various parameters
of the container including directories to be shared, logging etc.

Special emphasis is given on security where users can choose to lock down
or open up the container as required with reasonable defaults out of the
box. There is no sharing of HOME or no privileged mode container. This sets
it apart from other similar solutions like distrobox/toolbx and the reason
for starting this project since those other solutions don't care about
security/sandboxing at all and share the entire HOME while running the
containers in privileged mode. The other problem with those solutions is that
the shared HOME means that the user's configuration dot files also get shared
and can cause all kinds of trouble where container apps can overwrite
with their own versions (especially for updated apps in the containers)
breaking the app in the host system. It is, however, possible to share the
entire HOME if user really wants but that needs to be explcitly configured
in the ini profile.

Expected usage is for users to group similar applications in a container
and separate out containers depending on different needs like higher/lower
security, features off to minimum required for those set of applications.


## Features

- simple creation of podman or docker containers hosting Linux distributions (Arch Linux, Ubuntu
  and Debian supported currently) using `ybox-create` with interactive menus
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

If you create an Arch Linux based container (which probably hosts the largest repository of Linux
applications with its AUR), then you will have its applications to run in the host OS.
So, for example, if you want to run the latest and greatest Intellij IDEA community, all you need
to do is:

```sh
# create an Arch Linux based container and generate systemd service file (if possible)
ybox-create arch
# then select an appropriate built-in profile e.g. "dev.ini" from the menu

# then install the Arch package in the container
ybox-pkg install intellij-idea-community-edition
```

This will automatically create a wrapper desktop file that launches from the container, so
you can simply launch it from your desktop environment's applications as usual.

In this way this acts as a complete replacement of flatpak/snap while being able to choose
from way bigger software repositories, and with applications configured the way they are
supposed to be in the original Linux distribution.
The big difference being that these are just containers where you can open a shell
(using `ybox-cmd`) and learn/play as required, or micro-configure stuff. The shell will
behave quite like a full Linux installation apart from missing system-level stuff like systemd.


## Installation

First install the requirements:

- Python version 3.9 or higher. All recent Linux distributions should satisfy
  this but still confirm with `python3 --version`.
- Rootless podman or docker. Podman is recommended as it works out of the box for most
        distributions and container runs as normal non-root user unlike docker that
        needs to run as root in the container that may break some applications.
  * For podman this needs installation of `podman` and `slirp4netns` (or `passt` with
          podman >= 5) packages. Then setup /etc/subuid and /etc/subgid as noted here:
    [/etc/subuid and /etc/subgid configuration](https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md#etcsubuid-and-etcsubgid-configuration).
    Most distributions will set up subuid/subgid for current user automatically
    and rootless podman works out of the box after installation (tested on Ubuntu,
            Arch and Debian). Check with `podman unshare cat /proc/self/uid_map` which
    should show an output like:
    ```
         0       1000          1
         1     100000      65536
    ```
    where `1000` is the current user's ID (output of `id -u`).
  * For docker follow the instructions in the official [docs](https://docs.docker.com/engine/security/rootless/).

Finally install the `ybox` package for the current user using `pip` (`pip` is installed
    on most Linux distributions by default, or install from your distribution's
    repository e.g. `python3-pip` for Debian/Ubuntu based distros, `python-pip` on Arch):

```sh
pip install ybox --user
```

Note that newer versions of `pip` disallow installing packages directly and instead
require you to install in a custom virtual environment which can be done manually
(e.g. bash/zsh: `python3 -m venv ybox-venv && source ybox-env/bin/activate`,
 fish: `python3 -m venv ybox-venv && source ybox-env/bin/activate.fish`)
or automatically using `pipx`. Alternatively you can add `--break-system-packages`
flag to the `pip` command above or add it globally for all future packages using
`python3 -m pip config set global.break-system-packages true`. This alternative
approach works well for `ybox` which has a very minimal set of dependencies which will
not conflict with system packages (rather work with whatever system version is installed),
but if you prefer keeping the installation separate then use `pipx` or
a manual virtual environment.

Now you can run the `ybox-create` and other utilities that are normally installed
in your `~/.local/bin` directory which should be in PATH for modern Linux distributions.
If not, then add it to your PATH in your `.bashrc` (for bash) or the configuration
file of your login shell.

All the `ybox-*` utilities will show detailed help with the `-h`/`--help` option.


## Usage

The basic workflow consists of setting up one or more containers, installing/removing/...
packages in those containers and opening a shell into a container for more "direct" usage.

You can also destroy the containers, list them, see their logs, or restart them using
convenient utilities.

All the commands support podman or docker configured in rootless mode. When using docker, its
`dockerd` daemon needs to be running in background as the current user, while for podman
there is no such requirement. Additionally podman will run applications in the container using
the same user/group as the current user on the host, while docker needs to use the root user in
the container due to missing support of `--userns=keep-id` option.

Consequently podman is the recommended container manager for ybox containers. Its rootless mode
also works out of the box in most modern linux distributions, unlike docker that needs some
configuration to setup its user-mode rootless daemon.

The commands search for `/usr/bin/podman` followed by `/usr/bin/docker` for the container manager
executable. This can be overridden using the `YBOX_CONTAINER_MANAGER` environment variable
to point to the full path of the podman or docker executable.

### Create a new ybox container

```sh
ybox-create
```

By default this will also generate a user systemd service if possible (add `-S` or
  `--skip-systemd-service` option to skip creation of a user systemd service).
This will allow choosing from supported distributions, then from the available profiles.
You can start with the Arch Linux distribution and `apps.ini` profile to try it out. The container
will have a name like `ybox-<distribution>_<profile>` by default like `ybox-arch_apps` for the
`apps.ini` profile using Arch Linux distribution.

The `$HOME` directory of the container can be found in `~/.local/share/ybox/<container>/home`
e.g. `~/.local/share/ybox/ybox-arch_apps/home` for the above example.

When shared root directory is enabled (which is the default in the shipped profiles), then
it uses the common distribution path in `~/.local/share/ybox/SHARED_ROOTS/<distribution>`
by default e.g. `~/.local/share/ybox/SHARED_ROOTS/arch` for the Arch Linux guests.

For more advanced usage, you can copy from the available profiles in `src/ybox/conf/profiles`
into `~/.config/ybox/profiles`, then edit as required. The `basic.ini` profile lists
all the available options with detailed comments.

Note that when using podman, the container will use the same user/group as the current user
on the host, while if docker is being used then the container will use the root user.
This is because of missing support for `--userns=keep-id` in docker that allows mapping the
host user to the same user in the container when using podman. This means that if some application
does not run properly as root, then you cannot run it when using docker unless you explicitly
`sudo/su` to the host user in the container command. However, running as host user when running
rootless docker will map to a different user ID in the host (as specified in `/etc/subuid` on the
host) so files shared with the host, including devices like those in `/dev/dri`, will cause
permission issues that can hinder or break the application. Hence it is recommended to
just install podman (even if you already have docker installed) which works out of the
box in rootless mode in all tested distributions.


### Package management: install/uninstall/list/search/...

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
ybox-pkg list -v
```

List all the files installed by the package:
```sh
ybox-pkg list-files firefox
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

Show detailed information for an installed package:
```sh
ybox-pkg info firefox
```

Show detailed information for any package in the available repositories:
```sh
ybox-pkg info firefox -a
```

Clean package cache, temporary downloads etc:
```sh
ybox-pkg clean
```
Add `-q` option to answer yes for any questions automatically if all your containers use
the same shared root.

Mark a package as explicitly installed (also registers with `ybox-pkg` if not present):
```sh
ybox-pkg mark firefox -e
```

Mark a package as a dependency of another (also registers with `ybox-pkg` if not present):
```sh
ybox-pkg mark qt5ct -d zoom  # mark qt5ct as an optional dependency of zoom
```

Repair package installation after a failure or interrupt:
```sh
ybox-pkg repair
```

More extensive repair of package installation including reinstallation of all packages:
```sh
ybox-pkg repair --extensive
```

All the `ybox-pkg` subcommands will show detailed help with `-h/--help` option e.g.
`ybox-pkg list --help`.


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
`$HOME` files, nor does it delete the shared root directory (if enabled). Hence, if you create
a new container having the same shared root, then it will inherit everything installed
previously. Likewise, if you create the container with the same profile again, then it
will also have the `$HOME` as before if you do not explicitly delete the directories
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
`$HOME` directory by default, so you should see the same bash shell configuration as in your
host. These are linked in read-only mode, so if you want to change these auto-linked
configuration files inside the container, then you will need to create a copy from the symlink
first (but then it will lose the link from the host `$HOME`).

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
directory instead of polluting your journald logs as the podman/docker do by default.
You can delete old log files there safely if they start taking a lot of disk space.


### Restart a container

A container may get stopped after a reboot if systemd/... is not configured to auto-start
the podman/docker containers. Or you can explicitly stop a container using podman/docker.
You can check using `ybox-ls -a` and restart a stopped container as below:

```sh
ybox-control start ybox-arch_apps
```

The `ybox-control` script also allows for other actions `stop`, `restart` and `status`
for a ybox container. See the full set of options with `ybox-control -h/--help`.


### Auto-starting containers

Containers can be auto-started as per the usual way for rootless podman/docker services.
This is triggered by systemd on user login which is exactly what is required for ybox
containers so that the container applications are available on login and are stopped on
session logout. All the tested Linux distributions support this and provide for user
systemd daemon on user login.

The `ybox-create` command  autogenerates the systemd service file (in absence of `-S` or
  `--skip-systemd-service` option) which is also removed by `ybox-destroy` automatically.
The name of the generated service is `ybox-<NAME>` where `<NAME>` is the name of the
container if `<NAME>` does not start with `ybox-` prefix, else it is just `<NAME>`.

With a user service installed, the `systemctl` commands can be used to control the
ybox container (`<SERVICE_NAME>` is `ybox-<NAME>/<NAME>` mentioned above):

```sh
systemctl --user status <SERVICE_NAME>  # show status of the service
systemctl --user stop <SERVICE_NAME>    # stop the service
systemctl --user start <SERVICE_NAME>   # start the service
```

If your Linux distribution does not use systemd, then the autostart has to be handled
manually as per the distribution's preferred way. For instance an appropriate desktop
file can be added to `~/.config/autostart` directory to start a ybox container on
graphical login, though performing a clean stop can be hard with this approach.
Note that the preferred way to start/stop a ybox container is using the `ybox-control`
command rather than directly using podman/docker.


## Development

Virtual environment setup have been provided for consistent development, test and build
with multiple python versions. The minimum python version required is 3.9 and tests are
run against all major python versions higher than that (i.e. 3.10, 3.11, 3.12, 3.13 and
    others in future).

The setup uses pyenv with venv which can be used for development with IDEA/PyCharm/VSCode
or in terminal, running tests against all supported python versions using `tox` etc.
Scripts to set up a pyenv with venv environment have been provided in the `pyenv` directory
which creates a `venv` environment in `.venv` directory of the checkout.

If you do not have `pyenv` installed and configured, then you can install it using:

```sh
pyenv/install.sh
```

**NOTE:** this script will delete any existing `pyenv` artifacts in `$HOME/.pyenv`, so use
it only if you have never installed `pyenv` before.

The script will try to handle installation of required packages on most modern Linux
distributions (Ubuntu/Debian, Fedora, Arch Linux, OpenSUSE, homebrew), but if yours is a
different one, then check [pyenv wiki](https://github.com/pyenv/pyenv/wiki) or your
distribution docs/forums.

Next you can install the required python versions and venv environment:

```sh
pyenv/setup-venv.sh
```

Finally, you can activate it.

bash:

```sh
source pyenv/activate.bash
source .venv/bin/activate
```

zsh:

```sh
source pyenv/activate.zsh
source .venv/bin/activate
```

fish:

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

For using VSCode, ensure that the python extension from Microsoft and preferably the following
additional extensions are installed: autopep8, Flake8, isort, audoDocstring and
Python Environment Manager. The open the checkout directory and you should be good to go.


### Notes on writing tests

Tests have been categorized into two:
- in `tests/unit` directory: these have module/function/class level tests; convention is to
  use a separate test module for corresponding source module e.g. `test_state.py` for
  `ybox/state.py` module
- in `tests/functional` directory: these are end-to-end tests that invoke and check the
  top-level `ybox-*` utilities

All the existing tests use the `pytest` framework and new ones should do the same.
After adding new tests to the appropriate test directory run `code-check.sh` and
`tests-coverage.sh` scripts which should succeed and also see coverage report from latter.

**NOTE:** use mock only if absolutely necessary (e.g. for unexpected error
conditions that are difficult to simulate in tests or will cause other trouble).
For example the state database used is sqlite, but that is an internal detail and could
potentially change so mocking sqlite3 objects in tests for `ybox.state` module is a really
bad idea and one should just test for public API of `ybox.state`. On the other hand
checking for exceptions like `KeyboardInterrupt` can use mock since simulating them
otherwise is error-prone and can cause unwanted side-effects for other tests.


### Running the test suite

Once pyenv+venv set up is working, you can run the entire test suite and other checks
using `tox` in the checkout directory, or `tox -p` for parallel run. It will run with
all supported python versions (i.e. from 3.9 onwards). Tests are written using the `pytest`
test framework which will be installed along with other requirements by the `setup-venv.sh`
script (or you can explicitly use `requirements.txt` and install `tox` separately).

There is also a simple script `tests-coverage.sh` in the top-level directory which can be
used to run just the tests with the current python version and produce coverage report.
It accepts a single argument `-f` to run functional tests in addition to the unit tests,
else only unit tests are run with coverage. Any arguments afterwards are passed as such
to `pytest`. This will skip other stuff like `pyright`, for example, which is invoked by
`tox`. The lint and other related tools can be run explicitly using the `code-check.sh`
script in the top-level directory.

See `tox` and `pytest` documentation for more details like running individual tests.
