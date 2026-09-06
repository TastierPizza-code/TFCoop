"""Bounded, authenticated wire protocol for presence; never executes game commands."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import re
from typing import Any

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 65536  # Includes the newline delimiter.
MAX_PLAYERS = 4
MAX_PREVIEW_POINTS = 128
PREVIEW_TTL = 2.0
CAPABILITIES = ["presence", "preview"]
PREVIEW_KINDS = {
    "road", "rail", "station", "terrain", "area", "marker", "street", "track",
    "construction", "bulldozer",
}
COLORS = ("#55A7FF", "#FFB454", "#A9DC76", "#D59CFF")


class ProtocolError(ValueError):
    """A public, nonsecret explanation suitable for a protocol error response."""


class AuthenticationError(ProtocolError):
    pass


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise ProtocolError("non-finite number")


def encode_frame(message: dict[str, Any]) -> bytes:
    if not isinstance(message, dict):
        raise ProtocolError("frame must be a JSON object")
    try:
        data = json.dumps(message, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8") + b"\n"
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ProtocolError("invalid JSON frame") from exc
    if len(data) > MAX_FRAME_BYTES:
        raise ProtocolError("frame exceeds 64 KiB")
    return data


async def read_frame(reader: asyncio.StreamReader) -> dict[str, Any]:
    try:
        data = await reader.readline()
    except (ValueError, asyncio.LimitOverrunError) as exc:
        raise ProtocolError("frame exceeds 64 KiB") from exc
    if not data:
        raise EOFError("connection closed")
    if len(data) > MAX_FRAME_BYTES:
        raise ProtocolError("frame exceeds 64 KiB")
    if not data.endswith(b"\n"):
        raise ProtocolError("incomplete frame")
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_object,
                            parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError("invalid JSON frame") from exc
    if not isinstance(result, dict):
        raise ProtocolError("frame must be a JSON object")
    return result


def fields(data: Any, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(data, dict):
        raise ProtocolError("expected object")
    if not required <= data.keys() or data.keys() - required - (optional or set()):
        raise ProtocolError("missing or unsupported fields")
    return data


def clean_text(value: Any, maximum: int, field: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise ProtocolError(f"invalid {field}")
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value):
        raise ProtocolError(f"invalid {field}")
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ProtocolError(f"invalid {field}")
    return value


def validate_name(value: Any) -> str:
    name = clean_text(value, 32, "name").strip()
    if not name:
        raise ProtocolError("invalid name")
    return name


def validate_manifest(value: Any) -> dict[str, str]:
    fields(value, {"map_fingerprint", "mod_fingerprint"}, {"game_version"})
    return {k: clean_text(v, 256, "manifest fingerprint") for k, v in value.items()}


def finite_number(value: Any, lower: float, upper: float) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError("expected finite number")
    try:
        valid = math.isfinite(value) and lower <= value <= upper
    except OverflowError:
        valid = False
    if not valid:
        raise ProtocolError("number outside supported range")
    return value


def position(value: Any) -> list[int | float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ProtocolError("position must contain x, y, z")
    return [finite_number(n, -10_000_000, 10_000_000) for n in value]


def validate_preview(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    fields(value, {"kind", "points"}, {"label", "width"})
    if not isinstance(value["kind"], str) or value["kind"] not in PREVIEW_KINDS:
        raise ProtocolError("unsupported preview kind")
    points = value["points"]
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_PREVIEW_POINTS:
        raise ProtocolError("preview requires 1 to 128 points")
    result = {"kind": value["kind"], "points": [position(p) for p in points]}
    if "label" in value:
        result["label"] = clean_text(value["label"], 80, "preview label")
    if "width" in value:
        result["width"] = finite_number(value["width"], 0, 1000)
    return result


def validate_telemetry(value: Any) -> dict[str, Any] | None:
    """Optional diagnostics. These values never authorize or change game state."""
    if value is None:
        return None
    fields(value, set(), {"money", "balance", "date", "paused"})
    result = {}
    for key in ("money", "balance"):
        if key in value:
            result[key] = finite_number(value[key], -1e18, 1e18)
    if "date" in value:
        result["date"] = clean_text(value["date"], 40, "date")
    if "paused" in value:
        if not isinstance(value["paused"], bool):
            raise ProtocolError("paused must be boolean")
        result["paused"] = value["paused"]
    return result


def validate_presence(value: Any) -> dict[str, Any]:
    fields(value, {"cursor", "preview"}, {"telemetry"})
    result = {
        "cursor": None if value["cursor"] is None else position(value["cursor"]),
        "preview": validate_preview(value["preview"]),
    }
    if "telemetry" in value:
        result["telemetry"] = validate_telemetry(value["telemetry"])
    return result


def validate_client_message(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("expected object")
    kind = value.get("type")
    if kind == "build":
        raise ProtocolError("unsupported capability: building and game-state synchronization are unavailable")
    if kind == "presence":
        fields(value, {"type", "presence"})
        return {"type": kind, "presence": validate_presence(value["presence"])}
    if kind == "ping":
        fields(value, {"type"})
        return {"type": kind}
    if kind == "telemetry":
        fields(value, {"type", "telemetry"})
        return {"type": kind, "telemetry": validate_telemetry(value["telemetry"])}
    raise ProtocolError("unsupported message type")


def make_proof(token: str, nonce: str, name: str, manifest: dict[str, str]) -> str:
    payload = json.dumps({"version": PROTOCOL_VERSION, "nonce": nonce,
                          "name": name, "manifest": manifest}, sort_keys=True,
                         ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hmac.new(token.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def validate_auth(value: Any, token: str, nonce: str, manifest: dict[str, str]) -> str:
    fields(value, {"type", "version", "name", "manifest", "proof"})
    if value["type"] != "auth" or type(value["version"]) is not int or value["version"] != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    name = validate_name(value["name"])
    proposed_manifest = validate_manifest(value["manifest"])
    proof = value["proof"]
    if not isinstance(proof, str) or not re.fullmatch("[0-9a-f]{64}", proof):
        raise AuthenticationError("authentication failed")
    if not hmac.compare_digest(make_proof(token, nonce, name, proposed_manifest), proof):
        raise AuthenticationError("authentication failed")
    if proposed_manifest != manifest:
        raise ProtocolError("map/mod manifest mismatch")
    return name


def validate_snapshot(value: Any) -> dict[str, Any]:
    fields(value, {"type", "seq", "peers", "capabilities"})
    if value["type"] != "snapshot" or type(value["seq"]) is not int or value["seq"] < 0:
        raise ProtocolError("invalid snapshot sequence")
    if value["capabilities"] != CAPABILITIES:
        raise ProtocolError("unsupported server capabilities")
    peers = value["peers"]
    if not isinstance(peers, list) or len(peers) > MAX_PLAYERS:
        raise ProtocolError("invalid peer list")
    ids = set()
    result = []
    for peer in peers:
        fields(peer, {"id", "name", "color", "presence", "status", "telemetry"})
        peer_id = clean_text(peer["id"], 64, "peer id")
        if peer_id in ids or peer["color"] not in COLORS or peer["status"] not in ("active", "idle"):
            raise ProtocolError("invalid peer identity")
        ids.add(peer_id)
        fields(peer["presence"], {"cursor", "preview"})
        result.append({"id": peer_id, "name": validate_name(peer["name"]),
                       "color": peer["color"], "presence": validate_presence(peer["presence"]), "status": peer["status"],
                       "telemetry": validate_telemetry(peer["telemetry"])})
    return {"type": "snapshot", "seq": value["seq"], "peers": result,
            "capabilities": list(CAPABILITIES)}
