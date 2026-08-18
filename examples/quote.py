"""직접 호출: 종목 하나의 현재가를 가져온다.

가장 단순한 형태. 종목 코드를 주면 현재가를 출력한다.
실행:  python examples/quote.py 005930
       python examples/quote.py            # 인자 없으면 삼성전자
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common.kis import KISClient

code = sys.argv[1] if len(sys.argv) > 1 else "005930"
try:
    result = KISClient().get_price(code)
except RuntimeError as e:   # 우리가 학생에게 하려던 말 — traceback 에 묻지 않는다
    print(f"\n{e}\n", file=sys.stderr)
    sys.exit(1)
print(f"{result['code']} 현재가: {result['price']:,}원")
