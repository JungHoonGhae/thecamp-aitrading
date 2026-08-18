"""저장소 루트 .env 를 읽는다. 이미 있는 환경변수는 덮어쓰지 않는다.

수업 스위치는 여기 한 파일이다:
  KIS_MODE=mock | live
  KIS_ENV=paper | real  (+ 실전은 KIS_REAL_ACK)
"""
from __future__ import annotations

import os
from pathlib import Path

_REPO_ENV = Path(__file__).resolve().parents[2] / ".env"


def load_repo_env() -> None:
    if not _REPO_ENV.is_file():
        return
    for raw in _REPO_ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val
