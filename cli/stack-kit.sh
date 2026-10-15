#!/bin/bash
set -euo pipefail
PKG="$(cd "$(dirname "$0")/.." && pwd)"
export STACK_KIT_KIT_ROOT="$PKG"
# One discovery: the project library's (it also carries legacy names to the current ones).
# shellcheck source=../lib/project.sh
source "$PKG/lib/project.sh"
ROOT="$(stack_kit_find_project_root)" || { echo "ERROR: $(_stack_kit_identity manifestFilename) not found"; exit 1; }
export STACK_KIT_PROJECT_ROOT="$ROOT"
CMD="${1:-help}"
shift || true

case "$CMD" in
  init) exec bash "$PKG/toolkit/init/init.sh" "$@" ;;
  validate) export PYTHONPATH="$PKG${PYTHONPATH:+:$PYTHONPATH}"; exec python3 "$PKG/lib/validate_manifest.py" ;;
  migrate) export PYTHONPATH="$PKG${PYTHONPATH:+:$PYTHONPATH}"; exec python3 "$PKG/lib/migrate_manifest.py" "$@" ;;
  vscode-gen) export PYTHONPATH="$PKG${PYTHONPATH:+:$PYTHONPATH}"; exec python3 "$PKG/lib/vscode_gen.py" "$@" ;;
  compose-gen) exec python3 "$PKG/compose/build.py" ;;
  nginx-gen) exec python3 "$PKG/adapters/render_nginx.py" ;;
  stack-deploy) exec bash "$PKG/toolkit/deploy/stack-remote.sh" "$@" ;;
  infra)
    if [[ $# -gt 0 ]]; then
      if command -v pwsh >/dev/null 2>&1; then
        exec pwsh -NoProfile -ExecutionPolicy Bypass -File "$PKG/toolkit/infra/Invoke-Infra.ps1" "$@"
      fi
      if command -v powershell.exe >/dev/null 2>&1; then
        exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PKG/toolkit/infra/Invoke-Infra.ps1" "$@"
      fi
      echo "ERROR: pwsh or powershell required for: stack-kit infra $*"
      exit 1
    fi
    exec bash "$PKG/toolkit/infra/ensure-prereqs.sh"
    ;;
  stack) exec bash "$PKG/toolkit/stack/compose.sh" "$@" ;;
  *)
    exec powershell -ExecutionPolicy Bypass -File "$ROOT/tools/stack-kit.ps1" "$CMD" "$@" 2>/dev/null \
      || exec powershell -ExecutionPolicy Bypass -File "$PKG/cli/stack-kit.ps1" "$CMD" "$@"
    ;;
esac
