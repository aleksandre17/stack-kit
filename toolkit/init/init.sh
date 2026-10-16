#!/usr/bin/env bash
# stack-kit init — bash entry (calls PowerShell implementation when available)
set -euo pipefail
PKG="$(cd "$(dirname "$0")/../.." && pwd)"
TARGET="${1:-}"
INIT_PS1="$PKG/toolkit/init/Invoke-ProjectInit.ps1"
shift || true

if command -v powershell.exe >/dev/null 2>&1; then
  args=(-ExecutionPolicy Bypass -File "$INIT_PS1")
  [[ -n "$TARGET" ]] && args+=(-ProjectRoot "$(cd "$TARGET" && pwd)")
  args+=("$@")
  exec powershell.exe "${args[@]}"
fi

# Fallback: scaffold + seed + compose (no nginx / gitignore merge)
SCAFFOLD="$PKG/scaffold"
ROOT="${TARGET:-$(pwd)}"
while [[ -n "$ROOT" && "$ROOT" != "/" ]]; do
  [[ -f "$ROOT/stack-kit.json" ]] && break
  ROOT="$(dirname "$ROOT")"
done
[[ -f "$ROOT/stack-kit.json" ]] || ROOT="$(cd "$PKG/../.." && pwd)"

export STACK_KIT_PROJECT_ROOT="$ROOT"
export STACK_KIT_KIT_ROOT="$PKG"

echo ""
echo "  stack-kit init (bash) → $ROOT"
PY="$(command -v python3 || command -v python)"
"$PY" -B "$PKG/cli/stack_kit.py" extend --init --root "$ROOT"

copy_seed() {
  local ex="$1" tg="$2"
  [[ -f "$ROOT/$ex" ]] || return 0
  [[ -f "$ROOT/$tg" ]] && return 0
  mkdir -p "$(dirname "$ROOT/$tg")"
  cp "$ROOT/$ex" "$ROOT/$tg"
  echo "  [OK]   $tg ← $ex"
}

echo ""
echo "  ▸ Seed ops/config (manifest modules)"
export PYTHONPATH="$PKG${PYTHONPATH:+:$PYTHONPATH}"
python3 "$PKG/lib/ci_prepare.py" || py -3 "$PKG/lib/ci_prepare.py" || echo "  [warn] seed failed — run: python3 kits/stack-kit/lib/ci_prepare.py"

if [[ ! -f "$ROOT/ops/compose/catalog.json" && -f "$SCAFFOLD/ops/compose/catalog.full.json" ]]; then
  mkdir -p "$ROOT/ops/compose"
  cp "$SCAFFOLD/ops/compose/catalog.full.json" "$ROOT/ops/compose/catalog.json"
  echo "  [OK]   ops/compose/catalog.json (full)"
fi

echo ""
echo "  ▸ compose-gen"
python3 "$PKG/compose/build.py" || echo "  [warn] compose-gen failed"

echo ""
echo "  Next: fill the module env files and ops/deploy/targets.json, then: ./tools/stack-kit.sh compose-gen"
echo ""
