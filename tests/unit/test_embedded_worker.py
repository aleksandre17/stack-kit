"""P0-kit-13 — manifest embeddedWorker vs catalog features.worker."""
from __future__ import annotations

from lib.compose_identity import (
    effective_compose_features,
    embedded_worker_enabled,
    primary_api_module_id,
    primary_worker_module_id,
)


def test_embedded_worker_from_manifest() -> None:
    manifest = {
        "modules": {
            "chat-api": {
                "role": "api",
                "compose": {"embeddedWorker": True},
            },
            "ingestion": {"role": "worker"},
        }
    }
    assert embedded_worker_enabled(manifest, {"worker": False}) is True


def test_embedded_worker_manifest_false_overrides_catalog() -> None:
    manifest = {
        "modules": {
            "chat-api": {"role": "api", "compose": {"embeddedWorker": False}},
        }
    }
    assert embedded_worker_enabled(manifest, {"worker": True}) is False


def test_embedded_worker_catalog_fallback() -> None:
    manifest = {"modules": {"backend": {"role": "api"}}}
    assert embedded_worker_enabled(manifest, {"worker": True}) is True
    assert embedded_worker_enabled(manifest, {"worker": False}) is False


def test_effective_compose_features_sets_worker_key() -> None:
    manifest = {
        "modules": {
            "chat-api": {"role": "api", "compose": {"embeddedWorker": False}},
            "ingestion": {"role": "worker"},
        }
    }
    out = effective_compose_features(manifest, {"worker": True, "gcp": True})
    assert out["worker"] is False
    assert out["gcp"] is True


def test_primary_api_prefers_chat_api() -> None:
    manifest = {
        "stack": {"composeModules": ["chat-api", "ingestion"]},
        "modules": {
            "chat-api": {"role": "api"},
            "ingestion": {"role": "worker"},
        },
    }
    assert primary_api_module_id(manifest) == "chat-api"
    assert primary_worker_module_id(manifest) == "ingestion"
