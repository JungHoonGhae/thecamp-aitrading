"""KIS(한국투자증권) 클라이언트 — mock / live 두 가지 모드 + paper / real 서버 스위치.

- mock (기본): common/fixtures/*.json 을 읽어 응답한다. KIS 키가 없어도, 장이 닫힌
  토요일에도 항상 똑같이 동작한다. 강의 실습의 기본 모드.
- live: .env 에 넣은 KIS 키로 실제 API 를 호출한다. (원하는 학생만)
  - KIS_ENV=paper (기본): 모의투자 서버. 수업은 여기까지만 쓴다.
  - KIS_ENV=real: 실전(실계좌) 서버. **수업 범위 밖 — 졸업 스위치.**
    실수로 켜지지 않도록 KIS_REAL_ACK=REAL-MONEY-OK 를 함께 요구한다(이중 확인).
    같은 인터페이스 그대로 서버 주소와 거래 TR ID만 바뀐다 — 코드 수정 없이 전환된다.

모드는 환경변수 KIS_MODE / KIS_ENV 또는 생성 인자로 정한다.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
VPS = "https://openapivts.koreainvestment.com:29443"   # 모의투자(paper) 서버
REAL = "https://openapi.koreainvestment.com:9443"      # 실전(real) 서버 — 졸업 스위치


class KISClient:
    def __init__(self, mode: str | None = None, env: str | None = None):
        self.mode = (mode or os.getenv("KIS_MODE", "mock")).lower()
        self.env = (env or os.getenv("KIS_ENV", "paper")).lower()  # paper | real
        if self.env == "real" and os.getenv("KIS_REAL_ACK") != "REAL-MONEY-OK":
            raise RuntimeError(
                "실전(real) 전환은 이중 확인이 필요합니다: 환경변수 KIS_REAL_ACK=REAL-MONEY-OK 를 "
                "직접 설정하세요. (실제 돈이 움직입니다 — lessons/9-마무리 '졸업 스위치' 참조)")
        if self.mode == "live":
            self.app_key = os.environ["KIS_APP_KEY"]
            self.app_secret = os.environ["KIS_APP_SECRET"]
            self.account = os.environ["KIS_ACCOUNT"]  # 계좌 앞 8자리 (paper=모의, real=실계좌)
            self._token = None
        self.base = REAL if self.env == "real" else VPS

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
            data = self._fixture("balance.json")
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

    def place_order(self, code: str, side: str, qty: int) -> dict:
        """모의투자 시장가 주문. side='buy'|'sell'. {'ok','code','side','qty', ...} 반환.

        mock 모드: 실제로 넣지 않고 시뮬레이션 결과를 돌려준다(휴장·키 무관).
        live 모드: KIS 서버에 실제 주문을 전송한다(장중에만 체결).
          - KIS_ENV=paper(기본): 모의투자 주문. KIS_ENV=real: 실계좌 주문(이중 확인 필수).
        """
        if qty <= 0:
            return {"ok": False, "code": code, "side": side, "qty": qty,
                    "msg": "수량 0 — 주문 생략"}
        if self.mode == "mock":
            return {"ok": True, "code": code, "side": side, "qty": qty,
                    "simulated": True, "msg": "모의 시뮬레이션(실주문 아님)"}
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
                f"(서버 응답: {detail})"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"KIS 서버에 연결할 수 없습니다 — 네트워크 상태를 확인하세요. ({e})") from e

    def _get_token(self) -> str:
        if self._token:
            return self._token
        body = json.dumps({"grant_type": "client_credentials",
                           "appkey": self.app_key, "appsecret": self.app_secret}).encode()
        req = urllib.request.Request(f"{self.base}/oauth2/tokenP", data=body,
                                     headers={"Content-Type": "application/json"})
        self._token = self._open(req)["access_token"]
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
        time.sleep(0.5)
        return self._open(req)

    def _call(self, path: str, tr_id: str, params: dict) -> dict:
        q = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{self.base}{path}?{q}",
            headers={"authorization": f"Bearer {self._get_token()}",
                     "appkey": self.app_key, "appsecret": self.app_secret,
                     "tr_id": tr_id, "custtype": "P"},
        )
        time.sleep(0.5)  # 모의투자 초당 호출 제한 회피
        return self._open(req)
