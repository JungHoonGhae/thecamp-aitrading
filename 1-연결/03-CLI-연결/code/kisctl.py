"""가벼운 CLI 래퍼: 필요한 기능만 명령으로 감싼다.

여러 종목 현재가와 잔고를 명령 하나로 조회한다. AI 에이전트가 이런 CLI 를
'명령'으로 불러 쓰면, MCP 처럼 상시 떠 있지 않아도 필요할 때만 가볍게 쓴다.

실행:  python kisctl.py price 005930 000660
       python kisctl.py balance
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from common.kis import KISClient


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("사용법: python kisctl.py price <코드...> | balance")
        return
    kis = KISClient()
    cmd = args[0]
    if cmd == "price":
        for code in args[1:] or ["005930"]:
            print(f"{code}: {kis.get_price(code)['price']:,}원")
    elif cmd == "balance":
        bal = kis.get_balance()
        print(f"현금: {bal['cash']:,}원 / 보유 {len(bal['holdings'])}종목")
        for h in bal["holdings"]:
            print(f"  - {h['name']}({h['code']}): {h['qty']}주 · {h['eval_amt']:,}원")
    else:
        print(f"모르는 명령: {cmd}")


if __name__ == "__main__":
    main()
