"""KIS(한국투자증권) 클라이언트 — mock / live 두 가지 모드 + paper / real 서버 스위치.

- mock (기본, 수업 당일): fixtures 로 시세를 읽고, --execute 하면 연습 계좌 잔고가
  실제로 바뀐다. 키가 없어도, 토요 휴장에도 같은 화면이 나온다.
  처음 상태로: reset_mock_ledger() 또는 `python agent/agent.py --reset-mock`.
- live: .env 의 KIS 키로 증권사 API 를 호출한다. (평일·키 있는 학생)
  - KIS_ENV=paper (기본): 모의투자 서버. 수업 후 전환은 KIS_MODE=live 한 줄.
  - KIS_ENV=real: 실전 서버. **수업 범위 밖 — 졸업 스위치.**
    KIS_REAL_ACK=REAL-MONEY-OK 이중 확인. 코드 수정 없이 서버·TR ID 만 바뀐다.

모드는 .env 의 KIS_MODE / KIS_ENV 또는 생성 인자로 정한다.
"""
from __future__ import annotations

import json
import os
import time
import hashlib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .env import load_repo_env

FIXTURES = Path(__file__).parent / "fixtures"
LEDGER = FIXTURES / ".ledger.json"
VPS = "https://openapivts.koreainvestment.com:29443"   # 모의투자(paper) 서버
REAL = "https://openapi.koreainvestment.com:9443"      # 실전(real) 서버 — 졸업 스위치


def reset_mock_ledger() -> None:
    """수업용 연습 계좌를 fixtures 처음 상태로 되돌린다."""
    LEDGER.unlink(missing_ok=True)


