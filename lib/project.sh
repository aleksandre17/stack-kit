#!/bin/bash
# Project manifest resolution — package boundary.
#
# The manifest's NAME is not spelled here. It is declared once in lib/identity.json
# and projected into every runtime, so a rename is one edit and never an archaeology.

# Accepted manifest filenames, canonical first — read from the ONE declaration.
# Pure text parsing on purpose: this must work before python is known to exist.
_geostat_manifest_names() {
  local decl="${BASH_SOURCE[0]%/*}/identity.json"
  # No guessed default: a missing declaration is a broken kit, and a fallback
  # spelling here would be exactly the second home this file exists to remove.
  [[ -f "$decl" ]] || { echo "  ERROR: kit identity declaration missing: $decl" >&2; return 1; }
  sed -n 's/.*"manifestFilename"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$decl"
  sed -n '/"legacyManifestFilenames"[[:space:]]*:[[:space:]]*\[/,/\]/p' "$decl" \
    | grep -o '"[^"]*\.json"' | tr -d '"'
}

# First accepted manifest inside $1, or non-zero when the directory holds none.
_geostat_manifest_in() {
  local dir="$1" name
  while read -r name; do
    [[ -n "$name" && -f "$dir/$name" ]] && { echo "$dir/$name"; return 0; }
  done < <(_geostat_manifest_names)
  return 1
}

geostat_python() {
  if command -v python3 &>/dev/null; then
    if python3 -c "import sys" &>/dev/null 2>&1; then
      python3 "$@"
      return $?
    fi
  fi
  if command -v py &>/dev/null; then
    py -3 "$@"
  elif command -v python &>/dev/null; then
    python "$@"
  else
    echo "  ERROR: python not found (need python3, py, or python)" >&2
    return 127
  fi
}

_geostat_manifest_file() {
  local root="${GEOSTAT_PROJECT_ROOT:-}"
  if [[ -z "$root" ]]; then
    local dir="${1:-$(pwd)}"
    while [[ -n "$dir" && "$dir" != "/" ]]; do
      _geostat_manifest_in "$dir" && return 0
      dir="$(dirname "$dir")"
    done
    return 1
  fi
  _geostat_manifest_in "$root" && return 0
  # Declared root with no manifest yet: name the canonical target, not a guess.
  echo "$root/$(_geostat_manifest_names | head -1)"
}

_geostat_legacy_discovery() {
  [[ "${GEOSTAT_LEGACY_ROOT_DISCOVERY:-}" =~ ^(1|true|yes|on)$ ]]
}

# Git Bash / MSYS: Windows drive paths break PYTHONPATH in inline env (\U escapes).
geostat_normalize_unix_path() {
  local p="${1:-}"
  [[ -n "$p" ]] || return 1
  if [[ "$p" =~ ^[A-Za-z]:[/\\] ]]; then
    (cd "$p" && pwd) || echo "$p"
  else
    echo "$p"
  fi
}

geostat_find_project_root() {
  if [[ -n "${GEOSTAT_PROJECT_ROOT:-}" ]]; then
    geostat_normalize_unix_path "$GEOSTAT_PROJECT_ROOT"
    return 0
  fi
  local dir="${1:-$(pwd)}" mf
  while [[ -n "$dir" && "$dir" != "/" ]]; do
    if _geostat_manifest_in "$dir" >/dev/null; then
      geostat_normalize_unix_path "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  if _geostat_legacy_discovery; then
    dir="${1:-$(pwd)}"
    while [[ -n "$dir" && "$dir" != "/" ]]; do
      if [[ -d "$dir/secrets" || -d "$dir/ops/config" ]]; then
        if [[ -d "$dir/kits/geostat-kit" || -d "$dir/packages/geostat-kit" ]]; then
          geostat_normalize_unix_path "$dir"
          return 0
        fi
      fi
      dir="$(dirname "$dir")"
    done
  fi
  return 1
}

