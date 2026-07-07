"""hermes cron(no-agent)용 포트폴리오 점검 스크립트 — 크로스플랫폼(mac/Linux/Windows).

hermes 는 ~/.hermes/scripts/ 아래 스크립트를 실행하는데, `.sh` 는 bash 로(→ Windows 불가)
`.py` 는 현재 Python 인터프리터로 실행한다. 그래서 OS 를 안 가리게 `.py` 로 둔다.
출력(stdout)이 그대로 디스코드로 배달된다. LLM 을 쓰지 않는다(무료·결정적).

설치:
  1) 이 파일을 ~/.hermes/scripts/ 로 복사
  2) 아래 REPO 를 내 저장소 절대경로로 수정
     (Windows 예: r"C:\\Users\\나\\...\\edu-fastcampus-ai-trading-lab")
"""
import runpy
import sys
from pathlib import Path

REPO = r"__여기에_저장소_절대경로__"  # 예: /Users/나/workspace/projects/edu-fastcampus-ai-trading-lab

agent = Path(REPO) / "2부-나만의-에이전트" / "agent.py"
sys.argv = [str(agent)]
runpy.run_path(str(agent), run_name="__main__")
