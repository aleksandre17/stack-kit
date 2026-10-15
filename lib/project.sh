#!/bin/bash
# Project manifest resolution — package boundary.
#
# The manifest's NAME is not spelled here. It is declared once in lib/identity.json
# and projected into every runtime, so a rename is one edit and never an archaeology.

# One string field of the ONE declaration (pure text: works before python is known).
_stack_kit_identity() {
  local decl="${BASH_SOURCE[0]%/*}/identity.json"
  [[ -f "$decl" ]] || { echo "  ERROR: kit identity declaration missing: $decl" >&2; return 1; }
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$decl" | head -1
}

# One array field of the declaration, one item per line.
_stack_kit_identity_list() {
  local decl="${BASH_SOURCE[0]%/*}/identity.json"
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\[\([^]]*\)\].*/\1/p" "$decl" | grep -o '"[^"]*"' | tr -d '"'
}

# One line, once per legacy name and process tree: what is deprecated, what replaces it, when it
# stops (ADR-001). The names already told travel in <prefix>_NOTICED, shared with python and pwsh.
_stack_kit_notice() {
  local quiet_new quiet_old told
  quiet_new="$(_stack_kit_identity envPrefix)_NO_DEPRECATION_NOTICE"
  quiet_old="$(_stack_kit_identity legacyEnvPrefix)_NO_DEPRECATION_NOTICE"
  [[ -n "${!quiet_new:-}${!quiet_old:-}" ]] && return 0
  told="$(_stack_kit_identity envPrefix)_NOTICED"
  [[ "|${!told:-}|" == *"|$1|"* ]] && return 0
  export "$told=${!told:+${!told}|}$1"
  echo "[$(_stack_kit_identity kitName)] deprecated: $1 -> $2; read until $(_stack_kit_identity legacyRemovedIn)" >&2
}

# Carry every legacy-prefixed variable to its canonical name for this process tree. The
# canonical name wins when both are set; the legacy one is unset so a child is not told twice.
_stack_kit_adopt_legacy_env() {
  local canon legacy old new
  canon="$(_stack_kit_identity envPrefix)" || return 1
  legacy="$(_stack_kit_identity legacyEnvPrefix)"
  [[ -n "$legacy" ]] || return 0
  for old in $(compgen -e); do
    [[ "$old" == "${legacy}_"* ]] || continue
    new="${canon}_${old#"${legacy}_"}"
    [[ -n "${!new+x}" ]] || export "$new=${!old}"
    _stack_kit_notice "$old" "$new"
    unset "$old"
  done
}
_stack_kit_adopt_legacy_env

# Accepted manifest filenames, canonical first — read from the ONE declaration.
# Pure text parsing on purpose: this must work before python is known to exist.
_stack_kit_manifest_names() {
  local decl="${BASH_SOURCE[0]%/*}/identity.json"
  # No guessed default: a missing declaration is a broken kit, and a fallback
  # spelling here would be exactly the second home this file exists to remove.
  [[ -f "$decl" ]] || { echo "  ERROR: kit identity declaration missing: $decl" >&2; return 1; }
  sed -n 's/.*"manifestFilename"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$decl"
  _stack_kit_identity_list legacyManifestFilenames
}

# First accepted manifest inside $1, or non-zero when the directory holds none.
_stack_kit_manifest_in() {
  local dir="$1" name canonical=""
  while read -r name; do
    [[ -n "$canonical" ]] || canonical="$name"
    if [[ -n "$name" && -f "$dir/$name" ]]; then
      [[ "$name" == "$canonical" ]] || _stack_kit_notice "$name" "$canonical"
      echo "$dir/$name"
      return 0
    fi
  done < <(_stack_kit_manifest_names)
  return 1
}

