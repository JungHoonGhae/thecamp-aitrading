"""hermes --monitor-script 용 — 관심 종목 상태 한 줄.
출력이 직전과 같으면 hermes 는 아무것도 하지 않는다. 달라졌을 때만 깨운다.
"""
import runpy, sys
from pathlib import Path
REPO = r"__여기에_저장소_절대경로__"
r = Path(REPO) / "routines" / "가격도달-감시.py"
sys.path.insert(0, str(r.parent)); sys.argv = [str(r)]
runpy.run_path(str(r), run_name="__main__")
