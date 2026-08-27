"""코인 — 업비트 공개 시세.

주식만 보는 분도, 코인만 보는 분도 있다. 같은 규칙(내 스펙)을 코인에도 대 볼 수 있게
읽기 전용으로 붙여 둔다.

market.py(야후)와 다른 점이 하나 있고, 그게 이 수업의 요점이다.
  · market.py  → **비공식**. 문서 없는 엔드포인트. 예고 없이 막힐 수 있다.
  · crypto.py  → **공식**. 업비트가 문서로 공개한 시세 API 다. 키가 필요 없다.
                 https://docs.upbit.com  (Quotation API — 인증 불필요)
같은 「밖에서 가져온다」라도 무게가 다르다. 붙이기 전에 어느 쪽인지 보는 습관을 들인다.

주문은 다루지 않는다. 이 파일은 **읽기 전용**이다.
업비트 주문 API 는 키와 실명확인이 필요하고, 이 수업 범위 밖이다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.upbit.com/v1"
UA = {"User-Agent": "ai-trading-lab"}   # 헤더에 한글을 넣지 마라 (latin-1 만 된다)

# 이름만 알아도 되게. 나머지는 markets() 로 찾는다.
COINS = {"비트코인": "KRW-BTC", "이더리움": "KRW-ETH", "리플": "KRW-XRP",
         "솔라나": "KRW-SOL", "도지코인": "KRW-DOGE"}


class CryptoError(RuntimeError):
    """학생에게 그대로 보여줄 말."""


def _get(path: str, **params) -> list | dict:
    url = f"{BASE}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise CryptoError(f"업비트에서 못 가져왔습니다 (HTTP {e.code}). "
                          "종목 이름이 맞는지 보세요. 예: KRW-BTC") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise CryptoError("업비트에 못 닿았습니다. 인터넷을 확인해 주세요.") from e


def to_market(name: str) -> str:
    """「비트코인」 → KRW-BTC. 이미 KRW-XXX 면 그대로."""
    if name.upper().startswith("KRW-"):
        return name.upper()
    if name in COINS:
        return COINS[name]
    for row in markets():
        if row["korean_name"] == name or row["market"].endswith("-" + name.upper()):
            return row["market"]
    raise CryptoError(f"「{name}」 을(를) 업비트 원화 마켓에서 못 찾았습니다.")


def markets() -> list[dict]:
    """원화로 살 수 있는 코인 목록."""
    rows = _get("market/all")
    return [r for r in rows if r["market"].startswith("KRW-")]


def ticker(names: list[str]) -> list[dict]:
    """지금 시세. [{이름, 마켓, 가격, 전일대비%}]"""
    codes = [to_market(n) for n in names]
    rows = _get("ticker", markets=",".join(codes))
    korean = {r["market"]: r["korean_name"] for r in markets()}
    return [{"name": korean.get(r["market"], r["market"]),
             "market": r["market"],
             "price": float(r["trade_price"]),
             "change_pct": float(r["signed_change_rate"]) * 100}
            for r in rows]


def history(name: str, days: int = 90) -> list[float]:
    """일봉 종가를 옛날 → 최근 순으로. (업비트는 최신부터 주므로 뒤집는다)"""
    rows = _get("candles/days", market=to_market(name), count=min(days, 200))
    return [float(r["trade_price"]) for r in reversed(rows)]


def demo() -> None:
    """진짜로 값이 오는지 본다.  python src/common/crypto.py"""
    rows = ticker(["비트코인", "이더리움"])
    assert len(rows) == 2, f"두 개를 물었는데 {len(rows)}개가 왔습니다"
    assert all(r["price"] > 0 for r in rows), "가격이 0 이하입니다"
    closes = history("비트코인", 30)
    assert len(closes) >= 20, f"일봉이 너무 적습니다: {len(closes)}"
    assert closes[-1] > 0, "최근 종가가 비어 있습니다"
    assert to_market("KRW-ETH") == "KRW-ETH", "마켓 코드 변환이 틀렸습니다"
    names = ", ".join(f"{r['name']} {r['price']:,.0f}원({r['change_pct']:+.2f}%)"
                      for r in rows)
    print(f"OK — {names} · 일봉 {len(closes)}개")


if __name__ == "__main__":
    demo()