stack_kit_python() {
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

_stack_kit_manifest_file() {
  local root="${STACK_KIT_PROJECT_ROOT:-}"
  if [[ -z "$root" ]]; then
    local dir="${1:-$(pwd)}"
    while [[ -n "$dir" && "$dir" != "/" ]]; do
      _stack_kit_manifest_in "$dir" && return 0
      dir="$(dirname "$dir")"
    done
    return 1
  fi
  _stack_kit_manifest_in "$root" && return 0
  # Declared root with no manifest yet: name the canonical target, not a guess.
  echo "$root/$(_stack_kit_manifest_names | head -1)"
}

_stack_kit_legacy_discovery() {
  [[ "${STACK_KIT_LEGACY_ROOT_DISCOVERY:-}" =~ ^(1|true|yes|on)$ ]]
}

# Git Bash / MSYS: Windows drive paths break PYTHONPATH in inline env (\U escapes).
stack_kit_normalize_unix_path() {
  local p="${1:-}"
  [[ -n "$p" ]] || return 1
  if [[ "$p" =~ ^[A-Za-z]:[/\\] ]]; then
    (cd "$p" && pwd) || echo "$p"
  else
    echo "$p"
  fi
}

stack_kit_find_project_root() {
  if [[ -n "${STACK_KIT_PROJECT_ROOT:-}" ]]; then
    stack_kit_normalize_unix_path "$STACK_KIT_PROJECT_ROOT"
    return 0
  fi
  local dir="${1:-$(pwd)}" mf
  while [[ -n "$dir" && "$dir" != "/" ]]; do
    if _stack_kit_manifest_in "$dir" >/dev/null; then
      stack_kit_normalize_unix_path "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  if _stack_kit_legacy_discovery; then
    dir="${1:-$(pwd)}"
    while [[ -n "$dir" && "$dir" != "/" ]]; do
      if [[ -d "$dir/secrets" || -d "$dir/ops/config" ]]; then
        local vendor
        while read -r vendor; do
          if [[ -n "$vendor" && -d "$dir/$vendor" ]]; then
            stack_kit_normalize_unix_path "$dir"
            return 0
          fi
        done < <(_stack_kit_identity_list vendorDirs; _stack_kit_identity_list legacyVendorDirs)
      fi
      dir="$(dirname "$dir")"
    done
  fi
  return 1
}

stack_kit_read_manifest_field() {
  local field="$1" default="${2:-}"
  if [[ -z "$default" && -n "${STACK_KIT_KIT_ROOT:-}" ]]; then
    default="$(PYTHONPATH="${STACK_KIT_KIT_ROOT}${PYTHONPATH:+:$PYTHONPATH}" stack_kit_python -c "
from lib.manifest_defaults import default_field
import sys
print(default_field(sys.argv[1]))
" "$field" 2>/dev/null || true)"
  fi
  local mf root
  mf="$(_stack_kit_manifest_file 2>/dev/null)" || { echo "$default"; return; }
  root="$(dirname "$mf")"
  # The kit's own reader, so a field the kit renamed is still read under its old name.
  stack_kit_python -c "
import json, sys
sys.path.insert(0, sys.argv[4])
from lib.identity import manifest_field
with open(sys.argv[1], encoding='utf-8') as fh:
    v = manifest_field(json.load(fh), sys.argv[2])
print(v if v is not None else sys.argv[3])
" "$mf" "$field" "$default" "$(cd "${BASH_SOURCE[0]%/*}/.." && pwd)" || echo "$default"
}

# Read an ARRAY-valued manifest field as newline-separated items (empty when absent,
# not an array, or no manifest). Generic companion to stack_kit_read_manifest_field.
stack_kit_read_manifest_list() {
  local field="$1" mf
  mf="$(_stack_kit_manifest_file 2>/dev/null)" || return 0
  stack_kit_python -c "
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

stack_kit_kit_package_root() {
  if [[ -n "${OPS_PACKAGE_ROOT:-}" ]]; then
    echo "$OPS_PACKAGE_ROOT"
    return 0
  fi
  if [[ -n "${STACK_KIT_KIT_ROOT:-}" ]]; then
    echo "$STACK_KIT_KIT_ROOT"
    return 0
  fi
  local proj rel pkg
  proj="$(stack_kit_find_project_root)" || return 1
  rel="$(stack_kit_read_manifest_field package)"
  pkg="$(cd "$proj" && cd "$rel" 2>/dev/null && pwd)"
  echo "$pkg"
}

stack_kit_kit_toolkit_bash() {
  echo "$(stack_kit_kit_package_root)/toolkit/bash"
}

stack_kit_kit_deploy_lib() {
  echo "$(stack_kit_kit_package_root)/toolkit/deploy"
}

stack_kit_kit_compose_catalog() {
  local proj
  proj="$(stack_kit_find_project_root)" || return 1
  echo "$proj/$(stack_kit_read_manifest_field compose.catalog)"
}

stack_kit_kit_sync_modules_path() {
  local proj
  proj="$(stack_kit_find_project_root)" || return 1
  echo "$proj/$(stack_kit_read_manifest_field compose.syncModules)"
}

# --- Module / secrets paths (manifest modules.*) ---

stack_kit_module_path() {
  local module_id="$1" proj rel
  proj="$(stack_kit_find_project_root)" || return 1
  rel="$(stack_kit_read_manifest_field "modules.${module_id}.path" "")"
  [[ -n "$rel" ]] || return 1
  echo "$proj/$rel"
}

stack_kit_secrets_module_name() {
  local module_id="$1" sm
  sm="$(stack_kit_read_manifest_field "modules.${module_id}.secretsModule" "$module_id")"
  echo "$sm"
}

stack_kit_secrets_dir_for_module() {
  local module_id="$1"
  echo "$(stack_kit_secrets_root)/$(stack_kit_secrets_module_name "$module_id")"
}

stack_kit_stack_compose_dir() {
  local proj rel
  proj="$(stack_kit_find_project_root)" || return 1
  rel="$(stack_kit_read_manifest_field stack.composeDir)"
  echo "$proj/$rel"
}

stack_kit_manifest_feature_enabled() {
  local name="$1" mf
  mf="$(_stack_kit_manifest_file 2>/dev/null)" || { echo "false"; return; }
  stack_kit_python -c "
import json, sys
m = json.load(open(sys.argv[1], encoding='utf-8'))
f = (m.get('features') or {}).get(sys.argv[2])
print('true' if f is True else 'false')
" "$mf" "$name" 2>/dev/null || echo "false"
}

# Secrets folder names from manifest modules (one per line)
stack_kit_module_id_for_role() {
  local role="$1" idx="${2:-0}" mf mid
  mf="$(_stack_kit_manifest_file 2>/dev/null)" || return 1
  mapfile -t _STACK_KIT_ROLE_IDS < <(stack_kit_python -c "
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
  mid="${_STACK_KIT_ROLE_IDS[$idx]:-}"
  mid="${mid//$'\r'/}"
  [[ -n "$mid" ]] && echo "$mid"
}

stack_kit_module_id_for_type() {
  local driver_type="$1" mf mid
  mf="$(_stack_kit_manifest_file 2>/dev/null)" || return 1
  mid="$(stack_kit_python -c "
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

stack_kit_list_secrets_module_folders() {
  local mf
  mf="$(_stack_kit_manifest_file 2>/dev/null)" || return 0
  stack_kit_python -c "
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
stack_kit_module_credentials_lines() {
  local module_id="$1" kit
  kit="$(stack_kit_kit_package_root 2>/dev/null)" || return 0
  PYTHONPATH="${kit}${PYTHONPATH:+:$PYTHONPATH}" stack_kit_python -c "
from lib.project_context import ProjectContext
from lib.credentials import module_credentials
import sys
ctx = ProjectContext.discover()
for c in module_credentials(ctx.manifest, sys.argv[1]):
    ev = c.get('envVar', '')
    print(c['file'] + '\t' + c['mount'] + '\t' + ev)
" "$module_id" 2>/dev/null
}

stack_kit_gcp_credentials_file() {
  stack_kit_read_manifest_field adapters.gcp.credentialsFile google-credentials.json
}

stack_kit_gcp_container_mount() {
  stack_kit_read_manifest_field adapters.gcp.containerMount "/app/$(stack_kit_gcp_credentials_file)"
}

stack_kit_default_remote_deploy_base() {
  local secrets_folder="$1" base proj
  base="$(stack_kit_env_value "$secrets_folder" DEPLOY_PATH "")"
  if [[ -n "$base" ]]; then
    echo "${base%/}"
    return 0
  fi
  proj="$(stack_kit_project_slug)"
  base="$(stack_kit_server_base)/$proj/$secrets_folder"
  echo "${base%/}"
}

# Told once, here in the sourcing shell: a legacy manifest name noticed inside a $(...) subshell
# would be told again by every later one, because a subshell cannot export to its parent.
_stack_kit_manifest_file >/dev/null || true
