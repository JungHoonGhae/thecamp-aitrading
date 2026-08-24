"""저장소 루트 .env 를 읽는다.

수업 스위치는 여기 한 파일이다:
  KIS_MODE=mock | live
  KIS_ENV=paper | real  (+ 실전은 KIS_REAL_ACK)

이미 셸/앱이 넣어 둔 값은 덮지 않는다.
이 파일이 넣었던 값만, 파일이 바뀌면 다시 읽는다.
(MCP 는 오래 켜 두므로, 숙제에서 live 로 바꾸고 수업 전에 mock 으로 되돌릴 때 필요하다.)
"""
from __future__ import annotations

import os
from pathlib import Path

_REPO_ENV = Path(__file__).resolve().parents[2] / ".env"
_from_file: set[str] = set()


def load_repo_env() -> None:
    if not _REPO_ENV.is_file():
        return
    for raw in _REPO_ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if not key:
            continue
        if key not in os.environ:
            os.environ[key] = val
            _from_file.add(key)
        elif key in _from_file:
            os.environ[key] = val
