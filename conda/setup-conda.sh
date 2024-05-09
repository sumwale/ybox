#!/usr/bin/env bash

set -e

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
  os_code=Linux
elif [[ "$OSTYPE" == "darwin"* ]]; then
  os_code=MacOSX
fi
installer=Miniforge3-$os_code-$(uname -m).sh
url=https://github.com/conda-forge/miniforge/releases/latest/download/$installer

if type aria2c >/dev/null 2>/dev/null; then
  aria2c -x8 -j8 -s8 -k1M $url
else
  curl -L $url -o $installer
fi

conda_env="$SCRIPT_DIR/.conda"
rm -rf "$conda_env"
bash $installer -b -p "$conda_env"
rm -f $installer
export PATH="$conda_env/bin:$PATH"
source "$conda_env/etc/profile.d/conda.sh"

conda config --set solver libmamba --set changeps1 no --set channel_priority disabled
conda config --append channels anaconda
conda env create -f "$SCRIPT_DIR/ybox-conda.yaml"
conda clean -ay
