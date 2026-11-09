#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3 is required. On an unmanaged Mac: brew install python'
  exit 1
fi
python3 ./flatout2_vm.py start "$@"
