mkdir -p "$HOME/.pyenv"
set -gx PYENV_ROOT "$HOME/.pyenv"
set -g fish_user_paths "$PYENV_ROOT/bin" $fish_user_paths
if type pyenv >/dev/null 2>/dev/null
  pyenv init - fish | source
end
