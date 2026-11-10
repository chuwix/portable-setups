#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
source ./bootstrap.sh
if ! command -v brew >/dev/null 2>&1 && [[ -x /opt/homebrew/bin/brew ]]; then
  export PATH="/opt/homebrew/bin:$PATH"
fi
ensure_prerequisites
"$PYTHON" ./flatout2_vm.py install-game "$@"
