"""Manifest credential profiles — per-module list + global adapters.gcp fallback."""
from __future__ import annotations

from typing import Any

from lib.manifest_defaults import load_scaffold_manifest, read_nested
from lib.modules import driver_accepts_global_credentials


def _normalize_entry(raw: Any, *, default_mount_prefix: str = "/app") -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    fn = raw.get("file")
    if not fn or not isinstance(fn, str):
        return None
    mount = raw.get("mount")
    if not mount:
        mount = f"{default_mount_prefix.rstrip('/')}/{fn}"
    mount = str(mount)
    env_var = raw.get("envVar") or raw.get("env")
    out: dict[str, str] = {"file": fn, "mount": mount}
    if env_var:
        out["envVar"] = str(env_var)
    return out


def global_gcp_credentials(manifest: dict[str, Any]) -> list[dict[str, str]]:
    feats = manifest.get("features") or {}
    if feats.get("gcpCredentials") is not True:
        return []
    gcp = (manifest.get("adapters") or {}).get("gcp") or {}
    if isinstance(gcp, dict) and gcp.get("enabled") is False:
        return []
    scaffold = load_scaffold_manifest()
    fn = read_nested(manifest, "adapters.gcp.credentialsFile", "")
    if not fn:
        fn = read_nested(scaffold, "adapters.gcp.credentialsFile", "google-credentials.json")
    if isinstance(gcp, dict) and gcp.get("credentialsFile"):
        fn = str(gcp["credentialsFile"])
    mount = read_nested(manifest, "adapters.gcp.containerMount", "")
    if not mount and isinstance(gcp, dict) and gcp.get("containerMount"):
        mount = str(gcp["containerMount"])
    if not mount:
        mount = read_nested(scaffold, "adapters.gcp.containerMount", f"/app/{fn}")
    env_var = read_nested(manifest, "adapters.gcp.envVar", "")
    if not env_var and isinstance(gcp, dict) and gcp.get("envVar"):
        env_var = str(gcp["envVar"])
    if not env_var:
        env_var = "GOOGLE_APPLICATION_CREDENTIALS"
    return [{"file": fn, "mount": mount, "envVar": env_var}]


def _module_accepts_global_gcp(cfg: dict[str, Any]) -> bool:
    """Two declared routes to the manifest-wide credential: the DRIVER says so, or the ROLE does."""
    role = str(cfg.get("role") or "").lower()
    typ = str(cfg.get("type") or "")
    if driver_accepts_global_credentials(typ):
        return True
    return role in ("api", "worker", "gateway", "data")


def module_credentials(manifest: dict[str, Any], module_id: str) -> list[dict[str, str]]:
    """Resolved credential files for a module (explicit list or global GCP on JVM/api modules)."""
    cfg = (manifest.get("modules") or {}).get(module_id)
    if not isinstance(cfg, dict):
        return []
    raw_list = cfg.get("credentials")
    if isinstance(raw_list, list) and raw_list:
        out: list[dict[str, str]] = []
        for item in raw_list:
            norm = _normalize_entry(item)
            if norm:
                out.append(norm)
        return out
    if _module_accepts_global_gcp(cfg):
        return global_gcp_credentials(manifest)
    return []


def all_module_credential_files(manifest: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    mods = manifest.get("modules") or {}
    return {str(mid): module_credentials(manifest, str(mid)) for mid in mods}
