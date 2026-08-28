"""US/KR 참조 실험의 사람 채택과 결정적 로컬 모의 주문 계획."""
from __future__ import annotations

import math
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Protocol

from .reference_momentum import content_hash


@dataclass(frozen=True)
class ReferenceReview:
    weakness: str
    contrary_evidence: str
    next_question: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExitPolicy:
    rebalance_months: int
    sell_when_outside_target: bool
    stop_loss_review_pct: float
    automatic_stop_loss: bool


@dataclass(frozen=True)
class AdvisoryProposal:
    schema_version: int
    proposal_id: str
    manifest_hash: str
    input_hash: str
    result_hash: str
    market: str
    currency: str
    scope: str
    selected: tuple[str, ...]
    suggested_weights: dict[str, float]
    cash_weight: float
    exchanges: dict[str, str]
    review: ReferenceReview
    exit_policy: ExitPolicy


@dataclass(frozen=True)
class AdoptedSpec:
    schema_version: int
    spec_hash: str
    spec_version: int
    source_proposal_id: str
    manifest_hash: str
    input_hash: str
    result_hash: str
    market: str
    currency: str
    scope: str
    weights: dict[str, float]
    cash_weight: float
    max_position_weight: float
    exit_policy: ExitPolicy
    exchanges: dict[str, str]


@dataclass(frozen=True)
class Guardrails:
    max_weight: float
    min_cash: float
    forbidden_tickers: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlannedOrder:
    ticker: str
    side: str
    qty: int
    limit_price: int
    exchange: str
    order_key: str = ""


@dataclass(frozen=True)
class OrderPlan:
    schema_version: int
    plan_id: str
    account_id: str
    created_at: str
    expires_at: str
    ledger_revision: int
    holdings_hash: str
    manifest_hash: str
    input_hash: str
    result_hash: str
    proposal_hash: str
    spec_hash: str
    active_spec_version: int
    market: str
    currency: str
    environment: str
    quote_timestamp: str
    quote_unit: str
    cash_snapshot: int
    holdings_snapshot: dict[str, int]
    prices: dict[str, int]
    orders: tuple[PlannedOrder, ...]
    blocks: tuple[str, ...]


class LimitOrderBroker(Protocol):
    market: str

    def place_limit_order(
        self,
        ticker: str,
        side: str,
        qty: int,
        limit_price: int,
        exchange: str,
    ) -> dict:
        ...


def _proposal_content(proposal: AdvisoryProposal) -> dict:
    return {
        key: value
        for key, value in asdict(proposal).items()
        if key != "proposal_id"
    }


def proposal_digest(proposal: AdvisoryProposal) -> str:
    return content_hash(_proposal_content(proposal))


def _spec_content(spec: AdoptedSpec) -> dict:
    return {
        key: value
        for key, value in asdict(spec).items()
        if key != "spec_hash"
    }


def spec_digest(spec: AdoptedSpec) -> str:
    return content_hash(_spec_content(spec))


def save_adopted_spec(spec: AdoptedSpec, path: Path) -> None:
    if spec_digest(spec) != spec.spec_hash:
        raise ValueError("변경되거나 손상된 스펙은 저장할 수 없습니다.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(spec), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_adopted_spec(path: Path) -> AdoptedSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    spec = AdoptedSpec(
        schema_version=int(raw["schema_version"]),
        spec_hash=raw["spec_hash"],
        spec_version=int(raw["spec_version"]),
        source_proposal_id=raw["source_proposal_id"],
        manifest_hash=raw["manifest_hash"],
        input_hash=raw["input_hash"],
        result_hash=raw["result_hash"],
        market=raw["market"],
        currency=raw["currency"],
        scope=raw["scope"],
        weights={ticker: float(value) for ticker, value in raw["weights"].items()},
        cash_weight=float(raw["cash_weight"]),
        max_position_weight=float(raw["max_position_weight"]),
        exit_policy=ExitPolicy(**raw["exit_policy"]),
        exchanges=dict(raw["exchanges"]),
    )
    if spec_digest(spec) != spec.spec_hash:
        raise ValueError("채택 스펙이 변경되었거나 손상되었습니다.")
    return spec


