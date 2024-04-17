Create and manage docker/podman containers hosting different Linux
distribution images. Manage their packages and applications directly
from your host machine and easily configure the containers with a
simple INI files. It allows for set up of various aspects of
the container including support for X11, Wayland, audio, video acceleration,
NVIDIA, dbus among others. It also allows controlling various parameters
of the container including directories to be shared, logging etc.

Special emphasis is given on security where users can choose to lock down
or open up the container as required with reasonable defaults out of the
zbox. There is no sharing of HOME or no privileged mode container unless
explicitly configured.

Expected usage is for users to group similar applications in a container
and separate out containers depending on different needs like higher/lower
security, features off to minimum required for those set of applications.

As a convenience it provides for some features to make life easier like
sharing of your application configuration files automatically
(eg .bashrc, .vimrc etc.), sharing of 'root' system directories
like /usr among containers to reduce disk and memory usage, automatic
installation and configuration of applications. Separate utilities
for package management across containers are provided with the idea
being that the whole setup feels like a native package manager on
isolated containers having access to whole slew of applications from
huge repositories like Arch Linux with AUR.
