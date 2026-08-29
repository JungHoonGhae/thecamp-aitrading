"""공식 KIS 설정에 남은 모의 키를 프로젝트 .env로 값 노출 없이 복구한다."""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path.home() / "KIS" / "config" / "kis_devlp.yaml"
TARGET = ROOT / ".env"
MAPPING = {
    "paper_app": "KIS_APP_KEY",
    "paper_sec": "KIS_APP_SECRET",
    "my_paper_stock": "KIS_ACCOUNT",
}


def _yaml_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _valid(source: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    minimum = {"paper_app": 20, "paper_sec": 40, "my_paper_stock": 8}
    for source_key, target_key in MAPPING.items():
        value = source.get(source_key, "").strip()
        if len(value) < minimum[source_key] or any(
            word in value for word in ("앱키", "시크릿", "계좌", "여기에")
        ):
            raise ValueError(f"{source_key}가 실제 모의투자 값 형태가 아닙니다.")
        if source_key == "my_paper_stock" and not value.isdigit():
            raise ValueError("my_paper_stock은 숫자 8자리여야 합니다.")
        result[target_key] = value
    return result


def _update_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if path.is_file() else []
    output: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in updates:
            if key not in seen:
                output.append(f"{key}={updates[key]}")
                seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")

    fd, temporary = tempfile.mkstemp(prefix=".env-recover-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(output).rstrip() + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit("공식 KIS 설정 파일을 찾지 못했습니다.")
    values = _valid(_yaml_values(SOURCE))
    _update_env(TARGET, values)
    print("✅ KIS 모의투자 설정 복구 완료")
    print("✅ 앱 키·시크릿·계좌 값은 화면에 표시하지 않았습니다")
    print("✅ 기존 Telegram 값과 KIS_MODE는 유지했습니다")


if __name__ == "__main__":
    main()
