"""KIS 공식 트레이딩 MCP를 모의투자 전용으로 연결한다.

학생은 이 파일을 직접 조립하지 않는다. Claude Code·Codex·초록이가 Docker가
준비된 뒤 실행하며, 비밀값을 화면에 출력하지 않는다. 공식 166개 API는 서버 안에서
8개 분야 도구로 묶여 Hermes에 보인다. ``kis-lecture-lab``은 건드리지 않는다.
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_REPOSITORY = "https://github.com/koreainvestment/open-trading-api.git"
DEFAULT_SOURCE = Path.home() / ".cache" / "thecamp" / "open-trading-api"
MCP_RELATIVE_DIR = Path("MCP") / "Kis Trading MCP"
RUNTIME_ENV = Path.home() / ".config" / "thecamp" / "kis-trade-mcp.env"
IMAGE = "kis-trade-mcp:lecture"
CONTAINER = "kis-trade-mcp"
MCP_URL = "http://127.0.0.1:3000/sse"


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _find_executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    executable = f"{name}.exe" if os.name == "nt" else name
    home = Path.home()
    candidates: list[Path] = []
    if name == "hermes":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "hermes" / "bin" / "hermes.exe")
        candidates.append(home / "AppData" / "Local" / "hermes" / "bin" / "hermes.exe")
    candidates += [home / ".docker" / "bin" / executable, home / ".local" / "bin" / executable]
    if name == "docker":
        candidates += [
            home / "Applications" / "Docker.app" / "Contents" / "Resources" / "bin" / "docker",
            Path("/Applications/Docker.app/Contents/Resources/bin/docker"),
        ]
        candidates.extend(_windows_docker_candidates(os.environ))
    return next((str(candidate) for candidate in candidates if candidate.is_file()), None)


def _windows_docker_candidates(environment: os._Environ[str] | dict[str, str]) -> list[Path]:
    """Return per-user and system Docker CLI locations used by Docker Desktop."""
    candidates: list[Path] = []
    for variable in ("ProgramFiles", "ProgramW6432"):
        base = environment.get(variable)
        if base:
            candidates.append(
                Path(base) / "Docker" / "Docker" / "resources" / "bin" / "docker.exe"
            )
    local_app_data = environment.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data) / "Docker" / "resources" / "bin" / "docker.exe"
        )
    return candidates


def _subprocess_env(docker: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    paths = [str(Path.home() / ".docker" / "bin"), str(Path.home() / ".local" / "bin")]
    local_app_data = env.get("LOCALAPPDATA")
    if local_app_data:
        paths.append(str(Path(local_app_data) / "hermes" / "bin"))
    if docker:
        paths.append(str(Path(docker).parent))
    env["PATH"] = os.pathsep.join([*paths, env.get("PATH", "")])
    return env


def _run(
    command: list[str],
    *,
    timeout: int,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=capture,
        timeout=timeout,
        check=check,
        env=env,
    )


def _credentials() -> dict[str, str]:
    values = _read_env(ROOT / ".env")
    required = ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT")
    missing = [
        key for key in required
        if not values.get(key) or "여기에" in values[key] or "모의" in values[key]
    ]
    if missing:
        raise RuntimeError("KIS 모의투자 값이 준비되지 않았습니다: " + ", ".join(missing))
    return values


def _existing_token(path: Path) -> str:
    return _read_env(path).get("MCP_ACCESS_TOKEN", "")


def _write_runtime_env(path: Path, values: dict[str, str]) -> None:
    account = values["KIS_ACCOUNT"].replace("-", "")[:8]
    token = _existing_token(path) or secrets.token_urlsafe(48)
    runtime = {
        "ENV": "live",
        "MCP_TYPE": "sse",
        "MCP_HOST": "0.0.0.0",
        "MCP_PORT": "3000",
        "MCP_PATH": "/sse",
        "MCP_ACCESS_TOKEN": token,
        "KIS_APP_KEY": values["KIS_APP_KEY"],
        "KIS_APP_SECRET": values["KIS_APP_SECRET"],
        "KIS_PAPER_APP_KEY": values["KIS_APP_KEY"],
        "KIS_PAPER_APP_SECRET": values["KIS_APP_SECRET"],
        "KIS_ACCT_STOCK": account,
        "KIS_PAPER_STOCK": account,
        "KIS_PROD_TYPE": "01",
    }
    if values.get("KIS_HTS_ID"):
        runtime["KIS_HTS_ID"] = values["KIS_HTS_ID"]

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="kis-mcp-", suffix=".env", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            for key, value in runtime.items():
                stream.write(f"{key}={value}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _prepare_source(source: Path, *, update: bool, env: dict[str, str]) -> None:
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        _run(
            ["git", "clone", "--depth", "1", OFFICIAL_REPOSITORY, str(source)],
            timeout=180,
            env=env,
        )
    elif update:
        _run(["git", "-C", str(source), "pull", "--ff-only"], timeout=120, env=env)
    if not (source / MCP_RELATIVE_DIR / "Dockerfile").is_file():
        raise RuntimeError("KIS 공식 트레이딩 MCP Dockerfile을 찾지 못했습니다.")


def _configure_hermes(hermes: str, token: str, env: dict[str, str]) -> None:
    gateway_status = _run(
        [hermes, "gateway", "status"],
        timeout=15,
        check=False,
        capture=True,
        env=env,
    )
    gateway_was_running = _gateway_is_running(
        (gateway_status.stdout or "") + "\n" + (gateway_status.stderr or "")
    )
    hermes_home = Path(
        _run([hermes, "config", "path"], timeout=10, capture=True, env=env).stdout.strip()
    ).expanduser().parent
    hermes_python = hermes_home / "hermes-agent" / "venv" / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )
    if not hermes_python.is_file():
        raise RuntimeError("Hermes 설정용 Python을 찾지 못했습니다.")
    code = (
        "import sys; "
        "from hermes_cli.config import save_env_value; "
        "from hermes_cli.mcp_config import _save_mcp_server,_bearer_auth_headers; "
        "save_env_value('MCP_KIS_TRADE_MCP_API_KEY',sys.argv[1]); "
        "c={'url':sys.argv[2],'transport':'sse','headers':_bearer_auth_headers('kis-trade-mcp'),"
        "'enabled':True,'connect_timeout':30}; "
        "assert _save_mcp_server('kis-trade-mcp',c)"
    )
    _run([str(hermes_python), "-c", code, token, MCP_URL], timeout=20, env=env)
    _run([hermes, "mcp", "test", CONTAINER], timeout=45, env=env)
    if gateway_was_running:
        _run([hermes, "gateway", "restart"], timeout=45, check=False, env=env)


def _gateway_is_running(output: str) -> bool:
    lowered = output.lower()
    stopped_markers = ("not loaded", "not running", "stopped", "inactive")
    if any(marker in lowered for marker in stopped_markers):
        return False
    running_markers = ("supervised", "running", "active (running)", "pid ")
    return any(marker in lowered for marker in running_markers)


def setup(*, source: Path, update: bool = True, rebuild: bool = True) -> None:
    docker = _find_executable("docker")
    if not docker:
        raise RuntimeError("Docker Desktop이 없습니다. 공식 앱을 설치한 뒤 한 번 실행해 주세요.")
    env = _subprocess_env(docker)
    if _run([docker, "ps"], timeout=8, check=False, capture=True, env=env).returncode != 0:
        raise RuntimeError("Docker Desktop 엔진이 8초 안에 응답하지 않았습니다. 앱 상태를 확인해 주세요.")

    values = _credentials()
    _write_runtime_env(RUNTIME_ENV, values)
    _prepare_source(source, update=update, env=env)
    if rebuild:
        _run(
            [docker, "build", "-t", IMAGE, "."],
            timeout=600,
            env=env,
            cwd=source / MCP_RELATIVE_DIR,
        )
    exists = _run(
        [docker, "container", "inspect", CONTAINER],
        timeout=10,
        check=False,
        capture=True,
        env=env,
    ).returncode == 0
    if exists:
        _run([docker, "rm", "-f", CONTAINER], timeout=30, env=env)
    _run(
        [
            docker, "run", "-d", "--name", CONTAINER, "--restart", "unless-stopped",
            "-p", "127.0.0.1:3000:3000", "--env-file", str(RUNTIME_ENV), IMAGE,
        ],
        timeout=45,
        env=env,
    )
    if not _run(
        [docker, "inspect", "-f", "{{.State.Running}}", CONTAINER],
        timeout=10,
        capture=True,
        env=env,
    ).stdout.strip().lower().endswith("true"):
        raise RuntimeError("KIS MCP 컨테이너가 시작되지 않았습니다.")

    hermes = _find_executable("hermes")
    if not hermes:
        raise RuntimeError("Hermes를 찾지 못했습니다. Hermes 설치를 먼저 마쳐 주세요.")
    token = _existing_token(RUNTIME_ENV)
    _configure_hermes(hermes, token, env)
    print("✅ KIS Trading MCP · 공식 166 API · 모의투자 기본 · Hermes 연결")
    print("✅ kis-lecture-lab · 수업용 5개 · 그대로 유지")
    print("🔒 127.0.0.1 전용 · 비밀값 출력 안 함 · 주문 실행 안 함")


def main() -> None:
    parser = argparse.ArgumentParser(description="KIS 공식 트레이딩 MCP 수업 연결")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--no-update", action="store_true")
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()
    try:
        setup(source=args.source.expanduser(), update=not args.no_update, rebuild=not args.no_build)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(f"❌ KIS Trading MCP 연결 실패 · {error}") from error


if __name__ == "__main__":
    main()
