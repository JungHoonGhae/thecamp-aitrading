"""hermes cron(no-agent)용 — 아침 브리핑 루틴을 깨운다.

hermes 는 ~/.hermes/scripts/ 아래 스크립트를 실행한다. `.sh` 는 bash 로(→ Windows 불가),
`.py` 는 현재 Python 으로 실행하므로 OS 를 안 가리게 `.py` 로 둔다.

`--no-agent` 로 걸면 **hermes 는 LLM 을 쓰지 않는다**(무료·결정적).
깨우는 일만 hermes 가 하고, AI 판단은 루틴 안에서 내 코딩 앱(claude·codex)이 한다.
텔레그램 보고도 루틴이 저장소 `.env` 의 봇으로 직접 보낸다.

설치:
  1) 이 파일을 ~/.hermes/scripts/ 로 복사
  2) 아래 REPO 를 내 저장소 절대경로로 수정
     (Windows 예: r"C:\\Users\\나\\...\\thecamp-aitrading")
"""
import os
import runpy
import sys
from pathlib import Path

REPO = r"__여기에_저장소_절대경로__"  # 예: /Users/나/workspace/projects/thecamp-aitrading

routine = Path(REPO) / "routines" / "아침브리핑.py"
os.environ["THECAMP_STDOUT_ONLY"] = "1"
sys.path.insert(0, str(routine.parent))   # 루틴이 _routine.py 를 찾게 한다
sys.argv = [str(routine)]
runpy.run_path(str(routine), run_name="__main__")
