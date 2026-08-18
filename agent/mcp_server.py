"""랩 MCP 서버 — AI가 KIS 데이터를 "필요할 때 찾아서" 쓰게 한다.

`lessons/0-시작/2-개념-정보전달과-MCP.md` 가 설명한 catalog(점진적 공개)를 그대로 구현한다.
AI에게 API 문서를 통째로 주지 않는다. 도구는 **3개**뿐이다:

    search_api   (검색)     — 뭘 할 수 있는지 찾는다
    describe_api (상세보기)  — 그 하나가 무엇을 요구하는지 본다
    call_api     (호출)     — 실제로 부른다

Docker 도, 외부 라이브러리도 필요 없다. 표준 라이브러리로 stdio JSON-RPC 만 말한다.
데이터는 2부 `agent/agent.py` 와 **같은** KISClient 를 쓴다 — 1부에서 붙인 것이
2부에서 그대로 돌아가는 이유다.

등록:
    claude mcp add kis-lab -- python3 <저장소경로>/agent/mcp_server.py
    codex  mcp add kis-lab -- python3 <저장소경로>/agent/mcp_server.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from common.kis import KISClient  # noqa: E402
from common.stocks import NAME_TO_CODE  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"

# 이게 catalog 다. 330개가 아니라 2개지만 구조는 같다 —
# 모델은 목록을 먼저 보고, 필요한 하나의 스펙만 그때 꺼내 쓴다.
CATALOG = {
    "inquire_price": {
        "summary": "종목 현재가 조회",
        "keywords": ["현재가", "시세", "가격", "price", "quote"],
        "params": {"code": "종목코드 6자리 (예: 005930). 이름만 알면 search_api 로 먼저 찾으세요."},
    },
    "inquire_balance": {
        "summary": "내 계좌 잔고·보유 종목 조회",
        "keywords": ["잔고", "계좌", "보유", "평가금액", "balance"],
        "params": {},
    },
    "news_title": {
        "summary": "종목 관련 뉴스·공시 제목 (숫자로 안 보이는 것)",
        "keywords": ["뉴스", "공시", "소식", "이슈", "news"],
        "params": {"code": "종목코드 6자리. 이름만 알면 search_api 로 먼저 찾으세요."},
    },
    "market_cap": {
        "summary": "시가총액 상위 종목 (기본 스펙의 '시총 상위'가 어디서 오는지)",
        "keywords": ["시가총액", "시총", "상위", "순위", "랭킹"],
        "params": {"n": "몇 위까지 볼지 (기본 10)"},
    },
}


def _search(query: str) -> dict:
    q = (query or "").strip().lower()
    hits = [
        {"api": name, "summary": spec["summary"]}
        for name, spec in CATALOG.items()
        if not q or q in name.lower() or any(q in k.lower() for k in spec["keywords"])
        or q in spec["summary"].lower()
    ]
    # 종목 이름이 그대로 들어오면 코드를 같이 돌려준다 (학생이 "삼성전자" 라고 물을 때)
    codes = {n: c for n, c in NAME_TO_CODE.items() if query and query.strip() in n}
    return {"apis": hits, "종목코드": codes}


def _describe(api: str) -> dict:
    spec = CATALOG.get(api)
    if not spec:
        return {"error": f"'{api}' 는 없는 api 입니다. search_api 로 먼저 찾으세요."}
    return {"api": api, "summary": spec["summary"], "params": spec["params"]}


def _call(api: str, params: dict) -> dict:
    kis = KISClient()
    if api == "inquire_price":
        code = str((params or {}).get("code", "")).strip()
        if not code:
            return {"error": "code(종목코드 6자리)가 필요합니다. describe_api 로 확인하세요."}
        r = kis.get_price(code)
        return {"mode": kis.mode, "code": r["code"], "현재가": r["price"]}
    if api == "inquire_balance":
        b = kis.get_balance()
        return {"mode": kis.mode, "예수금": b["cash"], "보유": b["holdings"]}
    if api == "news_title":
        code = str((params or {}).get("code", "")).strip()
        if not code:
            return {"error": "code(종목코드 6자리)가 필요합니다. describe_api 로 확인하세요."}
        return {"mode": kis.mode, "code": code, "뉴스": kis.get_news(code),
                "주의": "제목만 가져옵니다. 이걸로 사고팔지는 정하지 않습니다 — 판단은 3~4회차."}
    if api == "market_cap":
        try:
            n = int((params or {}).get("n", 10))
        except (TypeError, ValueError):
            n = 10
        return {"mode": kis.mode, "상위": kis.get_market_cap_top(max(1, min(n, 30)))}
    return {"error": f"'{api}' 는 없는 api 입니다."}


TOOLS = [
    {
        "name": "search_api",
        "description": "무엇을 할 수 있는지 찾는다(검색). 종목 이름을 주면 종목코드도 같이 돌려준다.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "찾을 말 (예: 현재가, 잔고, 삼성전자)"}},
            "required": ["query"],
        },
    },
    {
        "name": "describe_api",
        "description": "고른 api 하나가 무엇을 요구하는지 본다(상세보기). 호출 전에 부른다.",
        "inputSchema": {
            "type": "object",
            "properties": {"api": {"type": "string", "description": "search_api 가 준 api 이름"}},
            "required": ["api"],
        },
    },
    {
        "name": "call_api",
        "description": "실제로 부른다(호출). 수업 기본은 mock 연습 계좌라 휴장에도 값이 나온다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "api": {"type": "string"},
                "params": {"type": "object", "description": "describe_api 가 알려준 값들"},
            },
            "required": ["api"],
        },
    },
]

HANDLERS = {
    "search_api": lambda a: _search(a.get("query", "")),
    "describe_api": lambda a: _describe(a.get("api", "")),
    "call_api": lambda a: _call(a.get("api", ""), a.get("params") or {}),
}


def handle(req: dict) -> dict | None:
    """JSON-RPC 요청 하나를 처리한다. 알림(id 없음)이면 None 을 돌려 응답하지 않는다."""
    method, rid = req.get("method"), req.get("id")

    if method == "initialize":
        # 클라이언트가 요구한 버전을 그대로 받아준다 — 버전 협상에서 튕기지 않게.
        asked = (req.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION
        result = {
            "protocolVersion": asked,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "kis-lab", "version": "1.0.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = req.get("params") or {}
        fn = HANDLERS.get(params.get("name"))
        if not fn:
            return _err(rid, -32602, f"모르는 도구: {params.get('name')}")
        try:
            payload = fn(params.get("arguments") or {})
        except Exception as e:  # noqa: BLE001 — 학생 화면에 traceback 대신 문장이 가게
            payload = {"error": f"{type(e).__name__}: {e}"}
        result = {"content": [{"type": "text",
                               "text": json.dumps(payload, ensure_ascii=False, indent=2)}]}
    elif method in ("ping",):
        result = {}
    elif rid is None:
        return None            # notifications/initialized 등 — 응답하지 않는다
    else:
        return _err(rid, -32601, f"모르는 method: {method}")

    return None if rid is None else {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code: int, msg: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            print(json.dumps(resp, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