def adopt_proposal(
    proposal: AdvisoryProposal,
    accepted_proposal_id: str,
    *,
    max_position_weight: float = 40,
    spec_version: int = 1,
) -> AdoptedSpec:
    """표시된 제안 전체와 같은 경우에만 local-mock 스펙으로 채택한다."""
    if proposal_digest(proposal) != proposal.proposal_id:
        raise ValueError("판단 제안이 변경되었거나 손상되었습니다. 다시 만드세요.")
    if accepted_proposal_id != proposal.proposal_id:
        raise ValueError("제안 번호가 다릅니다. 현재 제안을 다시 확인하세요.")
    if proposal.scope != "local_mock":
        raise ValueError("수업 제안은 local_mock 범위에서만 채택할 수 있습니다.")
    if spec_version < 1:
        raise ValueError("스펙 버전은 1 이상이어야 합니다.")
    if not math.isfinite(max_position_weight) or not 0 < max_position_weight <= 100:
        raise ValueError("한 종목 최대 비중이 잘못되었습니다.")

    provisional = AdoptedSpec(
        schema_version=1,
        spec_hash="",
        spec_version=spec_version,
        source_proposal_id=proposal.proposal_id,
        manifest_hash=proposal.manifest_hash,
        input_hash=proposal.input_hash,
        result_hash=proposal.result_hash,
        market=proposal.market,
        currency=proposal.currency,
        scope=proposal.scope,
        weights=dict(proposal.suggested_weights),
        cash_weight=proposal.cash_weight,
        max_position_weight=float(max_position_weight),
        exit_policy=proposal.exit_policy,
        exchanges=dict(proposal.exchanges),
    )
    return replace(provisional, spec_hash=spec_digest(provisional))


def holdings_digest(cash: int, holdings: dict[str, int]) -> str:
    return content_hash({
        "cash": int(cash),
        "holdings": {ticker: int(holdings[ticker]) for ticker in sorted(holdings)},
    })


def _order_content(order: PlannedOrder) -> dict:
    return {
        "ticker": order.ticker,
        "side": order.side,
        "qty": order.qty,
        "limit_price": order.limit_price,
        "exchange": order.exchange,
    }


def _plan_content(plan: OrderPlan) -> dict:
    payload = asdict(plan)
    payload.pop("plan_id")
    payload["orders"] = [_order_content(order) for order in plan.orders]
    return payload


def plan_digest(plan: OrderPlan) -> str:
    return content_hash(_plan_content(plan))