class KISClient:
    def __init__(self, mode: str | None = None, env: str | None = None):
        load_repo_env()
        self.mode = (mode or os.getenv("KIS_MODE", "mock")).lower()
        self.env = (env or os.getenv("KIS_ENV", "paper")).lower()  # paper | real
        if self.env == "real" and os.getenv("KIS_REAL_ACK") != "REAL-MONEY-OK":
            raise RuntimeError(
                "실전(real) 전환은 이중 확인이 필요합니다: 환경변수 KIS_REAL_ACK=REAL-MONEY-OK 를 "
                "직접 설정하세요. (실제 돈이 움직입니다 — lessons/9-마무리 '졸업 스위치' 참조)")
        if self.mode == "live":
            # 수업이 끝나고 평일에 혼자 live 로 바꾸는 순간이 이 코드가 가장 중요한 때다.
            # 그때 옆에 강사가 없으므로, KeyError traceback 대신 할 일을 알려준다.
            self.app_key = self._need("KIS_APP_KEY")
            self.app_secret = self._need("KIS_APP_SECRET")
            self.account = self._need("KIS_ACCOUNT")  # 계좌 앞 8자리 (paper=모의, real=실계좌)
            self._token = None
        self.base = REAL if self.env == "real" else VPS

    @staticmethod
    def _need(name: str) -> str:
        """live 모드에 필요한 값을 읽는다. 없거나 예시 그대로면 무엇을 할지 알려준다."""
        val = (os.getenv(name) or "").strip()
        if not val or val.startswith("여기에") or val == "모의계좌_앞8자리":
            raise RuntimeError(
                f"live 모드인데 {name} 가 비어 있습니다.\n"
                "- 수업 중(토요일)이라면: .env 의 KIS_MODE 를 mock 으로 되돌리세요. 연습 계좌가 정상 경로입니다.\n"
                "- 평일에 증권사 모의투자로 붙이려면: .env 에 KIS_APP_KEY / KIS_APP_SECRET / KIS_ACCOUNT 를\n"
                "  실제 값으로 채우세요. 발급 방법은 lessons/참고/kis-신청-가이드.md 에 있습니다.")
        return val

    def _tr(self, suffix: str) -> str:
        """거래계 TR ID — 모의(V…)/실전(T…) 접두만 다르다. 예: _tr("TTC8434R")"""
        return ("T" if self.env == "real" else "V") + suffix

    # ---- 공개 메서드 (mock/live 공통 인터페이스) ----
    def get_price(self, code: str) -> dict:
        """종목 현재가. {'code','price'} 반환. (종목명은 응답에 없음)"""
        if self.mode == "mock":
            prices = self._fixture("prices.json")
            if code not in prices:
                # mock 시세에 없는 종목(ETF·기타)은 코드 기반 고정 가격으로 대체 —
                # 값은 학습용 가짜지만 결정적이라, 어떤 스펙으로 바꿔도 실습 흐름이 안 끊긴다.
                return {"code": code, "price": 10_000 + int(code) % 190_000}
            data = prices[code]
        else:
            data = self._call(
                "/uapi/domestic-stock/v1/quotations/inquire-price",
                "FHKST01010100",
                {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
            )
        return {"code": code, "price": int(data["output"]["stck_prpr"])}

    def get_balance(self) -> dict:
        """계좌 잔고. {'cash', 'holdings':[{code,name,qty,eval_amt}]} 반환."""
        if self.mode == "mock":
            return self._balance_from_ledger()
        else:
            data = self._call(
                "/uapi/domestic-stock/v1/trading/inquire-balance",
                self._tr("TTC8434R"),
                {
                    "CANO": self.account, "ACNT_PRDT_CD": "01", "AFHR_FLPR_YN": "N",
                    "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01",
                    "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
                    "PRCS_DVSN": "01", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
                },
            )
        summary = (data.get("output2") or [{}])[0]
        holdings = [
            {"code": h["pdno"], "name": h["prdt_name"],
             "qty": int(h["hldg_qty"]), "eval_amt": int(h["evlu_amt"])}
            for h in data.get("output1", []) if int(h["hldg_qty"]) > 0
        ]
        return {"cash": int(summary.get("dnca_tot_amt", 0)), "holdings": holdings}

    def place_order(self, code: str, side: str, qty: int, name: str = "") -> dict:
        """시장가 주문. side='buy'|'sell'. {'ok','code','side','qty', ...} 반환.

        mock: 연습 계좌 잔고를 파일에 반영한다(주말·키 없이 다음 조회에 보임).
        live: KIS 서버에 주문을 전송한다(장중에만 체결).
          - KIS_ENV=paper(기본): 모의투자. KIS_ENV=real: 실전(이중 확인 필수).
        """
        if qty <= 0:
            return {"ok": False, "code": code, "side": side, "qty": qty,
                    "msg": "수량 0 — 주문 생략"}
        if self.mode == "mock":
            return self._fill_mock(code, side, qty, name)
        tr_id = self._tr("TTC0802U") if side == "buy" else self._tr("TTC0801U")  # 매수/매도
        body = {
            "CANO": self.account, "ACNT_PRDT_CD": "01", "PDNO": code,
            "ORD_DVSN": "01",  # 시장가
            "ORD_QTY": str(qty), "ORD_UNPR": "0",
        }
        res = self._post("/uapi/domestic-stock/v1/trading/order-cash", tr_id, body)
        ok = res.get("rt_cd") == "0"
        return {"ok": ok, "code": code, "side": side, "qty": qty,
                "simulated": False, "msg": res.get("msg1", ""),
                "order_no": (res.get("output") or {}).get("ODNO", "")}

    # ---- 내부 ----
    def _fixture(self, name: str) -> dict:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def _ledger_from_fixture(self) -> dict:
        data = self._fixture("balance.json")
        holdings = {}
        for h in data.get("output1", []):
            qty = int(h["hldg_qty"])
            if qty > 0:
                holdings[h["pdno"]] = {"name": h["prdt_name"], "qty": qty}
        cash = int((data.get("output2") or [{}])[0].get("dnca_tot_amt", 0))
        return {"cash": cash, "holdings": holdings}

    def _load_ledger(self) -> dict:
        if LEDGER.is_file():
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        return self._ledger_from_fixture()

    def _save_ledger(self, ledger: dict) -> None:
        LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")

    def _balance_from_ledger(self) -> dict:
        ledger = self._load_ledger()
        holdings = []
        for code, h in ledger.get("holdings", {}).items():
            qty = int(h.get("qty", 0))
            if qty <= 0:
                continue
            price = self.get_price(code)["price"]
            holdings.append({
                "code": code, "name": h.get("name") or code,
                "qty": qty, "eval_amt": qty * price,
            })
        return {"cash": int(ledger.get("cash", 0)), "holdings": holdings}

    def _fill_mock(self, code: str, side: str, qty: int, name: str) -> dict:
        ledger = self._load_ledger()
        price = self.get_price(code)["price"]
        cost = qty * price
        holdings = ledger.setdefault("holdings", {})
        cur = holdings.get(code, {"name": name or code, "qty": 0})
        if name:
            cur["name"] = name
        if side == "buy":
            if int(ledger.get("cash", 0)) < cost:
                return {"ok": False, "code": code, "side": side, "qty": qty,
                        "simulated": True,
                        "msg": f"예수금 부족 (필요 {cost:,}원)"}
            cur["qty"] = int(cur.get("qty", 0)) + qty
            ledger["cash"] = int(ledger.get("cash", 0)) - cost
        else:
            have = int(cur.get("qty", 0))
            if have < qty:
                return {"ok": False, "code": code, "side": side, "qty": qty,
                        "simulated": True,
                        "msg": f"보유 수량 부족 ({have}주)"}
            cur["qty"] = have - qty
            ledger["cash"] = int(ledger.get("cash", 0)) + cost
        holdings[code] = cur
        self._save_ledger(ledger)
        return {"ok": True, "code": code, "side": side, "qty": qty,
                "simulated": True, "msg": "연습 계좌 체결 (수업용 · 주말에도 동작)"}

    def _open(self, req: urllib.request.Request) -> dict:
        """공통 호출 래퍼 — 실패를 학생이 이해할 수 있는 메시지로 바꿔준다.

        특히 토큰 발급(oauth2/tokenP)은 앱키당 1분에 1회 제한이라, 에러 직후
        바로 재실행하면 같은 이유로 또 실패한다(자격증명 문제로 착각하기 쉬움).
        """
        try:
            return json.load(urllib.request.urlopen(req, timeout=10))
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")[:200]
            raise RuntimeError(
                "KIS API 호출 실패.\n"
                "- 방금 실행했다면: 토큰 발급은 1분에 1회만 가능합니다 — 1분 기다렸다가 다시 실행하세요.\n"
                "- 방금이 아니라면: .env 의 KIS_APP_KEY/KIS_APP_SECRET/KIS_ACCOUNT 를 확인하세요.\n"
                "- 주말·공휴일이거나 장 시간이 아니면 증권사가 시세·주문을 받지 않습니다 — 평일 장중에 다시 해보세요.\n"
                f"(서버 응답: {detail})"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"KIS 서버에 연결할 수 없습니다 — 네트워크 상태를 확인하세요. ({e})") from e

    # KIS 접근토큰은 앱키당 **1분에 1회**만 발급된다. 프로세스가 끝날 때마다 버리면
    # `agent.py` 미리보기 → `--execute` 처럼 연달아 실행하는 순간 발급이 거부된다
    # (레슨이 가르치는 바로 그 흐름이다). 그래서 파일에 캐시해 재사용한다.
    _TOKEN_CACHE = Path(__file__).resolve().parents[2] / ".kis_token.json"

    def _cache_key(self) -> str:
        """키·환경이 바뀌면 다른 토큰이어야 한다. 앱키 원문은 저장하지 않는다."""
        raw = f"{self.app_key}:{self.env}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def _read_cached_token(self) -> str | None:
        try:
            c = json.loads(self._TOKEN_CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        # 만료 1분 전부터는 새로 받는다 (호출 도중 만료 방지)
        if c.get("key") == self._cache_key() and c.get("expires_at", 0) - 60 > time.time():
            return c.get("token")
        return None

    def _write_cached_token(self, token: str, ttl: int) -> None:
        try:
            self._TOKEN_CACHE.write_text(json.dumps({
                "key": self._cache_key(), "token": token,
                "expires_at": time.time() + ttl,
            }), encoding="utf-8")
            self._TOKEN_CACHE.chmod(0o600)   # 토큰은 자격증명이다
        except OSError:
            pass   # 캐시를 못 써도 동작은 해야 한다

    def _get_token(self) -> str:
        if self._token:
            return self._token
        cached = self._read_cached_token()
        if cached:
            self._token = cached
            return cached
        body = json.dumps({"grant_type": "client_credentials",
                           "appkey": self.app_key, "appsecret": self.app_secret}).encode()
        req = urllib.request.Request(f"{self.base}/oauth2/tokenP", data=body,
                                     headers={"Content-Type": "application/json"})
        res = self._open(req)
        self._token = res["access_token"]
        # KIS 는 보통 24시간(86400초)을 준다. 값이 없거나 이상하면 보수적으로 1시간.
        try:
            ttl = int(res.get("expires_in") or 0)
        except (TypeError, ValueError):
            ttl = 0
        self._write_cached_token(self._token, ttl if 60 < ttl <= 86400 else 3600)
        return self._token

    def _post(self, path: str, tr_id: str, body: dict) -> dict:
        """거래계 POST 호출 (주문 등). _call 과 같은 인증 헤더 + JSON 본문."""
        req = urllib.request.Request(
            f"{self.base}{path}", data=json.dumps(body).encode(),
            headers={"authorization": f"Bearer {self._get_token()}",
                     "appkey": self.app_key, "appsecret": self.app_secret,
                     "tr_id": tr_id, "custtype": "P",
                     "Content-Type": "application/json"},
        )
        time.sleep(1.0)
        return self._open(req)

    def _call(self, path: str, tr_id: str, params: dict) -> dict:
        q = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{self.base}{path}?{q}",
            headers={"authorization": f"Bearer {self._get_token()}",
                     "appkey": self.app_key, "appsecret": self.app_secret,
                     "tr_id": tr_id, "custtype": "P"},
        )
        time.sleep(1.0)  # 모의투자 초당 호출 제한 회피
        return self._open(req)
