"""토요일에도 즉시 체결되는 미국·한국 주식 로컬 모의계좌."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .us_reference import OrderPlan, holdings_digest


class LocalMockBroker:
    def __init__(
        self,
        *,
        market: str,
        currency: str,
        prices: dict[str, int],
        initial_cash: int,
        ledger_path: Path,
    ):
        self.market = market
        self.currency = currency
        self.prices = dict(prices)
        self.initial_cash = initial_cash
        self.ledger_path = ledger_path

    def _load(self) -> dict:
        if self.ledger_path.is_file():
            ledger = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            if ledger.get("market") != self.market:
                raise ValueError("모의계좌 시장이 다릅니다. 시장별 장부를 따로 쓰세요.")
            return ledger
        return {
            "market": self.market,
            "currency": self.currency,
            "cash": self.initial_cash,
            "holdings": {},
            "orders": [],
            "next_order_no": 1,
            "revision": 0,
            "processed_order_keys": [],
        }

    def _save_atomic(self, ledger: dict) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.ledger_path.with_name(
            f".{self.ledger_path.name}.{os.getpid()}.tmp"
        )
        temporary.write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.ledger_path)

    def _save(self, ledger: dict) -> None:
        self._save_atomic(ledger)

    def reset(self) -> None:
        self.ledger_path.unlink(missing_ok=True)

    def get_balance(self) -> dict:
        ledger = self._load()
        return {
            "market": ledger["market"],
            "currency": ledger["currency"],
            "cash": int(ledger["cash"]),
            "revision": int(ledger.get("revision", 0)),
            "holdings": {
                ticker: int(qty)
                for ticker, qty in (ledger.get("holdings") or {}).items()
                if int(qty) > 0
            },
        }

    def get_orders(self) -> list[dict]:
        """수업용 장부의 주문 기록을 읽기 전용 복사본으로 돌려준다."""
        ledger = self._load()
        return [dict(order) for order in (ledger.get("orders") or [])]

    def place_limit_order(
        self,
        ticker: str,
        side: str,
        qty: int,
        limit_price: int,
        exchange: str = "",
    ) -> dict:
        if side not in ("buy", "sell"):
            raise ValueError("side는 buy 또는 sell이어야 합니다.")
        if qty <= 0:
            raise ValueError("주문 수량은 1주 이상이어야 합니다.")
        market_price = self.prices.get(ticker)
        if not market_price:
            raise ValueError(f"{ticker}의 수업용 가격이 없습니다.")

        ledger = self._load()
        holdings = ledger.setdefault("holdings", {})
        cash = int(ledger["cash"])
        held = int(holdings.get(ticker, 0))
        crosses = limit_price >= market_price if side == "buy" else limit_price <= market_price

        ok = True
        message = "지정가 주문이 체결되었습니다."
        if not crosses:
            ok = False
            message = "지정가가 수업용 현재가에 닿지 않아 미체결입니다."
        elif side == "buy" and cash < qty * market_price:
            ok = False
            message = "수업용 계좌의 현금이 부족합니다."
        elif side == "sell" and held < qty:
            ok = False
            message = "수업용 계좌의 보유 수량이 부족합니다."

        order_no = f"USMOCK-{int(ledger.get('next_order_no', 1)):04d}"
        ledger["next_order_no"] = int(ledger.get("next_order_no", 1)) + 1
        if ok and side == "buy":
            ledger["cash"] = cash - qty * market_price
            holdings[ticker] = held + qty
        elif ok:
            ledger["cash"] = cash + qty * market_price
            remaining = held - qty
            if remaining:
                holdings[ticker] = remaining
            else:
                holdings.pop(ticker, None)

        record = {
            "ok": ok,
            "order_no": order_no,
            "ticker": ticker,
            "exchange": exchange,
            "side": side,
            "qty": qty,
            "limit_price": limit_price,
            "fill_price": market_price if ok else None,
            "message": message,
            "simulated": True,
        }
        ledger.setdefault("orders", []).append(record)
        self._save(ledger)
        return record

    def execute_batch(self, plan: OrderPlan) -> list[dict]:
        """검증된 계획 전체를 메모리에서 처리한 뒤 장부를 한 번만 교체한다."""
        if plan.environment != "local_mock":
            raise ValueError("로컬 모의계좌는 local_mock 계획만 실행합니다.")
        if plan.market != self.market or plan.currency != self.currency:
            raise ValueError("주문 계획과 로컬 모의계좌의 시장 또는 통화가 다릅니다.")

        current = self._load()
        processed = set(current.get("processed_order_keys") or [])
        duplicate = next(
            (order.order_key for order in plan.orders if order.order_key in processed),
            None,
        )
        if duplicate:
            raise ValueError(f"{duplicate} 주문은 이미 처리되었습니다.")
        revision = int(current.get("revision", 0))
        if revision != plan.ledger_revision:
            raise ValueError("장부 버전이 바뀌었습니다. 새 주문 계획을 만드세요.")
        current_holdings = {
            ticker: int(qty)
            for ticker, qty in (current.get("holdings") or {}).items()
            if int(qty)
        }
        if holdings_digest(int(current["cash"]), current_holdings) != plan.holdings_hash:
            raise ValueError("보유 내역이 바뀌었습니다. 새 주문 계획을 만드세요.")

        pending = json.loads(json.dumps(current))
        holdings = pending.setdefault("holdings", {})
        cash = int(pending["cash"])
        records = []
        for order in plan.orders:
            market_price = self.prices.get(order.ticker)
            if not market_price:
                raise ValueError(f"{order.ticker}의 수업용 가격이 없습니다.")
            if int(order.limit_price) != int(plan.prices.get(order.ticker, 0)):
                raise ValueError(f"{order.ticker} 주문 가격과 계획 가격이 다릅니다.")
            crosses = (
                order.limit_price >= market_price
                if order.side == "buy"
                else order.limit_price <= market_price
            )
            if not crosses:
                raise RuntimeError(f"{order.ticker} 지정가가 수업용 현재가에 닿지 않습니다.")
            held = int(holdings.get(order.ticker, 0))
            notional = int(order.qty) * int(market_price)
            if order.side == "buy":
                if cash < notional:
                    raise RuntimeError(f"{order.ticker} 매수 현금이 부족합니다.")
                cash -= notional
                holdings[order.ticker] = held + int(order.qty)
            elif order.side == "sell":
                if held < order.qty:
                    raise RuntimeError(f"{order.ticker} 매도 수량이 부족합니다.")
                cash += notional
                remaining = held - int(order.qty)
                if remaining:
                    holdings[order.ticker] = remaining
                else:
                    holdings.pop(order.ticker, None)
            else:
                raise ValueError("side는 buy 또는 sell이어야 합니다.")
            records.append({
                "ok": True,
                "order_no": order.order_key,
                "order_key": order.order_key,
                "ticker": order.ticker,
                "exchange": order.exchange,
                "side": order.side,
                "qty": order.qty,
                "limit_price": order.limit_price,
                "fill_price": market_price,
                "message": "지정가 주문이 체결되었습니다.",
                "simulated": True,
            })

        pending["cash"] = cash
        pending["revision"] = revision + 1
        pending.setdefault("orders", []).extend(records)
        pending["processed_order_keys"] = sorted(
            processed | {order.order_key for order in plan.orders}
        )
        self._save_atomic(pending)
        return records


# 1.3.0 초안의 import 이름을 깨지 않기 위한 별칭입니다.
USMockBroker = LocalMockBroker
