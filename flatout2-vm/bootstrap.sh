#!/bin/bash
# Source from the setup launcher. Never change host tools from the Play launcher.

python_is_supported() {
  "$1" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1
}

utm_is_supported() {
  local version major minor patch
  version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' \
    /Applications/UTM.app/Contents/Info.plist 2>/dev/null) || return 1
  IFS=. read -r major minor patch <<< "$version"
  [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ && "$patch" =~ ^[0-9]+$ ]] || return 1
  (( major > 5 || (major == 5 && (minor > 0 || patch >= 8)) ))
}

ensure_prerequisites() {
  local repository prefix need_python=0 need_utm=0
  PYTHON=python3
  if ! command -v brew >/dev/null 2>&1; then
    echo 'Homebrew is required. Install it from https://brew.sh, then run setup again.' >&2
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1 || ! python_is_supported python3; then
    need_python=1
  fi
  utm_is_supported || need_utm=1
  if (( !need_python && !need_utm )); then
    return 0
  fi
  repository=$(brew --repository) || return 1
  if [[ "$repository" == *'.homebrew-is-managed-by-nix'* || "$repository" == /nix/store/* ]]; then
    echo 'Missing/outdated prerequisites on a Nix-managed Homebrew installation.' >&2
    echo 'Update UTM to 5.0.8+ and Python to 3.11+ through your manager, then retry.' >&2
    return 1
  fi
  echo 'Setup uses Homebrew to install missing Python 3.11+ and UTM 5.0.8+.'
  echo 'Homebrew may request macOS authorization. Do not run this launcher with sudo.'
  if (( need_python )); then
    brew install python || return 1
    prefix=$(brew --prefix python) || return 1
    PYTHON="$prefix/bin/python3"
    python_is_supported "$PYTHON" || {
      echo 'Homebrew Python is still below 3.11; update your Homebrew catalog and retry.' >&2
      return 1
    }
  fi
  if (( need_utm )); then
    if brew list --cask utm >/dev/null 2>&1; then
      brew upgrade --cask utm || return 1
    else
      brew install --cask utm || return 1
    fi
    utm_is_supported || {
      echo 'UTM is still below 5.0.8 or missing from /Applications; update Homebrew and retry.' >&2
      return 1
    }
  fi
}
