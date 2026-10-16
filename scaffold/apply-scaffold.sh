#!/bin/bash
# Copy stack-kit/scaffold → project root (merge; do not overwrite real secrets)
set -euo pipefail
SCAFFOLD="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-$(cd "$SCAFFOLD/../../.." && pwd)}"

never_overwrite() {
  local rel="$1"
  local f="$TARGET/$rel"
  [[ -f "$f" ]] || return 1
  case "$rel" in
    stack-kit.json) return 0 ;;
    ops/config/frontend/.env.dev|ops/config/frontend/.env.prod|ops/config/frontend/nginx.env) return 0 ;;
    ops/config/backend/.env.dev|ops/config/backend/.env.prod|ops/config/backend/google-credentials.json) return 0 ;;
    ops/config/ssh/id_rsa|ops/config/ssh/id_ed25519|ops/config/ssh/config) return 0 ;;
  esac
  return 1
}

copy_tree() {
  local src="$1" rel="${2:-}"
  local name dest relpath
  for name in "$src"/*; do
    [[ -e "$name" ]] || continue
    base="$(basename "$name")"
    [[ -z "$rel" && "$base" =~ ^(README.md|apply-scaffold\.(ps1|sh))$ ]] && continue
    relpath="${rel:+$rel/}$base"
    if [[ -d "$name" ]]; then
      mkdir -p "$TARGET/$relpath"
      copy_tree "$name" "$relpath"
    else
      if never_overwrite "$relpath"; then
        echo "  [skip] $relpath (exists)"
        continue
      fi
      if [[ -f "$TARGET/$relpath" && ! "$relpath" =~ \.example$ && "$relpath" != */README.md && "$base" != .gitkeep && "$base" != .gitignore ]]; then
        echo "  [skip] $relpath (exists)"
        continue
      fi
      mkdir -p "$(dirname "$TARGET/$relpath")"
      cp "$name" "$TARGET/$relpath"
      echo "  [OK]   $relpath"
    fi
  done
}

if [[ ! -f "$TARGET/ops/compose/catalog.json" && -f "$SCAFFOLD/ops/compose/catalog.minimal.json" ]]; then
  mkdir -p "$TARGET/ops/compose"
  cp "$SCAFFOLD/ops/compose/catalog.minimal.json" "$TARGET/ops/compose/catalog.json"
  echo "  [OK]   ops/compose/catalog.json (from catalog.minimal.json)"
fi

echo ""
echo "  stack-kit scaffold → $TARGET"
echo ""
copy_tree "$SCAFFOLD"
echo ""
echo "  Next: .\tools\stack-kit.ps1 init   (recommended)"
echo "  See kits/stack-kit/scaffold/README.md"
echo ""