geostat_read_manifest_field() {
  local field="$1" default="${2:-}"
  if [[ -z "$default" && -n "${GEOSTAT_KIT_ROOT:-}" ]]; then
    default="$(PYTHONPATH="${GEOSTAT_KIT_ROOT}${PYTHONPATH:+:$PYTHONPATH}" geostat_python -c "
from lib.manifest_defaults import default_field
import sys
print(default_field(sys.argv[1]))
" "$field" 2>/dev/null || true)"
  fi
  local mf root
  mf="$(_geostat_manifest_file 2>/dev/null)" || { echo "$default"; return; }
  root="$(dirname "$mf")"
  geostat_python -c "
import json, sys
p = sys.argv[1]
f = sys.argv[2]
d = sys.argv[3]
with open(p, encoding='utf-8') as fh:
    m = json.load(fh)
keys = f.split('.')
v = m
for k in keys:
    if not isinstance(v, dict) or k not in v:
        print(d)
        sys.exit(0)
    v = v[k]
print(v if v is not None else d)
" "$mf" "$field" "$default" 2>/dev/null || echo "$default"
}

# Read an ARRAY-valued manifest field as newline-separated items (empty when absent,
# not an array, or no manifest). Generic companion to geostat_read_manifest_field.
geostat_read_manifest_list() {
  local field="$1" mf
  mf="$(_geostat_manifest_file 2>/dev/null)" || return 0
  geostat_python -c "
import json, sys
with open(sys.argv[1], encoding='utf-8') as fh:
    m = json.load(fh)
v = m
for k in sys.argv[2].split('.'):
    if not isinstance(v, dict) or k not in v:
        sys.exit(0)
    v = v[k]
if isinstance(v, list):
    for item in v:
        if item is not None and str(item).strip():
            print(str(item).strip())
" "$mf" "$field" 2>/dev/null || true
}

geostat_kit_package_root() {
  if [[ -n "${OPS_PACKAGE_ROOT:-}" ]]; then
    echo "$OPS_PACKAGE_ROOT"
    return 0
  fi
  if [[ -n "${GEOSTAT_KIT_ROOT:-}" ]]; then
    echo "$GEOSTAT_KIT_ROOT"
    return 0
  fi
  local proj rel pkg
  proj="$(geostat_find_project_root)" || return 1
  rel="$(geostat_read_manifest_field package)"
  pkg="$(cd "$proj" && cd "$rel" 2>/dev/null && pwd)"
  echo "$pkg"
}

geostat_kit_toolkit_bash() {
  echo "$(geostat_kit_package_root)/toolkit/bash"
}

geostat_kit_deploy_lib() {
  echo "$(geostat_kit_package_root)/toolkit/deploy"
}

geostat_kit_compose_catalog() {
  local proj
  proj="$(geostat_find_project_root)" || return 1
  echo "$proj/$(geostat_read_manifest_field compose.catalog)"
}

geostat_kit_sync_modules_path() {
  local proj
  proj="$(geostat_find_project_root)" || return 1
  echo "$proj/$(geostat_read_manifest_field compose.syncModules)"
}

# --- Module / secrets paths (manifest modules.*) ---

geostat_module_path() {
  local module_id="$1" proj rel
  proj="$(geostat_find_project_root)" || return 1
  rel="$(geostat_read_manifest_field "modules.${module_id}.path" "")"
  [[ -n "$rel" ]] || return 1
  echo "$proj/$rel"
}

geostat_secrets_module_name() {
  local module_id="$1" sm
  sm="$(geostat_read_manifest_field "modules.${module_id}.secretsModule" "$module_id")"
  echo "$sm"
}

geostat_secrets_dir_for_module() {
  local module_id="$1"
  echo "$(geostat_secrets_root)/$(geostat_secrets_module_name "$module_id")"
}

geostat_stack_compose_dir() {
  local proj rel
  proj="$(geostat_find_project_root)" || return 1
  rel="$(geostat_read_manifest_field stack.composeDir)"
  echo "$proj/$rel"
}

