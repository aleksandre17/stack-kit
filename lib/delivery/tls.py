"""TLS for a private network (no public DNS, no public CA): an internal CA, a leaf per host, and a
public, password-less truststore for clients (ADR-001 amendment 14).

All of it lives in the environment's infra place on the target ({infra}/tls): the CA's key is made
there (umask 077) and never leaves; a leaf is signed there; only public material comes back.

    ca          the CA key and certificate, made once -- never replaced (every leaf depends on it)
    leaf        a host's key and certificate (subjectAltName: its DNS names and IPs), signed by the CA,
                397 days; written into tls/live where the edge reads it
    truststore  the CA certificate (PEM) and a PKCS#12 truststore holding only it, without a
                password (it holds nothing secret), copied to this machine
"""
from __future__ import annotations

import ipaddress
import posixpath
import re
import shlex
from pathlib import Path

from lib.delivery.context import Delivery, DeliveryError

NAME = re.compile(r"^[A-Za-z0-9.-]+$")


def _dir(ctx: Delivery) -> str:
    return posixpath.join(ctx.places.of("infra"), "tls")


def ca(ctx: Delivery, subject: str = "") -> str:
    d = _dir(ctx)
    key, crt = posixpath.join(d, "ca", "ca.key"), posixpath.join(d, "ca", "ca.crt")
    subj = subject or f"/CN={ctx.project} {ctx.environment} internal CA"
    script = (f"umask 077; mkdir -p {shlex.quote(posixpath.dirname(key))} && "
              f"if [ -s {shlex.quote(key)} ]; then echo exists; else "
              f"openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes -keyout {shlex.quote(key)} -out {shlex.quote(crt)} "
              f"-subj {shlex.quote(subj)} -addext basicConstraints=critical,CA:TRUE,pathlen:0 "
              f"-addext keyUsage=critical,keyCertSign,cRLSign && chmod 644 {shlex.quote(crt)}; fi")
    r = ctx.run(["sh", "-c", script])
    ctx.out(f"[tls] CA {'kept' if 'exists' in r.out else 'made'}: {crt} (its key stays on the target)")
    return crt


def leaf(ctx: Delivery, name: str, sans: list[str]) -> str:
    if not NAME.match(name):
        raise DeliveryError(f"tls leaf: '{name}' is not a host name", 2)
    d = _dir(ctx)
    ca_key, ca_crt = posixpath.join(d, "ca", "ca.key"), posixpath.join(d, "ca", "ca.crt")
    live = posixpath.join(d, "live")
    key, csr, crt = (posixpath.join(live, f"{name}.{ext}") for ext in ("key", "csr", "crt"))
    alt = []
    for s in [name, *sans]:
        try:
            ipaddress.ip_address(s)
            alt.append(f"IP:{s}")
        except ValueError:
            if not NAME.match(s):
                raise DeliveryError(f"tls leaf: '{s}' is neither a host name nor an IP", 2)
            alt.append(f"DNS:{s}")
    ext = posixpath.join(live, f"{name}.ext")
    script = (f"umask 077; [ -s {shlex.quote(ca_key)} ] || {{ echo 'no CA: run `tls ca` first' >&2; exit 3; }}; "
              f"mkdir -p {shlex.quote(live)} && "
              f"printf '%s\\n' 'basicConstraints=CA:FALSE' 'keyUsage=critical,digitalSignature,keyEncipherment' "
              f"'extendedKeyUsage=serverAuth' {shlex.quote('subjectAltName=' + ','.join(alt))} > {shlex.quote(ext)} && "
              f"openssl req -newkey rsa:2048 -nodes -keyout {shlex.quote(key)} -out {shlex.quote(csr)} -subj {shlex.quote('/CN=' + name)} && "
              f"openssl x509 -req -in {shlex.quote(csr)} -CA {shlex.quote(ca_crt)} -CAkey {shlex.quote(ca_key)} -CAcreateserial "
              f"-days 397 -sha256 -extfile {shlex.quote(ext)} -out {shlex.quote(crt)} && chmod 644 {shlex.quote(crt)} && "
              f"chmod 755 {shlex.quote(live)} && chmod 644 {shlex.quote(key)} && rm -f {shlex.quote(csr)} {shlex.quote(ext)}")
    # 644: the edge runs unprivileged (another uid) and reads it through a read-only mount; the
    # target account is the boundary, the CA key (0600 under ca/) never leaves it
    r = ctx.run(["sh", "-c", script], check=False)
    if r.code == 3:
        raise DeliveryError("tls leaf: the target has no CA yet -- `stack-kit tls ca` first", 2)
    if r.code != 0:
        raise DeliveryError(f"tls leaf {name}: openssl failed (exit {r.code})")
    ctx.out(f"[tls] leaf {name} ({', '.join(alt)}): {crt}")
    return crt


def truststore(ctx: Delivery, out: Path) -> list[Path]:
    """The CA certificate and a password-less PKCS#12 truststore of it, copied to `out`."""
    d = _dir(ctx)
    crt, p12 = posixpath.join(d, "ca", "ca.crt"), posixpath.join(d, "public", "truststore.p12")
    ctx.run(["sh", "-c", f"mkdir -p {shlex.quote(posixpath.dirname(p12))} && "
                         f"openssl pkcs12 -export -nokeys -in {shlex.quote(crt)} -out {shlex.quote(p12)} -passout pass: "
                         f"-name {shlex.quote(ctx.project + '-ca')} && chmod 644 {shlex.quote(p12)}"])
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for remote, local in ((crt, out / f"{ctx.project}-{ctx.environment}-ca.crt"), (p12, out / f"{ctx.project}-{ctx.environment}-truststore.p12")):
        data = ctx.transport.read(remote)
        if data is None and not ctx.plan:
            raise DeliveryError(f"tls truststore: {remote} is not there -- `stack-kit tls ca` first", 2)
        if data is not None:
            local.write_bytes(data)
            written.append(local)
    return written
