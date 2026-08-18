"""공통 패키지 — import 되는 순간 출력 인코딩을 UTF-8 로 고정한다.

한국어 윈도우의 콘솔 기본 인코딩은 cp949 라서, 보고서의 ⚠️·⛔·✅ 를 그냥 print 하면
`UnicodeEncodeError: 'cp949' codec can't encode character '\\u26a0'` 로 **첫 실행이
통째로 죽는다.** 비개발자 수강생에겐 여기서 실습이 끝나 버리므로, 실행 파일
(agent.py · verify.py · sync_spec.py · examples/quote.py)이 전부 거쳐 가는 이 한 곳에서
막는다. mac/Linux 는 이미 UTF-8 이라 아무 영향이 없다.
"""
from __future__ import annotations

import sys

for _stream in (sys.stdout, sys.stderr):
    # 파이프로 넘길 때 등 reconfigure 가 없는 객체일 수 있어 방어적으로 처리한다.
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
