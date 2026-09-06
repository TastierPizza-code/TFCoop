"""Bounded, data-only JSON mailboxes shared with the game's Lua mod."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any

MAX_BYTES = 64 * 1024
MAX_AGE_SECONDS = 3.0
MAX_PREVIEW_POINTS = 128
_KINDS = {"street", "track", "construction", "bulldozer"}
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")


def _number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and abs(value) <= 100_000_000)


def _point(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 3 and all(_number(n) for n in value)


def _validate_presence(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("presence must be an object")
    cursor = value.get("cursor")
    if cursor is not None and not _point(cursor):
        raise ValueError("cursor must be null or three finite coordinates")
    preview = value.get("preview")
    if preview is not None:
        if not isinstance(preview, dict) or preview.get("kind") not in _KINDS:
            raise ValueError("preview kind is invalid")
        points = preview.get("points")
        if (not isinstance(points, list) or len(points) > MAX_PREVIEW_POINTS
                or not all(_point(p) for p in points)):
            raise ValueError("preview points are invalid or too numerous")


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite JSON number")
    return number


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


class Mailbox:
    """Exchange snapshots without executing content from either side.

    Ordinary I/O and malformed-input failures are reported through ``last_error``
    and a false/None return value so the companion UI can stay responsive.
    """

    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory).expanduser().absolute()
        self.last_error: str | None = None

    def read_game(self) -> dict[str, Any] | None:
        try:
            path = self.directory / "game.json"
            with path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                age = time.time() - stat.st_mtime
                if age > MAX_AGE_SECONDS or age < -5:
                    raise ValueError("game snapshot is stale or has an invalid timestamp")
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("game snapshot exceeds 64 KiB")
            value = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant, parse_float=_finite_float,
                               object_pairs_hook=_unique_object)
            if not isinstance(value, dict) or type(value.get("protocol")) is not int or value["protocol"] != 1:
                raise ValueError("unsupported game snapshot protocol")
            _validate_presence(value)
            if "capabilities" in value and not isinstance(value["capabilities"], dict):
                raise ValueError("capabilities must be an object")
            if "status" in value and (not isinstance(value["status"], str) or len(value["status"]) > 2048):
                raise ValueError("status must be a short string")
            if "telemetry" in value and not isinstance(value["telemetry"], dict):
                raise ValueError("telemetry must be an object")
            self.last_error = None
            return value
        except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
            self.last_error = f"Cannot read game snapshot: {exc}"
            return None

    def write_peers(self, snapshot: dict[str, Any]) -> bool:
        temporary: Path | None = None
        try:
            if not isinstance(snapshot, dict):
                raise ValueError("peer snapshot must be an object")
            value = dict(snapshot)
            protocol = value.get("protocol", 1)
            if type(protocol) is not int or protocol != 1:
                raise ValueError("unsupported peer snapshot protocol")
            if type(value.get("connected")) is not bool:
                raise ValueError("connected must be a boolean")
            local_id = value.get("local_peer_id")
            if not isinstance(local_id, str) or len(local_id) > 128:
                raise ValueError("local_peer_id must be a short string")
            peers = value.get("peers")
            if not isinstance(peers, list) or len(peers) > 8:
                raise ValueError("peers must contain at most 8 players")
            ids: set[str] = set()
            for peer in peers:
                if not isinstance(peer, dict):
                    raise ValueError("peer must be an object")
                peer_id, name, color = peer.get("id"), peer.get("name"), peer.get("color")
                if not isinstance(peer_id, str) or not peer_id or len(peer_id) > 128 or peer_id in ids:
                    raise ValueError("peer ids must be unique short strings")
                ids.add(peer_id)
                if not isinstance(name, str) or not name.strip() or len(name) > 64:
                    raise ValueError("peer name must have 1 to 64 characters")
                if not isinstance(color, str) or not _COLOR.fullmatch(color):
                    raise ValueError("peer color must be #rrggbb")
                _validate_presence(peer.get("presence"))
            value["protocol"] = 1
            value["written_at"] = time.time()
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
            if len(raw) > MAX_BYTES:
                raise ValueError("peer snapshot exceeds 64 KiB")
            self.directory.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix=".peers-", suffix=".tmp", dir=self.directory)
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
            target = self.directory / "peers.json"
            for attempt in range(4):
                try:
                    os.replace(temporary, target)
                    break
                except PermissionError:
                    if attempt == 3:
                        raise
                    time.sleep(0.01 * (attempt + 1))
            self.last_error = None
            return True
        except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
            self.last_error = f"Cannot write peer snapshot: {exc}"
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
