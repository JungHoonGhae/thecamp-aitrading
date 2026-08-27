"""시장 맥락 — KIS 밖에서 가져오는 과거 시세·지수·환율.

왜 붙였나:
  KIS 모의투자는 **지금 값 한 점**을 준다. 그래서 "지금 비싼가 싼가",
  "요즘 흔들리나", "코스피보다 잘했나" 를 물어볼 수가 없다.
  과거 시세가 있어야 그 질문이 성립한다. 그래서 밖에서 가져온다.
  1주차에 배운 「AI가 못 보는 데이터는 찾아 붙인다」 가 여기 그대로 쓰인다.

  설치 0개. 키 0개. 표준 라이브러리(urllib)만 쓴다.

⚠️ 공식 API 가 아니다.
  Yahoo Finance 의 차트 엔드포인트는 **문서화된 공개 API 가 아니다.**
  공부와 실습에는 쓸 만하지만, 돈이 걸린 판단이나 남에게 파는 서비스의
  근거로 쓰면 안 된다. 예고 없이 막히거나 값이 바뀔 수 있다.
  1주차에서 「공식 소스와 비공식 소스는 무게가 다르다」 고 한 것이 이 자리다.
  주문은 언제나 공식(KIS)으로만 나간다. 이 파일은 **읽기 전용**이다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
# HTTP 헤더는 latin-1 로만 보낼 수 있다. 한글을 넣으면 UnicodeEncodeError 로 죽는다.
# (troubleshooting 스킬이 말하는 그 함정이다 — 설정에 한글을 남기지 마라.)
UA = {"User-Agent": "Mozilla/5.0 (ai-trading-lab)"}

# 자주 쓰는 것에 이름을 붙여 둔다. 학생이 기호를 외울 필요가 없게.
TICKERS = {
    "코스피": "^KS11",
    "코스닥": "^KQ11",
    "원달러": "USDKRW=X",
    "공포지수": "^VIX",       # 미국 변동성 지수. 높을수록 시장이 겁먹었다는 뜻.
    "S&P500": "^GSPC",
}


class MarketError(RuntimeError):
    """학생에게 그대로 보여줄 말. traceback 에 묻지 않는다."""


def _fetch(symbol: str, period: str, interval: str) -> dict:
    url = CHART.format(sym=urllib.parse.quote(symbol)) + "?" + urllib.parse.urlencode(
        {"range": period, "interval": interval})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise MarketError(f"{symbol} 을(를) 못 가져왔습니다 (HTTP {e.code}). "
                          "종목 기호가 맞는지 보세요.") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise MarketError("시장 데이터 서버에 못 닿았습니다. 인터넷을 확인해 주세요.") from e
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        err = ((data.get("chart") or {}).get("error") or {}).get("description", "")
        raise MarketError(f"{symbol} 에 대한 값이 없습니다. {err}".strip())
    return result[0]


def to_symbol(code: str) -> str:
    """국내 6자리 종목코드를 시장 기호로. 코스피(.KS)를 먼저, 없으면 코스닥(.KQ)."""
    if not code.isdigit():
        return code                       # 이미 ^KS11 · USDKRW=X 같은 기호
    for suffix in (".KS", ".KQ"):
        try:
            _fetch(code + suffix, "5d", "1d")
            return code + suffix
        except MarketError:
            continue
    raise MarketError(f"{code} 를 시장에서 못 찾았습니다.")


def history(symbol: str, period: str = "6mo", interval: str = "1d") -> list[float]:
    """종가만 시간순으로. 장중·휴장으로 비는 칸은 버린다."""
    res = _fetch(symbol, period, interval)
    closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    return [float(c) for c in closes if c is not None]


def last(symbol: str) -> float:
    """지금 값 하나."""
    meta = _fetch(symbol, "5d", "1d").get("meta", {})
    price = meta.get("regularMarketPrice")
    if price is None:
        raise MarketError(f"{symbol} 의 현재가가 비어 있습니다.")
    return float(price)


# ── 숫자 몇 개. 어려운 통계는 쓰지 않는다 ──────────────────────

def change_pct(closes: list[float]) -> float:
    """기간 수익률(%). 처음과 끝만 본다."""
    if len(closes) < 2 or closes[0] == 0:
        return 0.0
    return (closes[-1] / closes[0] - 1) * 100


def moving_average(closes: list[float], days: int) -> float:
    """최근 days 일 평균. 데이터가 모자라면 있는 만큼으로."""
    window = closes[-days:] or closes
    return sum(window) / len(window) if window else 0.0


def volatility_pct(closes: list[float]) -> float:
    """하루 등락폭이 평균 몇 %였나. 클수록 많이 흔들렸다는 뜻."""
    if len(closes) < 3:
        return 0.0
    moves = [abs(b / a - 1) * 100 for a, b in zip(closes, closes[1:]) if a]
    return sum(moves) / len(moves) if moves else 0.0


# ── 종목 정보 (이름 · 섹터 · 산업) ────────────────────────────

SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"

# 섹터 이름이 영어로 온다. 교실에서 읽히게 우리말로 바꾼다.
SECTOR_KO = {
    "Technology": "기술",
    "Financial Services": "금융",
    "Healthcare": "헬스케어",
    "Consumer Cyclical": "경기소비재",
    "Consumer Defensive": "필수소비재",
    "Industrials": "산업재",
    "Communication Services": "커뮤니케이션",
    "Energy": "에너지",
    "Basic Materials": "소재",
    "Utilities": "유틸리티",
    "Real Estate": "부동산",
}


def profile(symbol: str) -> dict:
    """종목 한 줄 소개. {name, sector, industry} — 못 찾으면 빈 값으로 돌려준다.

    섹터는 「어느 바닥의 회사인가」다. 같은 바닥만 잔뜩 담으면 분산이 아니다.
    """
    url = SEARCH + "?" + urllib.parse.urlencode(
        {"q": symbol, "quotesCount": 1, "newsCount": 0})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            rows = (json.loads(r.read().decode()).get("quotes") or [])
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        rows = []
    q = rows[0] if rows else {}
    sector = q.get("sector") or ""
    return {
        "name": q.get("longname") or q.get("shortname") or symbol,
        "sector": SECTOR_KO.get(sector, sector or "알 수 없음"),
        "industry": q.get("industry") or "",
    }


def demo() -> None:
    """진짜로 값이 오는지 본다.  python src/common/market.py"""
    kospi = history(TICKERS["코스피"], "6mo")
    assert len(kospi) > 50, f"코스피 데이터가 너무 적습니다: {len(kospi)}"
    assert all(v > 0 for v in kospi), "종가에 0 이하가 있습니다"
    assert abs(change_pct([100.0, 110.0]) - 10.0) < 1e-9, "수익률 계산이 틀렸습니다"
    assert moving_average([1.0, 2.0, 3.0], 2) == 2.5, "이동평균이 틀렸습니다"
    assert volatility_pct([100.0, 110.0, 99.0]) > 0, "변동성이 0 입니다"
    fx = last(TICKERS["원달러"])
    assert 500 < fx < 3000, f"원달러가 이상합니다: {fx}"
    print(f"OK — 코스피 {len(kospi)}일치, 6개월 {change_pct(kospi):+.1f}%, "
          f"원달러 {fx:,.1f}원")


if __name__ == "__main__":
    demo()