def build_order_plan(
    spec: AdoptedSpec,
    *,
    account_id: str = "course-local",
    cash: int,
    holdings: dict[str, int],
    ledger_revision: int = 0,
    prices: dict[str, int],
    quote_timestamp: str = "",
    guardrails: Guardrails,
    exchanges: dict[str, str] | None = None,
    environment: str = "local_mock",
    created_at: str = "",
    expires_at: str = "",
) -> OrderPlan:
    """확정 스펙과 한 시점의 계좌·가격으로 해시 고정 주문 계획을 만든다."""
    blocks: list[str] = []
    if spec_digest(spec) != spec.spec_hash:
        blocks.append("채택 스펙이 변경되었거나 손상되었습니다")
    if spec.scope != "local_mock" or environment != "local_mock":
        blocks.append("수업 주문 계획은 local_mock 환경만 허용합니다")
    if not account_id:
        blocks.append("로컬 모의계좌 ID가 없습니다")
    if ledger_revision < 0:
        blocks.append("장부 버전이 잘못되었습니다")
    if not math.isfinite(spec.cash_weight) or not 0 <= spec.cash_weight <= 100:
        blocks.append("현금 비중이 잘못되었습니다")
    if spec.cash_weight < guardrails.min_cash:
        blocks.append(
            f"현금 목표 {spec.cash_weight:g}% < 최소 현금 {guardrails.min_cash:g}%"
        )

    weight_sum = 0.0
    effective_max = min(spec.max_position_weight, guardrails.max_weight)
    for ticker, weight in spec.weights.items():
        if not math.isfinite(weight) or weight < 0:
            blocks.append(f"{ticker} — 목표 비중이 잘못되었습니다")
            continue
        weight_sum += weight
        if ticker in guardrails.forbidden_tickers:
            blocks.append(f"{ticker} — 금지 종목")
        if weight > effective_max:
            blocks.append(
                f"{ticker} 목표 {weight:g}% > 한 종목 최대 비중 {effective_max:g}%"
            )
        if ticker not in prices or int(prices[ticker]) <= 0:
            blocks.append(f"{ticker} — 가격이 없거나 잘못되었습니다")
    if not math.isclose(weight_sum + spec.cash_weight, 100, abs_tol=1e-6):
        blocks.append(
            f"종목과 현금의 비중 합이 {weight_sum + spec.cash_weight:g}%입니다. 100%로 맞추세요"
        )
    for ticker, qty in holdings.items():
        if int(qty) < 0:
            blocks.append(f"{ticker} — 보유 수량이 잘못되었습니다")
        if ticker not in prices or int(prices[ticker]) <= 0:
            blocks.append(f"{ticker} — 보유 종목의 가격이 없습니다")

    normalized_holdings = {
        ticker: int(qty) for ticker, qty in sorted(holdings.items()) if int(qty)
    }
    normalized_prices = {ticker: int(value) for ticker, value in sorted(prices.items())}
    total = int(cash) + sum(
        qty * normalized_prices.get(ticker, 0)
        for ticker, qty in normalized_holdings.items()
    )
    if total <= 0:
        blocks.append("계좌가 비어 있습니다")

    orders: list[PlannedOrder] = []
    if not blocks:
        exchange_map = {**spec.exchanges, **(exchanges or {})}
        for ticker in sorted(set(normalized_holdings) | set(spec.weights)):
            price = normalized_prices.get(ticker)
            if not price:
                continue
            current_qty = normalized_holdings.get(ticker, 0)
            target_value = total * spec.weights.get(ticker, 0) / 100
            gap = target_value - current_qty * price
            qty = int(abs(gap) // price)
            if qty <= 0:
                continue
            side = "buy" if gap > 0 else "sell"
            if side == "sell":
                qty = min(qty, current_qty)
            exchange = exchange_map.get(ticker, "")
            if not exchange:
                blocks.append(f"{ticker} — 주문 거래소가 없습니다")
                continue
            orders.append(PlannedOrder(ticker, side, qty, price, exchange))
        orders.sort(key=lambda order: (order.side != "sell", order.ticker))
        projected_cash = int(cash) + sum(
            order.qty * order.limit_price * (1 if order.side == "sell" else -1)
            for order in orders
        )
        minimum_cash = total * guardrails.min_cash / 100
        if projected_cash < minimum_cash:
            blocks.append(
                f"주문 뒤 현금 {projected_cash:g} < 최소 현금 {minimum_cash:g}"
            )
        if blocks:
            orders.clear()

    provisional = OrderPlan(
        schema_version=1,
        plan_id="",
        account_id=account_id,
        created_at=created_at,
        expires_at=expires_at,
        ledger_revision=ledger_revision,
        holdings_hash=holdings_digest(int(cash), normalized_holdings),
        manifest_hash=spec.manifest_hash,
        input_hash=spec.input_hash,
        result_hash=spec.result_hash,
        proposal_hash=spec.source_proposal_id,
        spec_hash=spec.spec_hash,
        active_spec_version=spec.spec_version,
        market=spec.market,
        currency=spec.currency,
        environment=environment,
        quote_timestamp=quote_timestamp,
        quote_unit="minor_currency_unit",
        cash_snapshot=int(cash),
        holdings_snapshot=normalized_holdings,
        prices=normalized_prices,
        orders=tuple(orders),
        blocks=tuple(blocks),
    )
    plan_id = plan_digest(provisional)
    bound_orders = tuple(
        replace(order, order_key=f"{plan_id}:{index}")
        for index, order in enumerate(provisional.orders)
    )
    return replace(provisional, plan_id=plan_id, orders=bound_orders)


def execute_approved_plan(
    plan: OrderPlan,
    approved_plan_id: str,
    broker: LimitOrderBroker,
) -> list[dict]:
    """다시 계산하지 않고 사람이 승인한 정확한 local-mock 계획만 실행한다."""
    if plan_digest(plan) != plan.plan_id:
        raise ValueError("주문 계획이 변경되었거나 손상되었습니다. 다시 만드세요.")
    if any(
        order.order_key != f"{plan.plan_id}:{index}"
        for index, order in enumerate(plan.orders)
    ):
        raise ValueError("주문 키가 계획과 다릅니다. 다시 만드세요.")
    if approved_plan_id != plan.plan_id:
        raise ValueError("주문 계획 번호가 다릅니다. 바뀐 주문을 다시 승인하세요.")
    if plan.environment != "local_mock":
        raise ValueError("정확히 한 번 실행 보장은 local_mock에만 적용됩니다.")
    if plan.blocks:
        raise RuntimeError("가드레일 위반이 있어 주문할 수 없습니다.")
    if getattr(broker, "market", plan.market) != plan.market:
        raise ValueError("주문 계획과 모의계좌의 시장이 다릅니다.")
    execute_batch = getattr(broker, "execute_batch", None)
    if execute_batch is not None:
        return execute_batch(plan)
    return [
        broker.place_limit_order(
            order.ticker,
            order.side,
            order.qty,
            order.limit_price,
            order.exchange,
        )
        for order in plan.orders
    ]
