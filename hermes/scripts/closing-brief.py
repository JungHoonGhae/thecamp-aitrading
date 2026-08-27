"""hermes cron(no-agent)용 — 마감 브리핑. 장 끝난 뒤 오늘을 정리한다."""
import runpy, sys
from pathlib import Path
REPO = r"__여기에_저장소_절대경로__"
r = Path(REPO) / "routines" / "마감브리핑.py"
sys.path.insert(0, str(r.parent)); sys.argv = [str(r)]
runpy.run_path(str(r), run_name="__main__")
