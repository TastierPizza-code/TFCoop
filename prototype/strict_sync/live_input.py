"""Bounded local player requests; collecting input never touches the game.

One launcher owns an InputWriter for a freshly prepared run. The immutable
history survives each atomic file replacement; an exclusive transaction lock
prevents concurrent writers from assigning the same sequence number. A crashed
writer's lock is deliberately not stolen. Prepare a new run instead.

Requests are accepted locally, not committed to both games. InputReader.take
only seals a bounded batch for the peer protocol. Network/engine acknowledgments
must be displayed separately by the launcher.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import time

from .core import ProtocolError, ROSTER, _EPOCH, canonical_json, decode_message
from .engine_mailbox import _shared_read


MAX_REQUESTS = 128
MAX_BATCH = 8
MAX_BYTES = 16384
IO_RETRY_SECONDS = 0.25


class InputError(ProtocolError):
    """Invalid identity/history or a request that cannot be admitted."""


class InputBusy(InputError):
    """Another writer owns the queue; never fall through to an unlocked write."""


class InputFull(InputError):
    """The run's bounded history is full; no request was accepted."""


def _identity(epoch, peer):
    if type(epoch) is not str or _EPOCH.fullmatch(epoch) is None:
        raise InputError("invalid live input epoch")
    if type(peer) is not str or peer not in ROSTER:
        raise InputError("invalid live input peer")


def _command(command):
    if type(command) is not dict:
        raise InputError("live input command must be a plain object")
    if command.get("op") == "SET_PAUSED":
        if set(command) != {"op", "value"} or type(command["value"]) is not bool:
            raise InputError("SET_PAUSED requires only a boolean value")
    elif command.get("op") == "END_TEST":
        if set(command) != {"op"}:
            raise InputError("END_TEST does not accept arguments")
    else:
        raise InputError("unsupported live input command")
    # This also rejects subclasses and non-plain op values before copying.
    canonical_json(command)
    return copy.deepcopy(command)


def _retry_io(operation):
    deadline = time.monotonic() + IO_RETRY_SECONDS
    while True:
        try:
            return operation()
        except OSError as exc:
            if getattr(exc, "winerror", None) not in (5, 32, 33) or time.monotonic() >= deadline:
                raise
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))


def _read(path, epoch, peer, command_validator=_command):
    raw = _retry_io(lambda: _shared_read(path, MAX_BYTES))
    if len(raw) > MAX_BYTES:
        raise InputError("live input file exceeds byte limit")
    try:
        document = decode_message(raw)
    except ProtocolError as exc:
        raise InputError("invalid live input JSON") from exc
    if (set(document) != {"protocol", "epoch", "peer", "requests"}
            or type(document["protocol"]) is not int or document["protocol"] != 1
            or document["epoch"] != epoch or document["peer"] != peer):
        raise InputError("live input identity or envelope differs")
    requests = document["requests"]
    if type(requests) is not list or len(requests) > MAX_REQUESTS:
        raise InputError("invalid live input history length")
    ended = False
    for seq, request in enumerate(requests, 1):
        if (type(request) is not dict or set(request) != {"seq", "command"}
                or type(request["seq"]) is not int or request["seq"] != seq):
            raise InputError("live input sequence is not contiguous")
        if ended:
            raise InputError("live input history continues after END_TEST")
        command_validator(request["command"])
        ended = request["command"]["op"] == "END_TEST"
    return document


def _history(document):
    return tuple(canonical_json(request) for request in document["requests"])


def _unchanged(previous, current):
    if len(current) < len(previous) or current[:len(previous)] != previous:
        raise InputError("live input history was truncated or changed")


@contextmanager
def _write_guard(path):
    lock = path.with_name(path.name + ".writer-lock")
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise InputBusy("live input writer is busy; no request was accepted") from exc
    try:
        yield
    finally:
        os.close(descriptor)
        try:
            _retry_io(lock.unlink)
        except OSError:
            # Do not turn a successfully replaced queue into an ambiguous
            # submission failure. The remaining lock rejects future writes.
            pass


def _replace(path, raw):
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _retry_io(lambda: os.replace(temporary, path))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def create(path, epoch, peer):
    """Create a new empty queue before starting workers; never replace a run."""
    _identity(epoch, peer)
    path = Path(path)
    raw = canonical_json({"protocol": 1, "epoch": epoch, "peer": peer, "requests": []}, limit=MAX_BYTES)
    with _write_guard(path):
        # No reader/worker is started until this fresh preparation returns.
        # Exclusive creation preserves an existing queue even on repeated setup.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            # A partial fresh queue must not look like successful preparation.
            # Retain it as evidence; another create must use a fresh path.
            raise


class InputWriter:
    def __init__(self, path, epoch, peer, *, command_validator=_command):
        _identity(epoch, peer)
        if not callable(command_validator):
            raise InputError("input command validator must be callable")
        self._command_validator = command_validator
        self.path, self.epoch, self.peer = Path(path), epoch, peer
        self._history = _history(_read(self.path, epoch, peer, self._command_validator))

    def submit(self, command):
        """Atomically append one real request and return its local sequence."""
        command = self._command_validator(command)
        with _write_guard(self.path):
            document = _read(self.path, self.epoch, self.peer, self._command_validator)
            history = _history(document)
            _unchanged(self._history, history)
            requests = document["requests"]
            if requests and requests[-1]["command"]["op"] == "END_TEST":
                raise InputError("END_TEST was already accepted; input is closed")
            if len(requests) >= MAX_REQUESTS:
                raise InputFull("live input history is full; no request was accepted")
            seq = len(requests) + 1
            requests.append({"seq": seq, "command": command})
            raw = canonical_json(document, limit=MAX_BYTES)
            _replace(self.path, raw)
            self._history = _history(document)
            return seq


class InputReader:
    def __init__(self, path, epoch, peer, *, command_validator=_command):
        _identity(epoch, peer)
        if not callable(command_validator):
            raise InputError("input command validator must be callable")
        self._command_validator = command_validator
        self.path, self.epoch, self.peer = Path(path), epoch, peer
        self._history = _history(_read(self.path, epoch, peer, self._command_validator))
        self._sealed = 0

    def take(self):
        """Seal at most eight oldest new requests, keeping all later requests."""
        document = _read(self.path, self.epoch, self.peer, self._command_validator)
        history = _history(document)
        _unchanged(self._history, history)
        result = copy.deepcopy(document["requests"][self._sealed:self._sealed + MAX_BATCH])
        self._history = history
        self._sealed += len(result)
        return result
