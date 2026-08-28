"""저장된 채택 스펙에서 exact local-mock 계획을 만들고 승인 실행한다."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .plan_store import PlanClaimError, claim_pending_plan, finish_plan
from .us_committee import load_reference_packet
from .us_mock import LocalMockBroker
from .us_reference import (
    Guardrails,
    OrderPlan,
    build_order_plan,
    execute_approved_plan,
    holdings_digest,
    load_adopted_spec,
)


def _reference_market(fixtures: Path) -> str:
    selection = json.loads(
        (fixtures / "reference_selection.json").read_text(encoding="utf-8")
    )
    return selection["reference_market"]


def _broker(fixtures: Path, state: Path, market: str) -> LocalMockBroker:
    packet = load_reference_packet(fixtures, market)
    return LocalMockBroker(
        market=market,
        currency=packet["currency"],
        prices=packet["prices"],
        initial_cash=packet["initial_cash"],
        ledger_path=state / f"{market.lower()}-ledger.json",
    )


def create_reference_plan(
    fixtures: Path,
    state: Path,
    *,
    market: str | None = None,
    now: str,
) -> OrderPlan:
    market = (market or _reference_market(fixtures)).upper()
    packet = load_reference_packet(fixtures, market)
    spec = load_adopted_spec(state / f"{market.lower()}-active-spec.json")
    if spec.market != market or spec.result_hash != packet["result_hash"]:
        raise ValueError("채택 스펙과 현재 고정 참조 결과가 다릅니다.")
    broker = _broker(fixtures, state, market)
    balance = broker.get_balance()
    created = _parse_time(now)
    return build_order_plan(
        spec,
        account_id=f"course-local-{market.lower()}",
        cash=balance["cash"],
        holdings=balance["holdings"],
        ledger_revision=balance["revision"],
        prices=broker.prices,
        quote_timestamp=f"{packet['as_of']}-01T00:00:00Z",
        guardrails=Guardrails(
            max_weight=spec.max_position_weight,
            min_cash=spec.cash_weight,
        ),
        created_at=_format_time(created),
        expires_at=_format_time(created + timedelta(minutes=15)),
    )


def approve_reference_plan(
    fixtures: Path,
    state: Path,
    pending_path: Path,
    *,
    plan_id: str,
    channel_id: int,
    sender_id: int,
    message_id: int,
    now: str,
) -> list[dict]:
    market = _reference_market(fixtures)
    spec = load_adopted_spec(state / f"{market.lower()}-active-spec.json")
    broker = _broker(fixtures, state, market)
    balance = broker.get_balance()
    try:
        plan = claim_pending_plan(
            pending_path,
            plan_id=plan_id,
            channel_id=channel_id,
            sender_id=sender_id,
            message_id=message_id,
            active_spec_version=spec.spec_version,
            ledger_revision=balance["revision"],
            holdings_hash=holdings_digest(balance["cash"], balance["holdings"]),
            now=now,
        )
    except PlanClaimError as error:
        raise RuntimeError(str(error)) from error
    try:
        fills = execute_approved_plan(plan, plan_id, broker)
    except Exception as error:
        finish_plan(
            pending_path,
            plan_id,
            status="failed",
            failure_reason=f"{type(error).__name__}: {error}",
        )
        raise
    finish_plan(pending_path, plan_id, status="executed")
    return fills


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_time(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")
