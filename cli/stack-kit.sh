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
  validate) export PYTHONPATH="$PKG${PYTHONPATH:+:$PYTHONPATH}"; stack_kit_python "$PKG/lib/validate_manifest.py" "$@" ;;
  migrate) export PYTHONPATH="$PKG${PYTHONPATH:+:$PYTHONPATH}"; stack_kit_python "$PKG/lib/migrate_manifest.py" "$@" ;;
  vscode-gen) export PYTHONPATH="$PKG${PYTHONPATH:+:$PYTHONPATH}"; stack_kit_python "$PKG/lib/vscode_gen.py" "$@" ;;
  compose-gen) stack_kit_python "$PKG/compose/build.py" ;;
  nginx-gen) stack_kit_python "$PKG/adapters/render_nginx.py" ;;
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
    # Every other verb is the PowerShell CLI's: pwsh on any platform, Windows PowerShell where only it
    # exists. (`exec` does not return, so a `|| fallback` after it could never run.)
    ps="$(command -v pwsh || command -v powershell.exe || command -v powershell || true)"
    [[ -n "$ps" ]] || { echo "ERROR: pwsh (PowerShell 7) is required for: stack-kit $CMD" >&2; exit 1; }
    exec "$ps" -NoProfile -ExecutionPolicy Bypass -File "$PKG/cli/stack-kit.ps1" "$CMD" "$@"
    ;;
esac
