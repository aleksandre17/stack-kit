"""A container host for the recording transport: the engine and compose answers a real one gives,
kept in a JSON file beside the recording, so the CLI's acceptance tests (and a rehearsal of a
plan) run every verb end to end without a server. Never used unless the transport is named
(`STACK_KIT_TRANSPORT=record:<file>`).

State: images built, containers up (and the health each reports), networks, and -- for the tests
-- `foreign` (other projects' published ports: {port: project}), `listening` (ports held outside
the engine) and `health` ({service: status} a container reports instead of healthy).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.delivery.transport import RecordingTransport, Result


def _load(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"images": [], "containers": {}, "networks": [], "foreign": {}, "listening": [], "health": {}}


def state_file(record: Path) -> Path:
    return record.with_name(record.name + ".engine.json")


def responses(t: RecordingTransport, record: Path):
    path = state_file(record)

    def save(st: dict[str, Any]) -> None:
        path.write_text(json.dumps(st, indent=1, sort_keys=True), encoding="utf-8")

    def compose_doc(file: str) -> dict[str, Any]:
        raw = t.read(file)
        return json.loads(raw.decode("utf-8")) if raw else {"services": {}}

    def answer(argv: list[str], cwd: str, env: dict[str, str]) -> Result:
        st = _load(path)
        if argv[:1] in (["ss"],):
            return Result(0, "".join(f"LISTEN 0 4096 0.0.0.0:{p} 0.0.0.0:*\n" for p in st["listening"]))
        if argv[:1] == ["df"]:
            return Result(0, "Filesystem 1024-blocks Used Available Capacity Mounted\n/dev/sda1 100000000 40000000 60000000 40% /\n")
        if argv[:1] == ["rsync"]:
            return Result(127, "", "rsync: not found")
        if "-f" in argv and argv[argv.index("-f") + 1].endswith("compose.yml"):
            i = argv.index("-f")
            doc = compose_doc(argv[i + 1])
            verb, rest = (argv[i + 2] if len(argv) > i + 2 else ""), argv[i + 3:]
            if verb == "version":
                return Result(0, "Docker Compose version v2.29.0\n")
            names = [a for a in rest if not a.startswith("-")] or sorted(doc.get("services") or {})
            if verb == "build":
                for sid in names:
                    image = (doc["services"].get(sid) or {}).get("image")
                    if image and image not in st["images"]:
                        st["images"].append(image)
                save(st)
                return Result(0, f"built {', '.join(names)}\n")
            if verb in ("up", "start", "restart"):
                for sid in names:
                    svc = doc["services"].get(sid) or {}
                    if svc.get("build") and svc.get("image") not in st["images"]:
                        st["images"].append(svc["image"])
                    st["containers"][svc.get("container_name", sid)] = {"service": sid, "image": svc.get("image")}
                save(st)
                return Result(0)
            if verb in ("stop", "rm", "down"):
                for sid in names if verb != "down" else list(st["containers"]):
                    name = (doc["services"].get(sid) or {}).get("container_name", sid)
                    st["containers"].pop(name, None)
                save(st)
                return Result(0)
            return Result(0)
        verb = argv[1] if len(argv) > 1 else ""
        if verb == "version":
            return Result(0, "29.0.0\n")
        if verb == "ps":
            mine = "".join(f"{c.get('project', '')}\t0.0.0.0:{c['port']}->80/tcp\n" for c in st.get("published", []))
            return Result(0, mine + "".join(f"{proj}\t0.0.0.0:{port}->80/tcp\n" for port, proj in st["foreign"].items()))
        if verb == "network":
            net = argv[3] if len(argv) > 3 else ""
            if argv[2] == "inspect":
                return Result(0 if net in st["networks"] else 1)
            if argv[2] == "create":
                st["networks"].append(net)
                save(st)
            if argv[2] == "rm" and net in st["networks"]:
                st["networks"].remove(net)
                save(st)
            return Result(0)
        if verb == "image" and argv[2] == "inspect":
            return Result(0 if argv[3] in st["images"] else 1)
        if verb == "inspect":
            name = argv[-1]
            c = st["containers"].get(name)
            if not c:
                return Result(1, "", f"No such container: {name}")
            health = st["health"].get(c["service"], "healthy")
            return Result(0, ("exited " if health == "exited" else "running ") + ("" if health in ("exited", "none") else health) + "\n")
        return Result(0)

    return answer
