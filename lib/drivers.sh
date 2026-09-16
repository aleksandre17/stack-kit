#!/bin/bash
# Module driver resolution — delegates to lib/driver_api.py (manifest + registry)
# geostat_python — from project.sh (Windows-safe)

geostat_driver_api() {
  geostat_python "$(geostat_kit_package_root)/lib/driver_api.py" "$@"
}

geostat_driver_registry() {
  echo "$(geostat_kit_package_root)/drivers/registry.json"
}

geostat_module_config() {
  local id="$1" key="$2" default="${3:-}"
  geostat_python -c "
import json, os, sys
root = os.environ.get('GEOSTAT_PROJECT_ROOT', '')
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

geostat_module_type() {
  geostat_driver_api type "$1"
}

geostat_module_project_dir() {
  local id="$1" rel
  rel="$(geostat_module_config "$id" "path" "$id")"
  echo "$GEOSTAT_PROJECT_ROOT/$rel"
}

geostat_driver_root() {
  local id="$1" typ
  typ="$(geostat_module_type "$id")"
  echo "$(geostat_kit_package_root)/drivers/$typ"
}

geostat_driver_command_path() {
  local id="$1" cmd="$2"
  geostat_driver_api path "$id" "$cmd"
}

geostat_driver_capabilities() {
  geostat_driver_api caps "$1"
}

geostat_cli_resolve_alias() {
  geostat_driver_api alias "$1"
}
