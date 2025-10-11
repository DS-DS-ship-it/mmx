#!/usr/bin/env bash
set -euo pipefail

_usage(){ echo "Usage:
  source scripts/env_arch.sh <target-triple>
  scripts/env_arch.sh <target-triple> -- <command ...>"; }

_env_for_target(){
  t="${1:-}"
  unset PKG_CONFIG PKG_CONFIG_PATH PKG_CONFIG_DIR PKG_CONFIG_SYSROOT_DIR
  case "$(uname -s)/$(uname -m)/$t" in
    Darwin/arm64/aarch64-apple-darwin|Darwin/arm64/)
      export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
      export PKG_CONFIG="/opt/homebrew/bin/pkg-config"
      export PKG_CONFIG_PATH="/opt/homebrew/lib/pkgconfig:/opt/homebrew/opt/libffi/lib/pkgconfig"
      ;;
    Darwin/arm64/x86_64-apple-darwin)
      if [[ -x /usr/local/bin/pkg-config ]]; then
        export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
        export PKG_CONFIG="/usr/local/bin/pkg-config"
        export PKG_CONFIG_PATH="/usr/local/lib/pkgconfig:/usr/local/opt/libffi/lib/pkgconfig"
      fi
      ;;
    *)
      :
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  _env_for_target "${1:-}"
  return 0 2>/dev/null || exit 0
fi

[[ $# -ge 3 ]] || { _usage; exit 1; }
target="$1"; shift
[[ "${1:-}" == "--" ]] || { _usage; exit 1; }
shift

_env_for_target "$target"

exec "$@"
