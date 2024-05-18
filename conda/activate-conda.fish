# source this file

set SCRIPT_DIR (dirname (realpath (status -f)))

source "$SCRIPT_DIR/.conda/etc/fish/conf.d/conda.fish"
conda activate ybox
