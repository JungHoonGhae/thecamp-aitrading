"""Telegram 승인용 로컬 OrderPlan 저장소와 원자적 상태 전이."""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .us_reference import OrderPlan, PlannedOrder, plan_digest


class PlanClaimError(RuntimeError):
    """승인 요청이 저장된 계획과 정확히 일치하지 않을 때 발생한다."""


def _plan_from_dict(raw: dict) -> OrderPlan:
    values = dict(raw)
    values["orders"] = tuple(PlannedOrder(**order) for order in raw["orders"])
    values["blocks"] = tuple(raw["blocks"])
    values["holdings_snapshot"] = {
        ticker: int(qty) for ticker, qty in raw["holdings_snapshot"].items()
    }
    values["prices"] = {
        ticker: int(price) for ticker, price in raw["prices"].items()
    }
    return OrderPlan(**values)


def _write_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


@contextmanager
def _claim_lock(path: Path) -> Iterator[None]:
    lock = path.with_name(f".{path.name}.lock")
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise PlanClaimError("plan claim is already executing") from error
    try:
        yield
    finally:
        lock.rmdir()


def save_pending_plan(
    path: Path,
    plan: OrderPlan,
    *,
    channel_id: int,
    sender_id: int,
    message_id: int,
) -> None:
    if plan_digest(plan) != plan.plan_id:
        raise ValueError("변경되거나 손상된 주문 계획은 저장할 수 없습니다.")
    record = {
        "schema_version": 1,
        "status": "pending",
        "plan_id": plan.plan_id,
        "channel_id": int(channel_id),
        "sender_id": int(sender_id),
        "message_id": int(message_id),
        "created_at": plan.created_at,
        "expires_at": plan.expires_at,
        "failure_reason": "",
        "plan": asdict(plan),
    }
    _write_atomic(path, record)


def load_plan_record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _terminal_failure(path: Path, record: dict, reason: str) -> None:
    record["status"] = "failed"
    record["failure_reason"] = reason
    _write_atomic(path, record)


def claim_pending_plan(
    path: Path,
    *,
    plan_id: str,
    channel_id: int,
    sender_id: int,
    message_id: int,
    active_spec_version: int,
    ledger_revision: int,
    holdings_hash: str,
    now: str,
) -> OrderPlan:
    """모든 바인딩을 확인하고 pending을 executing으로 먼저 바꾼다."""
    with _claim_lock(path):
        record = load_plan_record(path)
        if record["plan_id"] != plan_id:
            raise PlanClaimError("wrong plan_id")
        if int(record["channel_id"]) != int(channel_id):
            raise PlanClaimError("wrong channel")
        if int(record["sender_id"]) != int(sender_id):
            raise PlanClaimError("wrong sender")
        if int(record["message_id"]) != int(message_id):
            raise PlanClaimError("wrong message")
        if record["status"] != "pending":
            raise PlanClaimError(f"plan is already {record['status']}")
        if _parse_time(now) > _parse_time(record["expires_at"]):
            record["status"] = "expired"
            record["failure_reason"] = "approval expired"
            _write_atomic(path, record)
            raise PlanClaimError("plan approval expired")

        try:
            plan = _plan_from_dict(record["plan"])
        except (KeyError, TypeError, ValueError) as error:
            _terminal_failure(path, record, "tampered plan schema")
            raise PlanClaimError("tampered plan schema") from error
        if plan.plan_id != record["plan_id"] or plan_digest(plan) != plan.plan_id:
            _terminal_failure(path, record, "tampered plan digest")
            raise PlanClaimError("tampered plan digest")
        if plan.environment != "local_mock":
            _terminal_failure(path, record, "wrong environment")
            raise PlanClaimError("wrong environment")
        if plan.active_spec_version != int(active_spec_version):
            _terminal_failure(path, record, "active spec changed")
            raise PlanClaimError("active spec changed")
        if plan.ledger_revision != int(ledger_revision):
            _terminal_failure(path, record, "ledger revision changed")
            raise PlanClaimError("ledger revision changed")
        if plan.holdings_hash != holdings_hash:
            _terminal_failure(path, record, "holdings changed")
            raise PlanClaimError("holdings changed")

        record["status"] = "executing"
        record["failure_reason"] = ""
        _write_atomic(path, record)
        return plan


def finish_plan(
    path: Path,
    plan_id: str,
    *,
    status: str,
    failure_reason: str = "",
) -> None:
    if status not in {"executed", "failed"}:
        raise ValueError("finish status must be executed or failed")
    with _claim_lock(path):
        record = load_plan_record(path)
        if record["plan_id"] != plan_id:
            raise PlanClaimError("wrong plan_id")
        if record["status"] != "executing":
            raise PlanClaimError(f"plan is {record['status']}, not executing")
        record["status"] = status
        record["failure_reason"] = failure_reason
        _write_atomic(path, record)


def cancel_plan(
    path: Path,
    *,
    plan_id: str,
    channel_id: int,
    sender_id: int,
    message_id: int,
) -> None:
    with _claim_lock(path):
        record = load_plan_record(path)
        if record["plan_id"] != plan_id:
            raise PlanClaimError("wrong plan_id")
        if int(record["channel_id"]) != int(channel_id):
            raise PlanClaimError("wrong channel")
        if int(record["sender_id"]) != int(sender_id):
            raise PlanClaimError("wrong sender")
        if int(record["message_id"]) != int(message_id):
            raise PlanClaimError("wrong message")
        if record["status"] != "pending":
            raise PlanClaimError(f"plan is already {record['status']}")
        record["status"] = "cancelled"
        record["failure_reason"] = "cancelled by owner"
        _write_atomic(path, record)


def _parse_time(value: str) -> datetime:
    if not value:
        raise PlanClaimError("plan timestamp is missing")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
