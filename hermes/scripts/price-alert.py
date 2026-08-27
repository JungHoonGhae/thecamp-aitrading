"""hermes cron(no-agent)용 — 가격 도달 알림.
상태가 바뀐 순간에만 텔레그램으로 간다. 그대로면 아무 말도 하지 않는다.
"""
import runpy, sys
from pathlib import Path
REPO = r"__여기에_저장소_절대경로__"
r = Path(REPO) / "routines" / "가격도달-알림.py"
sys.path.insert(0, str(r.parent)); sys.argv = [str(r)]
runpy.run_path(str(r), run_name="__main__")
