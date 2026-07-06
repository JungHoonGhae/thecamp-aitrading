"""직접 호출: 종목 하나의 현재가를 가져온다.

가장 단순한 형태. 종목 코드를 주면 현재가를 출력한다.
실행:  python quote.py 005930
       python quote.py            # 인자 없으면 삼성전자
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from common.kis import KISClient

code = sys.argv[1] if len(sys.argv) > 1 else "005930"
result = KISClient().get_price(code)
print(f"{result['code']} 현재가: {result['price']:,}원")
