# source this file

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

source "$SCRIPT_DIR/.conda/etc/profile.d/conda.sh"
conda activate ybox
