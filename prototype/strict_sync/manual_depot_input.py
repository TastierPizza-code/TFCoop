"""Bounded launcher depot input and observed-engine receipt contract.

No coordinates, prices, outcomes or engine objects are invented here. The four
site indices are a limited test layout evaluated by the real Lua engine adapter.
"""
from __future__ import annotations

import copy

from .core import ProtocolError, canonical_json, _hash


SITES = (1, 2, 3, 4)
ROTATIONS = (0, 90, 180, 270)
REJECTION_REASONS = frozenset(("site_occupied", "outside_map", "water", "too_uneven",
                                "engine_rejected", "insufficient_funds"))
MAX_PREVIEW_BYTES = 2048
MAX_BUILD_RECEIPT_BYTES = 4096


def _need(value, detail):
    if not value:
        raise ProtocolError("manual depot: " + detail)


def validate_command(command):
    canonical_json(command, limit=256)
    _need(type(command) is dict, "command must be a plain object")
    op = command.get("op")
    if op == "SET_PAUSED":
        _need(set(command) == {"op", "value"} and type(command["value"]) is bool,
              "SET_PAUSED requires only a boolean value")
    elif op == "END_TEST":
        _need(set(command) == {"op"}, "END_TEST accepts no arguments")
    elif op == "BUILD_DEPOT":
        _need(set(command) == {"op", "site", "rotation"}
              and type(command["site"]) is int and command["site"] in SITES
              and type(command["rotation"]) is int and command["rotation"] in ROTATIONS,
              "BUILD_DEPOT requires a site 1..4 and rotation 0/90/180/270")
    else:
        _need(False, "unsupported command")
    return copy.deepcopy(command)


def _position(value):
    return type(value) is list and len(value) == 3 and all(type(v) is int for v in value)


def validate_preview(value, command, world):
    validate_command(command)
    _need(command["op"] == "BUILD_DEPOT", "preview is only for depot commands")
    canonical_json(value, limit=MAX_PREVIEW_BYTES)
    _need(type(value) is dict and set(value) == {"allowed", "reason", "cost", "position_mm",
                                                "rotation", "proposal_digest", "state_digest"},
          "preview fields differ from the contract")
    _need(type(value["allowed"]) is bool and type(value["rotation"]) is int
          and value["rotation"] == command["rotation"], "invalid preview approval or rotation")
    _hash(value["proposal_digest"], "depot proposal digest")
    _hash(value["state_digest"], "depot preview state")
    _need(value["state_digest"] == world["state_digest"], "preview refers to another observed world")
    _need(value["position_mm"] is None or _position(value["position_mm"]), "invalid preview position")
    _need(value["cost"] is None or type(value["cost"]) is int and value["cost"] >= 0,
          "invalid preview cost")
    if value["allowed"]:
        _need(value["reason"] == "" and _position(value["position_mm"])
              and type(value["cost"]) is int and value["cost"] > 0,
              "approved depot requires an observed position and positive construction cost")
    else:
        _need(type(value["reason"]) is str and value["reason"] in REJECTION_REASONS,
              "unknown depot rejection reason")
    return copy.deepcopy(value)


def validate_build_receipt(value, command, command_key, preview, before, after):
    preview = validate_preview(preview, command, before)
    _need(preview["allowed"] is True, "cannot apply a rejected depot")
    canonical_json(value, limit=MAX_BUILD_RECEIPT_BYTES)
    _need(type(value) is dict and set(value) == {"success", "result", "state_digest"}
          and value["success"] is True and value["state_digest"] == after["state_digest"],
          "depot lacks a successful fresh callback receipt")
    _need(all(after[key] == before[key] for key in ("frame", "sim_time_us", "paused"))
          and after["state_digest"] != before["state_digest"],
          "depot changed time/pause or did not change its observed world")
    result = value["result"]
    _need(type(result) is dict and set(result) == {"op", "site", "rotation", "logical_id", "cost",
          "balance_before", "balance_after", "loan_before", "loan_after", "position_mm"},
          "depot callback fields differ from the contract")
    _need(result["op"] == "BUILD_DEPOT" and result["site"] == command["site"]
          and type(result["site"]) is int and type(result["rotation"]) is int
          and result["rotation"] == command["rotation"] and result["logical_id"] == command_key
          and _position(result["position_mm"]) and result["position_mm"] == preview["position_mm"],
          "depot callback does not identify the approved placement")
    _need(all(type(result[key]) is int for key in ("cost", "balance_before", "balance_after", "loan_before", "loan_after"))
          and result["cost"] == preview["cost"]
          and result["balance_before"] - result["balance_after"] == result["cost"]
          and result["loan_before"] == result["loan_after"],
          "depot actual company debit differs from its approved cost")
    return copy.deepcopy(value)