geostat_manifest_feature_enabled() {
  local name="$1" mf
  mf="$(_geostat_manifest_file 2>/dev/null)" || { echo "false"; return; }
  geostat_python -c "
import json, sys
m = json.load(open(sys.argv[1], encoding='utf-8'))
f = (m.get('features') or {}).get(sys.argv[2])
print('true' if f is True else 'false')
" "$mf" "$name" 2>/dev/null || echo "false"
}

# Secrets folder names from manifest modules (one per line)
geostat_module_id_for_role() {
  local role="$1" idx="${2:-0}" mf mid
  mf="$(_geostat_manifest_file 2>/dev/null)" || return 1
  mapfile -t _GEOSTAT_ROLE_IDS < <(geostat_python -c "
import json, sys
m = json.load(open(sys.argv[1], encoding='utf-8'))
role = sys.argv[2]
out = []
for mid, cfg in (m.get('modules') or {}).items():
    if not isinstance(cfg, dict):
        continue
    r = (cfg.get('role') or '').lower()
    if not r and cfg.get('type') == 'node-vite':
        r = 'ui'
    if not r and cfg.get('type') == 'java-boot':
        r = 'api'
    if r == role:
        out.append(mid)
print('\n'.join(out))
" "$mf" "$role" 2>/dev/null)
  mid="${_GEOSTAT_ROLE_IDS[$idx]:-}"
  mid="${mid//$'\r'/}"
  [[ -n "$mid" ]] && echo "$mid"
}

geostat_module_id_for_type() {
  local driver_type="$1" mf mid
  mf="$(_geostat_manifest_file 2>/dev/null)" || return 1
  mid="$(geostat_python -c "
import json, sys
m = json.load(open(sys.argv[1], encoding='utf-8'))
for mid, cfg in (m.get('modules') or {}).items():
    if isinstance(cfg, dict) and cfg.get('type') == sys.argv[2]:
        print(mid)
        break
" "$mf" "$driver_type" 2>/dev/null)"
  mid="${mid//$'\r'/}"
  [[ -n "$mid" ]] && echo "$mid"
}

geostat_list_secrets_module_folders() {
  local mf
  mf="$(_geostat_manifest_file 2>/dev/null)" || return 0
  geostat_python -c "
import json, sys
m = json.load(open(sys.argv[1], encoding='utf-8'))
seen = []
for mid, cfg in (m.get('modules') or {}).items():
    if not isinstance(cfg, dict):
        continue
    folder = str(cfg.get('secretsModule', mid))
    if folder not in seen:
        seen.append(folder)
        print(folder)
" "$mf" 2>/dev/null
}

# Fallback remote DEPLOY_PATH base: {server_base}/{project_slug}/{secrets_folder}
# Credential profiles for module (file<TAB>mount<TAB>envVar per line)
geostat_module_credentials_lines() {
  local module_id="$1" kit
  kit="$(geostat_kit_package_root 2>/dev/null)" || return 0
  PYTHONPATH="${kit}${PYTHONPATH:+:$PYTHONPATH}" geostat_python -c "
from lib.project_context import ProjectContext
from lib.credentials import module_credentials
import sys
ctx = ProjectContext.discover()
for c in module_credentials(ctx.manifest, sys.argv[1]):
    ev = c.get('envVar', '')
    print(c['file'] + '\t' + c['mount'] + '\t' + ev)
" "$module_id" 2>/dev/null
}

geostat_gcp_credentials_file() {
  geostat_read_manifest_field adapters.gcp.credentialsFile google-credentials.json
}

geostat_gcp_container_mount() {
  geostat_read_manifest_field adapters.gcp.containerMount "/app/$(geostat_gcp_credentials_file)"
}

geostat_default_remote_deploy_base() {
  local secrets_folder="$1" base proj
  base="$(geostat_env_value "$secrets_folder" DEPLOY_PATH "")"
  if [[ -n "$base" ]]; then
    echo "${base%/}"
    return 0
  fi
  proj="$(geostat_project_slug)"
  base="$(geostat_server_base)/$proj/$secrets_folder"
  echo "${base%/}"
}
