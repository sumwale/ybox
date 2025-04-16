mkdir -p "$HOME/.pyenv"
export PYENV_ROOT="$HOME/.pyenv"
[ -d "$PYENV_ROOT/bin" ] && export PATH="$PATH:$PYENV_ROOT/bin"
if type pyenv >/dev/null 2>/dev/null; then
  eval "$(pyenv init - bash)"
fi
