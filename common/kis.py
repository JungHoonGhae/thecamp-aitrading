"""KIS(한국투자증권) 모의투자 클라이언트 — mock / live 두 가지 모드.

- mock (기본): common/fixtures/*.json 을 읽어 응답한다. KIS 키가 없어도, 장이 닫힌
  토요일에도 항상 똑같이 동작한다. 강의 실습의 기본 모드.
- live: .env 에 넣은 KIS 모의투자 키로 실제 API 를 호출한다. (원하는 학생만)

모드는 환경변수 KIS_MODE 또는 생성 인자로 정한다.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
VPS = "https://openapivts.koreainvestment.com:29443"  # 모의투자 서버


class KISClient:
    def __init__(self, mode: str | None = None):
        self.mode = (mode or os.getenv("KIS_MODE", "mock")).lower()
        if self.mode == "live":
            self.app_key = os.environ["KIS_APP_KEY"]
            self.app_secret = os.environ["KIS_APP_SECRET"]
            self.account = os.environ["KIS_ACCOUNT"]  # 모의계좌 앞 8자리
            self._token = None

    # ---- 공개 메서드 (mock/live 공통 인터페이스) ----
    def get_price(self, code: str) -> dict:
        """종목 현재가. {'code','price'} 반환. (종목명은 응답에 없음)"""
        if self.mode == "mock":
            data = self._fixture("prices.json")[code]
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
            data = self._fixture("balance.json")
        else:
            data = self._call(
                "/uapi/domestic-stock/v1/trading/inquire-balance",
                "VTTC8434R",
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

    def place_order(self, code: str, side: str, qty: int) -> dict:
        """모의투자 시장가 주문. side='buy'|'sell'. {'ok','code','side','qty', ...} 반환.

        mock 모드: 실제로 넣지 않고 시뮬레이션 결과를 돌려준다(휴장·키 무관).
        live 모드: KIS 모의투자 서버에 실제 주문을 전송한다(장중에만 체결).
        """
        if qty <= 0:
            return {"ok": False, "code": code, "side": side, "qty": qty,
                    "msg": "수량 0 — 주문 생략"}
        if self.mode == "mock":
            return {"ok": True, "code": code, "side": side, "qty": qty,
                    "simulated": True, "msg": "모의 시뮬레이션(실주문 아님)"}
        tr_id = "VTTC0802U" if side == "buy" else "VTTC0801U"  # 모의 매수/매도
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

    def _get_token(self) -> str:
        if self._token:
            return self._token
        body = json.dumps({"grant_type": "client_credentials",
                           "appkey": self.app_key, "appsecret": self.app_secret}).encode()
        req = urllib.request.Request(f"{VPS}/oauth2/tokenP", data=body,
                                     headers={"Content-Type": "application/json"})
        self._token = json.load(urllib.request.urlopen(req, timeout=10))["access_token"]
        return self._token

    def _call(self, path: str, tr_id: str, params: dict) -> dict:
        q = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{VPS}{path}?{q}",
            headers={"authorization": f"Bearer {self._get_token()}",
                     "appkey": self.app_key, "appsecret": self.app_secret,
                     "tr_id": tr_id, "custtype": "P"},
        )
        time.sleep(0.5)  # 모의투자 초당 호출 제한 회피
        return json.load(urllib.request.urlopen(req, timeout=10))
