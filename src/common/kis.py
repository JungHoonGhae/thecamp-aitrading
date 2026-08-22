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


def _kis_order_err(msg_cd: str, msg1: str) -> dict:
    """주문 실패 본문. live 거절과 같은 칸이다."""
    return {"rt_cd": "7", "msg_cd": msg_cd, "msg1": msg1, "output": {}}


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
        data = self._price_payload(code)
        return {"code": code, "price": int(data["output"]["stck_prpr"])}

    def get_news(self, code: str) -> list[dict]:
        """종목 관련 뉴스·공시 제목. [{date, source, title}] 반환.

        숫자로는 안 보이는 것을 보는 자리다. mock 은 연습용 고정 제목이고,
        평일에 live 로 두면 실제 뉴스가 온다. **제목만** 가져온다 — 본문을 지어내지
        않게 하려는 것이고, 판단은 3~4회차에서 다룬다.
        """
        data = self._news_payload(code)
        rows = data.get("output") or []
        return [{"date": r.get("data_dt", ""), "source": r.get("dorg", ""),
                 "title": r.get("hts_pbnt_titl_cntt", "")} for r in rows[:10]]

    def get_market_cap_top(self, n: int = 10) -> list[dict]:
        """시가총액 상위. [{rank, code, name, 시총_억, 등락률}] 반환.

        기본 스펙이 "시총 상위 균등"이라, 그 순위가 어디서 오는지 학생이 직접 본다.
        """
        data = self._market_cap_payload()
        rows = (data.get("output") or [])[:n]
        return [{"rank": int(r["data_rank"]), "code": r["mksc_shrn_iscd"],
                 "name": r["hts_kor_isnm"], "시총_억": int(r["stck_avls"]),
                 "등락률": float(r["prdy_ctrt"])} for r in rows]

    def get_balance(self) -> dict:
        """계좌 잔고. {'cash', 'holdings':[{code,name,qty,eval_amt}]} 반환."""
        data = self._balance_payload()
        summary = (data.get("output2") or [{}])[0]
        holdings = [
            {"code": h["pdno"], "name": h["prdt_name"],
             "qty": int(h["hldg_qty"]), "eval_amt": int(h["evlu_amt"])}
            for h in data.get("output1", []) if int(h["hldg_qty"]) > 0
        ]
        return {"cash": cash_from_summary(summary), "holdings": holdings}

    def place_order(self, code: str, side: str, qty: int, name: str = "") -> dict:
        """시장가 주문. side='buy'|'sell'.

        모의·라이브 모두 KIS order-cash 본문(rt_cd, msg_cd, msg1, output.ODNO)을
        같은 칸으로 파싱한다. mock 은 그 본문을 fixtures 로 만들고 연습 계좌에 반영한다.
        MCP 도구는 바꾸지 않는다 — 바뀌는 것은 .env 의 KIS_MODE / KIS_ENV 뿐이다.
        """
        if qty <= 0:
            res = _kis_order_err("APBK0011", "주문수량을 확인하세요.")
        elif self.mode == "mock":
            res = self._fill_mock(code, side, qty, name)
        else:
            tr_id = self._tr("TTC0802U") if side == "buy" else self._tr("TTC0801U")
            body = {
                "CANO": self.account, "ACNT_PRDT_CD": "01", "PDNO": code,
                "ORD_DVSN": "01",
                "ORD_QTY": str(qty), "ORD_UNPR": "0",
            }
            res = self._post("/uapi/domestic-stock/v1/trading/order-cash", tr_id, body)
        return self._parse_order(res, code, side, qty)

    def order_request(self, code: str, side: str, qty: int) -> dict:
        """주문 직전에 나가는 요청 형태. 미리보기에서 그대로 보여 준다."""
        tr_id = self._tr("TTC0802U") if side == "buy" else self._tr("TTC0801U")
        cano = self.account if self.mode == "live" else "00000000"
        return {
            "path": "/uapi/domestic-stock/v1/trading/order-cash",
            "tr_id": tr_id,
            "body": {
                "CANO": cano, "ACNT_PRDT_CD": "01", "PDNO": code,
                "ORD_DVSN": "01", "ORD_QTY": str(qty), "ORD_UNPR": "0",
            },
        }

    # ---- 내부: mock 도 live 와 같은 JSON 칸을 만든다 ----
    def _fixture(self, name: str) -> dict:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def _price_payload(self, code: str) -> dict:
        if self.mode == "mock":
            prices = self._fixture("prices.json")
            if code in prices:
                return prices[code]
            price = 10_000 + int(code) % 190_000
            return {
                "rt_cd": "0", "msg_cd": "MCA00000",
                "msg1": "정상처리 되었습니다.",
                "output": {"stck_prpr": str(price), "stck_shrn_iscd": code},
            }
        return self._call(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
        )

    def _news_payload(self, code: str) -> dict:
        if self.mode == "mock":
            blob = self._fixture("news.json").get(code)
            if not blob:
                return {"rt_cd": "0", "msg_cd": "MCA00000",
                        "msg1": "정상처리 되었습니다.", "output": []}
            return blob
        return self._call(
            "/uapi/domestic-stock/v1/quotations/news-title", "FHKST01011800",
            {"FID_NEWS_OFER_ENTP_CODE": "", "FID_COND_MRKT_CLS_CODE": "",
             "FID_INPUT_ISCD": code, "FID_TITL_CNTT": "", "FID_INPUT_DATE_1": "",
             "FID_INPUT_HOUR_1": "", "FID_RANK_SORT_CLS_CODE": "", "FID_INPUT_SRNO": ""},
        )

    def _market_cap_payload(self) -> dict:
        if self.mode == "mock":
            return self._fixture("market_cap.json")
        return self._call(
            "/uapi/domestic-stock/v1/ranking/market-cap", "FHPST01740000",
            {"fid_cond_mrkt_div_code": "J", "fid_cond_scr_div_code": "20174",
             "fid_div_cls_code": "1", "fid_input_iscd": "0000", "fid_trgt_cls_code": "0",
             "fid_trgt_exls_cls_code": "0", "fid_input_price_1": "",
             "fid_input_price_2": "", "fid_vol_cnt": ""},
        )

    def _balance_payload(self) -> dict:
        if self.mode == "mock":
            return self._balance_envelope()
        return self._call(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            self._tr("TTC8434R"),
            {
                "CANO": self.account, "ACNT_PRDT_CD": "01", "AFHR_FLPR_YN": "N",
                "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            },
        )

    def _parse_order(self, res: dict, code: str, side: str, qty: int) -> dict:
        output = res.get("output") or {}
        return {
            "ok": res.get("rt_cd") == "0",
            "code": code, "side": side, "qty": qty,
            "simulated": self.mode == "mock",
            "msg": (res.get("msg1") or "").strip(),
            "order_no": output.get("ODNO", ""),
            "rt_cd": res.get("rt_cd", ""),
            "msg_cd": res.get("msg_cd", ""),
            "output": output,
        }

    def _ledger_from_fixture(self) -> dict:
        data = self._fixture("balance.json")
        summary = (data.get("output2") or [{}])[0]
        holdings = {}
        for h in data.get("output1", []):
            qty = int(h["hldg_qty"])
            if qty > 0:
                holdings[h["pdno"]] = {
                    "name": h["prdt_name"],
                    "qty": qty,
                    "pchs_avg_pric": float(h.get("pchs_avg_pric") or 0),
                }
        return {
            "dnca_tot_amt": int(summary.get("dnca_tot_amt") or 0),
            "prvs_rcdl_excc_amt": int(summary.get("prvs_rcdl_excc_amt")
                                      or summary.get("dnca_tot_amt") or 0),
            "thdt_buy_amt": int(summary.get("thdt_buy_amt") or 0),
            "thdt_sll_amt": int(summary.get("thdt_sll_amt") or 0),
            "next_odno": 1,
            "holdings": holdings,
        }

    def _normalize_ledger(self, raw: dict) -> dict:
        """예전 {cash, holdings} 장부도 읽는다."""
        if "prvs_rcdl_excc_amt" in raw or "dnca_tot_amt" in raw:
            holdings = {}
            for code, h in (raw.get("holdings") or {}).items():
                holdings[code] = {
                    "name": h.get("name") or code,
                    "qty": int(h.get("qty") or 0),
                    "pchs_avg_pric": float(h.get("pchs_avg_pric") or 0),
                }
            cash = int(raw.get("prvs_rcdl_excc_amt")
                       or raw.get("dnca_tot_amt") or raw.get("cash") or 0)
            return {
                "dnca_tot_amt": int(raw.get("dnca_tot_amt") or cash),
                "prvs_rcdl_excc_amt": cash,
                "thdt_buy_amt": int(raw.get("thdt_buy_amt") or 0),
                "thdt_sll_amt": int(raw.get("thdt_sll_amt") or 0),
                "next_odno": int(raw.get("next_odno") or 1),
                "holdings": holdings,
            }
        cash = int(raw.get("cash") or 0)
        holdings = {}
        for code, h in (raw.get("holdings") or {}).items():
            holdings[code] = {
                "name": h.get("name") or code,
                "qty": int(h.get("qty") or 0),
                "pchs_avg_pric": float(h.get("pchs_avg_pric") or 0),
            }
        return {
            "dnca_tot_amt": cash, "prvs_rcdl_excc_amt": cash,
            "thdt_buy_amt": 0, "thdt_sll_amt": 0, "next_odno": 1,
            "holdings": holdings,
        }

    def _load_ledger(self) -> dict:
        if LEDGER.is_file():
            return self._normalize_ledger(
                json.loads(LEDGER.read_text(encoding="utf-8")))
        return self._ledger_from_fixture()

    def _save_ledger(self, ledger: dict) -> None:
        LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")

    def _output1_row(self, code: str, name: str, qty: int,
                     avg: float, price: int) -> dict:
        pchs_amt = int(round(qty * avg))
        evlu = qty * price
        pfls = evlu - pchs_amt
        rt = round(pfls / pchs_amt * 100, 2) if pchs_amt else 0.0
        return {
            "pdno": code, "prdt_name": name, "trad_dvsn_name": "현금",
            "hldg_qty": str(qty), "ord_psbl_qty": str(qty),
            "pchs_avg_pric": f"{avg:.4f}", "pchs_amt": str(pchs_amt),
            "prpr": str(price), "evlu_amt": str(evlu),
            "evlu_pfls_amt": str(pfls), "evlu_pfls_rt": f"{rt:.2f}",
            "fltt_rt": "0.00", "bfdy_cprs_icdc": "0",
        }

    def _balance_envelope(self) -> dict:
        """inquire-balance 와 같은 칸. mock 다음 조회가 live 와 같은 본문을 본다."""
        ledger = self._load_ledger()
        rows = []
        scts = 0
        pchs_sum = 0
        pfls_sum = 0
        for code, h in ledger.get("holdings", {}).items():
            qty = int(h.get("qty") or 0)
            if qty <= 0:
                continue
            price = self.get_price(code)["price"]
            avg = float(h.get("pchs_avg_pric") or price)
            row = self._output1_row(code, h.get("name") or code, qty, avg, price)
            rows.append(row)
            scts += int(row["evlu_amt"])
            pchs_sum += int(row["pchs_amt"])
            pfls_sum += int(row["evlu_pfls_amt"])
        cash = int(ledger.get("prvs_rcdl_excc_amt") or 0)
        dnca = int(ledger.get("dnca_tot_amt") or cash)
        tot = cash + scts
        return {
            "rt_cd": "0", "msg_cd": "20310000",
            "msg1": "모의투자 조회가 완료되었습니다.                                                 ",
            "output1": rows,
            "output2": [{
                "dnca_tot_amt": str(dnca),
                "nxdy_excc_amt": str(tot),
                "prvs_rcdl_excc_amt": str(cash),
                "cma_evlu_amt": "0",
                "bfdy_buy_amt": "0",
                "thdt_buy_amt": str(int(ledger.get("thdt_buy_amt") or 0)),
                "nxdy_auto_rdpt_amt": "0",
                "bfdy_sll_amt": "0",
                "thdt_sll_amt": str(int(ledger.get("thdt_sll_amt") or 0)),
                "d2_auto_rdpt_amt": "0",
                "bfdy_tlex_amt": "0",
                "thdt_tlex_amt": "0",
                "tot_loan_amt": "0",
                "scts_evlu_amt": str(scts),
                "tot_evlu_amt": str(tot),
                "nass_amt": str(tot),
                "fncg_gld_auto_rdpt_yn": "",
                "pchs_amt_smtl_amt": str(pchs_sum),
                "evlu_amt_smtl_amt": str(scts),
                "evlu_pfls_smtl_amt": str(pfls_sum),
                "tot_stln_slng_chgs": "0",
                "bfdy_tot_asst_evlu_amt": str(tot),
                "asst_icdc_amt": "0",
                "asst_icdc_erng_rt": "0.00000000",
            }],
        }

    def _fill_mock(self, code: str, side: str, qty: int, name: str) -> dict:
        """KIS order-cash 본문을 만들고, 연습 계좌에 반영한다."""
        ledger = self._load_ledger()
        price = self.get_price(code)["price"]
        cost = qty * price
        holdings = ledger.setdefault("holdings", {})
        cur = holdings.get(code, {"name": name or code, "qty": 0, "pchs_avg_pric": 0.0})
        if name:
            cur["name"] = name
        have = int(cur.get("qty") or 0)
        avg = float(cur.get("pchs_avg_pric") or 0)
        cash = int(ledger.get("prvs_rcdl_excc_amt") or 0)
        if side == "buy":
            if cash < cost:
                return _kis_order_err("APBK0400", "주문가능금액을 초과했습니다.")
            new_qty = have + qty
            cur["pchs_avg_pric"] = ((avg * have) + (price * qty)) / new_qty
            cur["qty"] = new_qty
            ledger["prvs_rcdl_excc_amt"] = cash - cost
            ledger["thdt_buy_amt"] = int(ledger.get("thdt_buy_amt") or 0) + cost
        else:
            if have < qty:
                return _kis_order_err("APBK0401", "주문가능수량을 초과했습니다.")
            cur["qty"] = have - qty
            ledger["prvs_rcdl_excc_amt"] = cash + cost
            ledger["thdt_sll_amt"] = int(ledger.get("thdt_sll_amt") or 0) + cost
        holdings[code] = cur
        odno = f"{int(ledger.get('next_odno') or 1):010d}"
        ledger["next_odno"] = int(ledger.get("next_odno") or 1) + 1
        self._save_ledger(ledger)
        return {
            "rt_cd": "0", "msg_cd": "APBK0013",
            "msg1": "주문 전송 완료 되었습니다.",
            "output": {
                "KRX_FWDG_ORD_ORGNO": "06010",
                "ODNO": odno,
                "ORD_TMD": time.strftime("%H%M%S"),
            },
        }

    def _open(self, req: urllib.request.Request, retry_on_rate_limit: bool = False) -> dict:
        """공통 호출 래퍼 — 실패를 학생이 이해할 수 있는 메시지로 바꿔준다.

        KIS 는 제한이 두 종류다. 토큰 발급(oauth2/tokenP)은 앱키당 1분에 1회,
        일반 호출은 초당 건수 제한(EGW00201)이다. 증상이 똑같이 HTTP 500 이라
        학생이 자격증명 문제로 착각하기 쉬워서, 응답 코드로 갈라 안내한다.

        retry_on_rate_limit 은 **조회에만** 쓴다. 주문에 붙이면 중복 체결이 난다.
        """
        try:
            # 잔고 조회(inquire-balance)는 장중에 10초 가까이 걸리는 게 정상이다(실측 9.9초).
            # 예전 값이 10초여서 경계에 걸려 있었다 — 조금만 느려지면 수업 중에 터진다.
            return json.load(urllib.request.urlopen(req, timeout=30))
        except TimeoutError as e:
            # 읽기 타임아웃은 URLError 가 아니라 TimeoutError 로 온다. 안 잡으면
            # 학생 화면에 traceback 이 그대로 뜬다.
            raise RuntimeError(
                "증권사 응답이 30초 안에 오지 않았습니다 — 서버가 느린 것이지 설정 문제가 아닙니다.\n"
                "잠시 뒤 같은 명령을 다시 실행하세요."
            ) from e
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")[:200]
            if "EGW00201" in detail and retry_on_rate_limit:
                time.sleep(self._MIN_INTERVAL * 2)
                return self._open(req)      # 조회 한정, 한 번만 (재귀 깊이 1)
            if "EGW00201" in detail:
                raise RuntimeError(
                    "KIS 가 초당 호출 제한으로 거절했습니다 — 몇 초 뒤 다시 실행하세요.\n"
                    "(자격증명 문제가 아닙니다. 여러 개를 동시에 실행 중이면 하나만 남기세요.)"
                ) from e
            raise RuntimeError(
                "KIS API 호출 실패.\n"
                "- 처음 실행이라면: 토큰 발급은 1분에 1회만 가능합니다 — 1분 기다렸다가 다시 실행하세요.\n"
                "- 그게 아니라면: .env 의 KIS_APP_KEY/KIS_APP_SECRET/KIS_ACCOUNT 를 확인하세요.\n"
                "- 주말·공휴일이거나 장 시간이 아니면 증권사가 시세·주문을 받지 않습니다 — 평일 장중에 다시 해보세요.\n"
                f"(서버 응답: {detail})"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"KIS 서버에 연결할 수 없습니다 — 네트워크 상태를 확인하세요. ({e})") from e

    # KIS 접근토큰은 앱키당 **1분에 1회**만 발급된다. 프로세스가 끝날 때마다 버리면
    # `agent.py` 미리보기 → `--execute` 처럼 연달아 실행하는 순간 발급이 거부된다
    # (레슨이 가르치는 바로 그 흐름이다). 그래서 파일에 캐시해 재사용한다.
    _TOKEN_CACHE = Path(__file__).resolve().parents[2] / ".kis_token.json"

    # 모의투자는 **초당 호출 수**도 제한된다(토큰 발급 제한과 별개다).
    # 대기를 프로세스 안에서만 세면 소용이 없다 — 수업은 quote.py → agent.py →
    # agent.py --execute 처럼 매번 새 프로세스라, 직전 호출이 0.1초 전인지 모른다.
    # 그래서 마지막 호출 시각을 파일에 남겨 프로세스가 바뀌어도 간격을 지킨다.
    # 덤으로, 한동안 안 썼으면 안 기다린다 (예전엔 첫 호출에도 무조건 1초를 버렸다).
    _RATE_STAMP = Path(__file__).resolve().parents[2] / ".kis_last_call"
    _MIN_INTERVAL = 0.6   # ponytail: 모의 2건/초 기준 여유값. 계속 걸리면 이 값만 올린다.

    def _throttle(self) -> None:
        try:
            wait = self._MIN_INTERVAL - (time.time() - self._RATE_STAMP.stat().st_mtime)
            if wait > 0:
                time.sleep(wait)
        except OSError:
            pass          # 스탬프를 못 읽어도 호출 자체는 돼야 한다
        try:
            self._RATE_STAMP.touch()
        except OSError:
            pass

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
        self._throttle()
        return self._open(req)

    def _call(self, path: str, tr_id: str, params: dict) -> dict:
        q = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{self.base}{path}?{q}",
            headers={"authorization": f"Bearer {self._get_token()}",
                     "appkey": self.app_key, "appsecret": self.app_secret,
                     "tr_id": tr_id, "custtype": "P"},
        )
        self._throttle()
        return self._open(req, retry_on_rate_limit=True)


