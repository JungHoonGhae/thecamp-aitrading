#!/usr/bin/env bash
# VERSION + CHANGELOG 맨 위 칸으로 GitHub 릴리즈를 만든다.
# 사용:  scripts/release.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ver="$(tr -d '[:space:]' < VERSION)"
tag="v${ver}"

if git rev-parse "$tag" >/dev/null 2>&1; then
  echo "이미 태그 $tag 가 있습니다. 먼저 VERSION 을 올리세요."
  exit 1
fi

py=python3
command -v python3 >/dev/null || py=python
notes="$($py - <<'PY'
from pathlib import Path
ver = Path("VERSION").read_text(encoding="utf-8").strip()
text = Path("CHANGELOG.md").read_text(encoding="utf-8")
lines = text.splitlines()
start = None
for i, line in enumerate(lines):
    if line.startswith("## ") and ver in line.split("—")[0]:
        start = i
        break
if start is None:
    raise SystemExit(f"CHANGELOG.md 에 {ver} 칸이 없습니다.")
chunk = []
for line in lines[start + 1:]:
    if line.startswith("## "):
        break
    chunk.append(line)
body = "\n".join(chunk).strip()
print(f"수업 자료 {ver}\n\n{body}\n\n맞추는 말: 수업 자료 업데이트 해 줘")
PY
)"

git tag -a "$tag" -m "수업 자료 ${ver}"
git push origin HEAD "$tag"
gh release create "$tag" --title "수업 자료 ${ver}" --notes "$notes"
echo "릴리즈: $(gh release view "$tag" --json url -q .url)"
