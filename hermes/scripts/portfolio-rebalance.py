"""hermes cron(no-agent)용 리밸런싱 실행 스크립트 — 크로스플랫폼(mac/Linux/Windows).

portfolio-check.py(점검·미리보기)의 실행판. agent.py 를 --execute 로 돌려
가드레일을 통과한 주문만 **모의투자**로 실제 전송하고 결과를 보고한다.
- 가드레일 위반이 있으면 agent.py 가 스스로 주문을 차단한다 (스크립트가 아니라 에이전트가 지킴).
- 실전(실계좌)은 졸업 스위치(KIS_ENV=real + 이중 확인)를 직접 켠 경우에만 — 기본은 모의다.
출력은 화면에 나오고, `.env` 에 텔레그램 봇이 있으면 그쪽으로도 보낸다. LLM 을 쓰지 않는다(무료·결정적).

설치:
  1) 이 파일을 ~/.hermes/scripts/ 로 복사
  2) 아래 REPO 를 내 저장소 절대경로로 수정
     (Windows 예: r"C:\\Users\\나\\...\\lecture-thecamp-aitrading")
"""
import runpy
import sys
from pathlib import Path

REPO = r"__여기에_저장소_절대경로__"  # 예: /Users/나/workspace/projects/lecture-thecamp-aitrading

agent = Path(REPO) / "agent" / "agent.py"
sys.argv = [str(agent), "--execute"]
runpy.run_path(str(agent), run_name="__main__")
