"""Private pre-beta pairing preferences and fresh, authenticated run identities.

The persistent code authenticates the lobby only. Simulation credentials are
derived anew from a host-issued run epoch after both fresh local run tokens have
been acknowledged. This file contains no user's address or pairing defaults.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import uuid

from .core import ProtocolError, canonical_json

PROFILE_NAME = "test-pairing.json"
PROFILE_LIMIT = 2048
TOKEN = re.compile(r"[0-9a-f]{32}")


def canonical_code(code):
    raw = str(code).replace("-", "").replace(" ", "").strip().upper()
    if len(raw) != 32 or any(c not in "0123456789ABCDEF" for c in raw):
        raise ValueError("Bitte den vollständigen Testschlüssel des Hosts einfügen (8 Gruppen).")
    return "-".join(raw[index:index + 4] for index in range(0, 32, 4))


def new_code():
    return canonical_code(secrets.token_hex(16))


def connection_identity(code):
    """Stable lobby identity, deliberately not the simulation run epoch."""
    raw = canonical_code(code).replace("-", "").lower()
    return (hashlib.sha256(("tf2-probe-epoch:" + raw).encode()).hexdigest()[:32],
            hashlib.sha256(("tf2-probe-key:" + raw).encode()).hexdigest().encode("ascii"))


def validate_host(value):
    try:
        address = ipaddress.IPv4Address(str(value).strip())
        if address.is_unspecified or address.is_multicast or str(address) == "255.255.255.255":
            raise ValueError()
    except ValueError as exc:
        raise ValueError("Bitte die IPv4-Adresse des Hosts aus Hamachi oder dem gemeinsamen LAN eingeben.") from exc
    return str(address)


def validate_profile(value):
    if (type(value) is not dict or set(value) != {"schema", "host", "code", "role"}
            or type(value["schema"]) is not int or value["schema"] != 1
            or value["role"] not in ("a", "b") or type(value["code"]) is not str
            or type(value["host"]) is not str):
        raise ValueError("Ungültiges privates Testprofil; bitte die Verbindungsdaten erneut speichern.")
    return {"schema": 1, "host": validate_host(value["host"]),
            "code": canonical_code(value["code"]), "role": value["role"]}


def load_profile(root):
    path = Path(root) / PROFILE_NAME
    try:
        if path.is_symlink() or path.stat().st_size > PROFILE_LIMIT:
            raise ValueError("Ungültige private Testprofildatei.")
        return validate_profile(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return None
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Das private Testprofil ist nicht lesbar; bitte erneut speichern.") from exc


def save_profile(root, *, host, code, role):
    value = validate_profile({"schema": 1, "host": host, "code": code, "role": role})
    path = Path(root) / PROFILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Die private Testprofildatei darf keine Verknüpfung sein.")
    temp = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(canonical_json(value))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return value


def validate_token(value):
    if type(value) is not str or TOKEN.fullmatch(value) is None:
        raise ProtocolError("invalid fresh run token")
    return value


def signed_message(secret, kind, **fields):
    value = {"kind": kind, **fields}
    value["proof"] = hmac.new(secret, canonical_json(value), hashlib.sha256).hexdigest()
    return value


def validate_signed(secret, value, kind, fields):
    if type(value) is not dict or set(value) != {"kind", "proof", *fields} or value["kind"] != kind:
        raise ProtocolError("invalid authenticated run negotiation")
    expected = signed_message(secret, kind, **{key: value[key] for key in fields})["proof"]
    if type(value["proof"]) is not str or not hmac.compare_digest(expected, value["proof"]):
        raise ProtocolError("run negotiation authentication failed")


def game_secret(secret, epoch, manifest):
    validate_token(epoch)
    return hmac.new(secret, canonical_json(["tfcoop-game-run-v1", epoch, manifest]), hashlib.sha256).hexdigest().encode("ascii")


def connection_receipt(secret, *, role, local_run, epoch, manifest):
    validate_token(local_run)
    validate_token(epoch)
    return signed_message(secret, "local_run_connected", role=role, local_run=local_run,
                          epoch=epoch, manifest=manifest)["proof"]


def validate_connection(secret, status, *, role, local_run, manifest):
    epoch = status.get("epoch")
    if (status.get("protocol") != 2 or status.get("state") != "connected"
            or status.get("role") != role or status.get("local_run") != local_run
            or status.get("manifest") != manifest):
        raise ProtocolError("connection receipt does not belong to this prepared run")
    expected = connection_receipt(secret, role=role, local_run=local_run, epoch=epoch, manifest=manifest)
    if type(status.get("run_proof")) is not str or not hmac.compare_digest(expected, status["run_proof"]):
        raise ProtocolError("connection receipt authentication failed")
    return epoch


def redact_addresses(text):
    """Logs can contain socket error tuples; diagnostic copies omit IPv4s."""
    # An address may also be part of an exception's filename (IP.log), a
    # directory or JSON-escaped path; letters/dots cannot exempt that address.
    return re.sub(r"(?<![0-9])(?:\d{1,3}\.){3}\d{1,3}(?![0-9])", "[IPv4 entfernt]", text)
