"""고정 참조 결과를 한 번 검토하고 사람 채택용 제안으로 묶는다."""
from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Callable

from .reference_momentum import content_hash
from .us_reference import (
    AdvisoryProposal,
    ExitPolicy,
    ReferenceReview,
    proposal_digest,
)

AskFn = Callable[..., str]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_reference_packet(fixtures: Path, market: str) -> dict:
    """검증된 manifest·결과·로컬 체결 가격을 한 묶음으로 읽는다."""
    market = market.upper()
    if market not in {"US", "KR"}:
        raise ValueError("시장은 US 또는 KR이어야 합니다.")
    manifest = _load(fixtures / "reference_manifest.json")
    result = _load(fixtures / f"{market.lower()}_momentum_result.json")
    selection = _load(fixtures / "reference_selection.json")
    quotes = _load(fixtures / f"{market.lower()}_reference.json")

    if result["manifest_hash"] != content_hash(manifest):
        raise ValueError("참조 결과와 전략 manifest가 다릅니다.")
    result_without_hash = {key: value for key, value in result.items() if key != "result_hash"}
    if content_hash(result_without_hash) != result["result_hash"]:
        raise ValueError("참조 결과가 변경되었거나 손상되었습니다.")
    if selection["result_hashes"][market] != result["result_hash"]:
        raise ValueError("참조 시장 선택과 결과가 다릅니다.")

    latest = result["months"][-1]
    selected = tuple(latest["selected"])
    prices = {}
    exchanges = {}
    names = {}
    for ticker in selected:
        quote_key = ticker.removesuffix(".KS")
        if quote_key not in quotes["prices"]:
            raise ValueError(f"{ticker}의 로컬 모의 체결 가격이 없습니다.")
        prices[ticker] = int(quotes["prices"][quote_key])
        exchange_map = quotes.get("exchanges") or {}
        exchanges[ticker] = exchange_map.get(quote_key) or (
            "KRX" if market == "KR" else ""
        )
        if not exchanges[ticker]:
            raise ValueError(f"{ticker}의 주문 거래소가 없습니다.")
        names[ticker] = (quotes.get("names") or {}).get(quote_key, ticker)

    return {
        "schema_version": 1,
        "market": market,
        "currency": result["currency"],
        "scope": "local_mock",
        "manifest": manifest,
        "manifest_hash": result["manifest_hash"],
        "input_hash": result["input_hash"],
        "result": result,
        "result_hash": result["result_hash"],
        "reference_market": selection["reference_market"],
        "selected": selected,
        "scores": latest["scores"],
        "prices": prices,
        "exchanges": exchanges,
        "names": names,
        "initial_cash": int(quotes["initial_cash"]),
        "as_of": latest["month"],
        "fixture_notice": (
            "고정 바스켓·비공식 조정주가를 사용한 학습용 결과입니다. "
            "수익 보장이나 투자 추천이 아닙니다."
        ),
    }


def _parse_review(answer: str) -> tuple[str, str, str]:
    labels = {
        "약점": "고정 바스켓에는 생존편향이 있어 시장 전체 결과로 일반화할 수 없습니다.",
        "반대 근거": "시장과 기간에 따라 모멘텀 결과가 약하거나 반대로 나타날 수 있습니다.",
        "다음 질문": "한 종목 최대 비중을 낮추면 오늘 주문이 막히는가?",
    }
    for line in answer.splitlines():
        for label in tuple(labels):
            prefix = f"{label}:"
            if line.strip().startswith(prefix):
                value = line.strip()[len(prefix):].strip()
                if value:
                    labels[label] = value
    return labels["약점"], labels["반대 근거"], labels["다음 질문"]


def build_reference_advisory(
    packet: dict,
    *,
    ask_fn: AskFn | None = None,
) -> AdvisoryProposal:
    """AI는 약점·반대 근거·다음 질문만 말하고 계산값은 바꾸지 않는다."""
    summary = packet["result"]["periods"]
    material = json.dumps(
        {
            "rule": packet["manifest"]["entry"],
            "exit": packet["manifest"]["scheduled_exit"],
            "loss_review": packet["manifest"]["loss_review"],
            "earlier": summary["earlier"],
            "later": summary["later"],
            "limitations": packet["manifest"]["limitations"],
        },
        ensure_ascii=False,
    )
    answer = ""
    if ask_fn is not None:
        answer = ask_fn(
            재료=material,
            질문=(
                "이 고정 참조 실험을 검토하세요. 정확히 '약점:', '반대 근거:', "
                "'다음 질문:' 세 줄만 쓰세요. 종목·비중·가격·수량·주문은 만들거나 바꾸지 마세요."
            ),
        ) or ""
    weakness, contrary, next_question = _parse_review(answer)
    review = ReferenceReview(
        weakness=weakness,
        contrary_evidence=contrary,
        next_question=next_question,
        evidence_ids=(packet["manifest_hash"], packet["result_hash"]),
    )
    cash_weight = 10.0
    each = (100.0 - cash_weight) / len(packet["selected"])
    weights = {ticker: each for ticker in packet["selected"]}
    provisional = AdvisoryProposal(
        schema_version=1,
        proposal_id="",
        manifest_hash=packet["manifest_hash"],
        input_hash=packet["input_hash"],
        result_hash=packet["result_hash"],
        market=packet["market"],
        currency=packet["currency"],
        scope="local_mock",
        selected=tuple(packet["selected"]),
        suggested_weights=weights,
        cash_weight=cash_weight,
        exchanges=dict(packet["exchanges"]),
        review=review,
        exit_policy=ExitPolicy(
            rebalance_months=1,
            sell_when_outside_target=True,
            stop_loss_review_pct=10.0,
            automatic_stop_loss=False,
        ),
    )
    return replace(provisional, proposal_id=proposal_digest(provisional))


def save_advisory(proposal: AdvisoryProposal, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(proposal), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_advisory(path: Path) -> AdvisoryProposal:
    raw = _load(path)
    review = raw["review"]
    proposal = AdvisoryProposal(
        schema_version=int(raw["schema_version"]),
        proposal_id=raw["proposal_id"],
        manifest_hash=raw["manifest_hash"],
        input_hash=raw["input_hash"],
        result_hash=raw["result_hash"],
        market=raw["market"],
        currency=raw["currency"],
        scope=raw["scope"],
        selected=tuple(raw["selected"]),
        suggested_weights={
            ticker: float(weight)
            for ticker, weight in raw["suggested_weights"].items()
        },
        cash_weight=float(raw["cash_weight"]),
        exchanges=dict(raw["exchanges"]),
        review=ReferenceReview(
            weakness=review["weakness"],
            contrary_evidence=review["contrary_evidence"],
            next_question=review["next_question"],
            evidence_ids=tuple(review["evidence_ids"]),
        ),
        exit_policy=ExitPolicy(**raw["exit_policy"]),
    )
    if proposal_digest(proposal) != proposal.proposal_id:
        raise ValueError("판단 제안이 변경되었거나 손상되었습니다. 다시 만드세요.")
    return proposal
