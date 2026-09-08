"""Bounded guided input and compared observed-engine receipt contracts."""
from __future__ import annotations

import copy

from .core import ProtocolError, canonical_json, _hash
from .guided_catalog import STEPS, get_step

MAX_PREVIEW_BYTES = 8192
MAX_GUIDED_RECEIPT_BYTES = 16384
REJECTION_REASONS = frozenset(("not_ready", "site_occupied", "insufficient_funds",
    "missing_dependency", "unsupported_capability", "engine_rejected"))


def _need(condition, reason):
    if not condition:
        raise ProtocolError("guided input: " + reason)


def validate_command(command):
    canonical_json(command, limit=256)
    _need(type(command) is dict, "command must be a plain object")
    if command.get("op") == "END_TEST":
        _need(set(command) == {"op"}, "END_TEST accepts no arguments")
    else:
        _need(set(command) == {"op", "step"} and command.get("op") == "GUIDED_ACTION"
              and type(command["step"]) is int and 1 <= command["step"] <= len(STEPS),
              "GUIDED_ACTION requires one known integer step")
    return copy.deepcopy(command)


def validate_preview(value, command, world):
    validate_command(command)
    _need(command["op"] == "GUIDED_ACTION", "preview requires a guided action")
    step = get_step(command["step"])
    canonical_json(value, limit=MAX_PREVIEW_BYTES)
    _need(type(value) is dict and set(value) == {"allowed", "reason", "step", "action", "state_digest", "observation"},
          "preview fields differ from the contract")
    _need(type(value["allowed"]) is bool and type(value["step"]) is int
          and value["step"] == step["step"] and value["action"] == step["action"],
          "preview identifies another catalogue action")
    _hash(value["state_digest"], "guided preview state")
    _need(value["state_digest"] == world["state_digest"], "preview refers to another observed world")
    _need(type(value["observation"]) is dict, "preview lacks actual observations")
    company = value["observation"].get("company")
    _need(type(company) is dict and set(company) == {"balance", "loan"}
          and all(type(item) is int for item in company.values()),
          "preview lacks actual company values")
    if value["allowed"]:
        _need(value["reason"] == "", "approved action has a rejection reason")
    else:
        _need(value["reason"] in REJECTION_REASONS, "unknown preview rejection reason")
        _need(value["reason"] != "not_ready" or step["read_only"], "only observation steps may await readiness")
    return copy.deepcopy(value)


def validate_action_receipt(value, command, command_key, preview, before, after):
    preview = validate_preview(preview, command, before)
    step = get_step(command["step"])
    _need(preview["allowed"] is True, "cannot apply a rejected action")
    canonical_json(value, limit=MAX_GUIDED_RECEIPT_BYTES)
    _need(type(value) is dict and set(value) == {"success", "result", "state_digest"}
          and value["success"] is True and value["state_digest"] == after["state_digest"],
          "action lacks a successful fresh receipt")
    _need(all(after[key] == before[key] for key in ("frame", "sim_time_us")),
          "action changed the held native time")
    _need(after["paused"] is step.get("pause", before["paused"]), "action changed pause incorrectly")
    if step["read_only"]:
        _need(after == before, "read-only observation changed the world")
    result = value["result"]
    _need(type(result) is dict and set(result) == {"op", "step", "action", "command_key", "effect"}
          and result["op"] == "GUIDED_ACTION" and type(result["step"]) is int
          and result["step"] == step["step"] and result["action"] == step["action"]
          and result["command_key"] == command_key, "receipt identifies another action")
    effect = result["effect"]
    _need(type(effect) is dict and set(effect) == {"balance_before", "balance_after", "loan_before", "loan_after",
                                               "observed", "kind", "target", "created", "removed"},
          "receipt effect fields differ from the observed contract")
    _need(all(type(effect[key]) is int for key in ("balance_before", "balance_after", "loan_before", "loan_after"))
          and effect["loan_before"] == effect["loan_after"], "invalid actual company values")
    _need(preview["observation"]["company"] == {"balance": effect["balance_before"], "loan": effect["loan_before"]},
          "receipt company before-state differs from the approved preview")
    if step["action"] == "BUY_BUS":
        _need(effect["balance_after"] < effect["balance_before"], "purchase lacks an actual company debit")
    elif step["action"] == "SELL_BUS":
        _need(effect["balance_after"] >= effect["balance_before"], "sale unexpectedly debited company money")
    else:
        _need(effect["balance_after"] == effect["balance_before"], "no-cost action changed company money")
    _need(type(effect["observed"]) is dict and bool(effect["observed"])
          and type(effect["target"]) is str and len(effect["target"]) <= 128,
          "receipt lacks concrete observed postconditions")
    _need(effect["kind"] == ("observation" if step["read_only"] else "callback"),
          "observation and actual callback evidence must be distinguished")
    for field in ("created", "removed"):
        ids = effect[field]
        _need(type(ids) is list and len(ids) <= 16 and all(type(key) is str and 0 < len(key) <= 128 for key in ids)
              and len(ids) == len(set(ids)), "invalid logical object identities")
    if step["read_only"]:
        _need(effect["balance_before"] == effect["balance_after"] and not effect["created"] and not effect["removed"],
              "read-only observation altered company or object membership")
    return copy.deepcopy(value)
