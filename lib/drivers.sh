#!/bin/bash
# Module driver resolution — delegates to lib/driver_api.py (manifest + registry)
# stack_kit_python — from project.sh (Windows-safe)

stack_kit_driver_api() {
  stack_kit_python "$(stack_kit_kit_package_root)/lib/driver_api.py" "$@"
}

stack_kit_driver_registry() {
  echo "$(stack_kit_kit_package_root)/drivers/registry.json"
}

stack_kit_module_config() {
  local id="$1" key="$2" default="${3:-}"
  stack_kit_python -c "
import json, os, sys
root = os.environ.get('STACK_KIT_PROJECT_ROOT', '')
decl = os.path.join(os.path.dirname(os.path.abspath(sys.argv[4])), 'identity.json')
d = json.load(open(decl, encoding='utf-8'))
names = [d['manifestFilename'], *d.get('legacyManifestFilenames', [])]
mf = next((p for p in (os.path.join(root, n) for n in names) if os.path.isfile(p)), '')
m = {}
if mf:
    data = json.load(open(mf, encoding='utf-8'))
    m = data.get('modules', {}).get(sys.argv[1], {})
v = m.get(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else '')
print(v if v is not None else '')
" "$id" "$key" "$default" "${BASH_SOURCE[0]}"
}

stack_kit_module_type() {
  stack_kit_driver_api type "$1"
}

stack_kit_module_project_dir() {
  local id="$1" rel
  rel="$(stack_kit_module_config "$id" "path" "$id")"
  echo "$STACK_KIT_PROJECT_ROOT/$rel"
}

stack_kit_driver_root() {
  local id="$1" typ
  typ="$(stack_kit_module_type "$id")"
  echo "$(stack_kit_kit_package_root)/drivers/$typ"
}

stack_kit_driver_command_path() {
  local id="$1" cmd="$2"
  stack_kit_driver_api path "$id" "$cmd"
}

stack_kit_driver_capabilities() {
  stack_kit_driver_api caps "$1"
}

stack_kit_cli_resolve_alias() {
  stack_kit_driver_api alias "$1"
}
