if [ -e "$HOME/.pyenv" ]
  set -gx PYENV_ROOT "$HOME/.pyenv"
  set -g fish_user_paths "$PYENV_ROOT/bin" $fish_user_paths
  pyenv init - | source
end
