"""hermes gateway(no-agent)용 고정 참조전략 점검 스크립트.

hermes 는 ~/.hermes/scripts/ 아래 스크립트를 실행하는데, `.sh` 는 bash 로(→ Windows 불가)
`.py` 는 현재 Python 인터프리터로 실행한다. 그래서 OS 를 안 가리게 `.py` 로 둔다.
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

routine = Path(REPO) / "routines" / "참조전략-실험.py"
sys.path.insert(0, str(routine.parent))
sys.argv = [str(routine)]
runpy.run_path(str(routine), run_name="__main__")
