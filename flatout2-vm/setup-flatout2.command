#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ "$(/usr/bin/uname -s)" != Darwin || "$(/usr/bin/uname -m)" != arm64 ]]; then
  echo 'Setup requires an Apple Silicon Mac.' >&2
  exit 1
fi
source ./bootstrap.sh
if ! command -v brew >/dev/null 2>&1 && [[ -x /opt/homebrew/bin/brew ]]; then
  export PATH="/opt/homebrew/bin:$PATH"
fi
ensure_prerequisites
"$PYTHON" ./flatout2_vm.py setup "$@"
