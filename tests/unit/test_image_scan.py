"""The image scan a release passes (lib/delivery/scan.py): a pinned scanner on the target judges each
built image; a finding at or above the floor refuses, unless waived by the VEX document or observed
only; an old vulnerability database refuses; the verdict is written beside the release."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from delivery_host import ROOT, commit, ctx_for, host, manifest_of, packaged, server
from lib import identity
from lib.delivery import release, scan
from lib.delivery.context import DeliveryError
from lib.delivery.transport import Result

SCANNER = "anchore/grype@sha256:" + "0" * 64


def report(*sevs, built=None):
    built = built or (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    return {"matches": [{"vulnerability": {"id": f"CVE-2026-{i}", "severity": s}, "artifact": {"name": "lib"}}
                        for i, s in enumerate(sevs)], "descriptor": {"db": {"built": built}}}


def test_the_verdict_holds_the_floor_the_waivers_and_the_database_age():
    p = {"failOn": "high", "maxDbAgeHours": 24}
    why, counts = scan.verdict(report("low", "high"), p, set())
    assert counts["high"] == 1 and why and "CVE-2026-1 (high)" in why[0]
    assert scan.verdict(report("low", "high"), p, {"CVE-2026-1"})[0] == []
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    assert "database is 48h old" in scan.verdict(report("low", built=old), p, set())[0][0]
    assert scan.problems({"security": {"imageScan": {"scanner": "anchore/grype:latest"}}})


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = host(tmp_path)
    (root / "ops" / "security").mkdir(parents=True)
    (root / "ops" / "security" / "vex.json").write_text(json.dumps({"@context": "https://openvex.dev/ns/v0.2.0", "statements": [
        {"vulnerability": {"name": "CVE-2026-9"}, "status": "not_affected", "justification": "vulnerable_code_not_in_execute_path"}]}),
        encoding="utf-8")
    m = manifest_of(root)
    m["security"] = {"imageScan": {"scanner": SCANNER, "failOn": "high", "vex": "ops/security/vex.json"}}
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")
    commit(root, "with a scan policy")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
    return root


def _server_with(tmp_path, rep):
    t = server(tmp_path)
    fake = t.responses

    def answer(argv, cwd, env):
        if SCANNER in argv:
            return Result(0, json.dumps(rep))
        return fake(argv, cwd, env)
    t.responses = answer
    return t


def test_a_release_with_a_high_finding_is_refused_before_it_runs(project, tmp_path):
    t = _server_with(tmp_path, report("critical"))
    with pytest.raises(DeliveryError, match="refused by the image scan policy") as e:
        release.release(ctx_for(project, t), "edge", packaged(project))
    assert e.value.code == 5
    assert not [x for x in t.log if x[0] == "exec" and " up -d " in " ".join(x[1])]


def test_a_waived_finding_passes_and_the_verdict_is_kept_beside_the_release(project, tmp_path):
    rep = report("low")
    rep["matches"].append({"vulnerability": {"id": "CVE-2026-9", "severity": "critical"}, "artifact": {"name": "lib"}})
    t = _server_with(tmp_path, rep)
    archive = packaged(project)
    assert release.release(ctx_for(project, t), "edge", archive) == 0
    rid = archive.name[len("edge-"):-len(".tgz")]
    kept = json.loads(t.read(f"{ROOT}/shop/staging/edge/edge/releases/{rid}/.stack-kit/scan.json"))
    assert kept["counts"]["critical"] == 1 and kept["refused"] == []