def cash_from_summary(summary: dict) -> int:
    """잔고 응답에서 '실제로 쓸 수 있는 현금'을 고른다.

    KIS 는 예수금을 여러 개 준다. dnca_tot_amt(D+0)는 오늘 산 금액이 아직 안 빠져
    있어서, 매수 직후 조회하면 "현금은 그대로인데 주식도 있음"이 되고 총자산이 부풀려진다.
    그러면 방금 산 종목이 또 목표 미달로 보여 **매일 다시 사게 된다**(2026-08-21 실측).
    prvs_rcdl_excc_amt(가수도정산금액)가 정산까지 반영된 값이라 이쪽을 쓴다.
    """
    return int(summary.get("prvs_rcdl_excc_amt")
               or summary.get("dnca_tot_amt", 0))


def _self_check() -> None:
    """회귀 검사 — live 키 없이 돈다.

    실행:  PYTHONPATH=src python3 -m common.kis
    """
    # 2026-08-21 모의투자 실제 응답 (삼성전자 외 4종목 매수 직후)
    real = {"dnca_tot_amt": "10000000", "prvs_rcdl_excc_amt": "1324790",
            "thdt_buy_amt": "8674000"}
    assert cash_from_summary(real) == 1324790, "D+0 예수금을 쓰면 총자산이 부풀려져 무한 매수가 된다"
    # 거래가 없던 계좌는 두 값이 같다
    assert cash_from_summary({"dnca_tot_amt": "10000000",
                              "prvs_rcdl_excc_amt": "10000000"}) == 10000000
    # 필드가 아예 없거나 비어 있어도 죽지 않는다 (구버전/모의 응답 편차)
    assert cash_from_summary({"dnca_tot_amt": "500"}) == 500
    assert cash_from_summary({"prvs_rcdl_excc_amt": "", "dnca_tot_amt": "500"}) == 500
    assert cash_from_summary({}) == 0

    reset_mock_ledger()
    kis = KISClient(mode="mock")
    before = kis.get_balance()
    filled = kis.place_order("005930", "buy", 1, name="삼성전자")
    assert filled["ok"] and filled["rt_cd"] == "0", filled
    assert filled["msg_cd"] == "APBK0013"
    assert filled["output"]["ODNO"] == "0000000001"
    assert filled["output"]["KRX_FWDG_ORD_ORGNO"] == "06010"
    after = kis.get_balance()
    assert after["cash"] == before["cash"] - 307_500, (before["cash"], after["cash"])
    samsung = next(h for h in after["holdings"] if h["code"] == "005930")
    start = next(h for h in before["holdings"] if h["code"] == "005930")
    assert samsung["qty"] == start["qty"] + 1
    denied = kis.place_order("005930", "buy", 99_999, name="삼성전자")
    assert not denied["ok"] and denied["rt_cd"] == "7"
    assert kis.get_balance()["cash"] == after["cash"]
    news = kis.get_news("005930")
    assert news and news[0]["title"]
    cap = kis.get_market_cap_top(3)
    assert cap[0]["code"] == "005930" and cap[0]["rank"] == 1
    req = kis.order_request("005930", "buy", 1)
    assert req["tr_id"].endswith("0802U") and req["body"]["ORD_DVSN"] == "01"
    reset_mock_ledger()
    print("kis 자가 검사 통과")


if __name__ == "__main__":
    _self_check()
