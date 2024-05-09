# source this file

SCRIPT_DIR=$(cd "$(dirname "${(%):-%x}")" && pwd)

source "$SCRIPT_DIR/.conda/etc/profile.d/conda.sh"
conda activate ybox
