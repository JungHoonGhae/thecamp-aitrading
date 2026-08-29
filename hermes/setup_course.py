"""Hermes를 이 저장소의 Telegram 인터페이스와 수업 명령에 연결한다.

비밀값은 출력하지 않는다. 기본 실행은 플러그인·스킬·명령 메뉴만 맞춘다.
``--managed-telegram``은 사용자 소유의 새 bot을 만들고 토큰·대화 ID를 직접 저장하며,
``--from-project-env``는 기존 ``.env``의 Telegram 값을 Hermes 비밀 저장소로 옮긴다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common import acp_worker  # noqa: E402
from common.judge import PRIMARY_FREE_MODEL, free_models  # noqa: E402

PLUGIN_SOURCE = ROOT / "hermes" / "plugins" / "thecamp-invest"
SKILLS = ROOT / "hermes" / "skills"
COURSE_SCRIPT_NAMES = ("morning-brief.py",)
PUBLIC_COMMANDS = [
    "ts_help",
    "ts_update",
    "ts_doctor",
    "ts_auth",
    "ts_status",
    "ts_tools",
    "ts_config",
    "ts_analyze",
    "ts_rule",
    "ts_order_plan",
    "ts_memory",
]
COURSE_CLARIFY_TIMEOUT_SECONDS = 120
MANAGED_TELEGRAM_TIMEOUT_SECONDS = 300
GATEWAY_START_TIMEOUT_SECONDS = 15
DISCORD_KEYS = (
    "DISCORD_BOT_TOKEN",
    "DISCORD_ALLOWED_USERS",
    "DISCORD_HOME_CHANNEL",
    "DISCORD_HOME_CHANNEL_THREAD_ID",
)
TELEGRAM_REACTION_SOURCE = (
    '"\\U0001f44d" if outcome == ProcessingOutcome.SUCCESS else "\\U0001f44e"'
)
TELEGRAM_REACTION_TARGET = (
    '"\\u2705" if outcome == ProcessingOutcome.SUCCESS else "\\u274c"'
)
PLUGIN_CHOICE_SOURCE = '''\
                    result = plugin_handler(user_args)
                    if asyncio.iscoroutine(result):
                        result = await result
                    return str(result) if result else None
'''
PLUGIN_CHOICE_TARGET = '''\
                    result = plugin_handler(user_args)
                    if asyncio.iscoroutine(result):
                        result = await result
                    if isinstance(result, dict) and result.get("__hermes_choice__") is True:
                        from tools import clarify_gateway as _clarify_mod
                        import uuid as _uuid

                        choices = [
                            str(choice).strip()
                            for choice in (result.get("choices") or [])
                            if str(choice).strip()
                        ][:4]
                        question = str(result.get("question") or "하나를 선택해 주세요.").strip()
                        if not choices:
                            return "선택 항목을 만들지 못했습니다. 수업 연결을 다시 설치해 주세요."
                        adapter = self._adapter_for_source(source)
                        if adapter is None:
                            return "버튼을 보낼 수 없습니다. 수업 연결을 다시 설치해 주세요."

                        clarify_id = _uuid.uuid4().hex[:10]
                        _clarify_mod.register(
                            clarify_id=clarify_id,
                            session_key=_quick_key,
                            question=question,
                            choices=choices,
                            multi_select=False,
                        )
                        sent = await adapter.send_clarify(
                            chat_id=str(source.chat_id),
                            question=question,
                            choices=choices,
                            clarify_id=clarify_id,
                            session_key=_quick_key,
                            metadata=self._thread_metadata_for_source(source),
                        )
                        if not getattr(sent, "success", False):
                            _clarify_mod.clear_session(_quick_key)
                            return "버튼을 보내지 못했습니다. 수업 연결을 다시 설치해 주세요."

                        timeout = _clarify_mod.get_clarify_timeout()
                        selected = await asyncio.to_thread(
                            _clarify_mod.wait_for_response,
                            clarify_id,
                            float(timeout),
                        )
                        if not selected:
                            return str(result.get("timeout_message") or "선택 시간이 끝났습니다. 다시 실행해 주세요.")
                        result = plugin_handler(selected)
                        if asyncio.iscoroutine(result):
                            result = await result
                    return str(result) if result else None
'''


def _find_executable(name: str) -> str | None:
    """Find CLI installs that GUI coding apps and non-login shells often miss."""
    found = shutil.which(name)
    if found:
        return found

    home = Path.home()
    suffixes = (name, f"{name}.exe", f"{name}.cmd")
    local_app_data = os.environ.get("LOCALAPPDATA")
    roots = [
        home / ".local" / "bin",
        home / "bin",
        home / ".npm-global" / "bin",
        home / "AppData" / "Roaming" / "npm",
        home / "AppData" / "Local" / "hermes" / "bin",
        home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links",
    ]
    if local_app_data:
        roots.insert(0, Path(local_app_data) / "hermes" / "bin")
    for root in roots:
        for suffix in suffixes:
            candidate = root / suffix
            if candidate.is_file():
                return str(candidate)
    return None


def _hermes_python(hermes_home: Path) -> Path:
    candidates = (
        hermes_home / "hermes-agent" / "venv" / "bin" / "python",
        hermes_home / "hermes-agent" / "venv" / "Scripts" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Hermes 설정용 Python을 찾지 못했습니다. Hermes 설치 상태를 확인해 주세요.")


def _ensure_telegram_reaction_symbols(hermes_home: Path) -> bool:
    """Keep Telegram lifecycle reactions classroom-readable across updates.

    Hermes 0.20.x documents check/cross reactions but its Telegram adapter
    still ships thumbs-up/down literals.  Patch only that exact expression,
    validate the resulting module, and leave unknown future versions alone.
    Returning ``False`` lets the caller report that the installed Hermes
    version needs review instead of claiming a symbol was changed.
    """
    adapter = (
        hermes_home
        / "hermes-agent"
        / "plugins"
        / "platforms"
        / "telegram"
        / "adapter.py"
    )
    if not adapter.is_file():
        return False

    source = adapter.read_text(encoding="utf-8")
    if TELEGRAM_REACTION_TARGET in source:
        return True
    if TELEGRAM_REACTION_SOURCE not in source:
        return False

    updated = source.replace(
        TELEGRAM_REACTION_SOURCE,
        TELEGRAM_REACTION_TARGET,
        1,
    )
    compile(updated, str(adapter), "exec")

    original_mode = stat.S_IMODE(adapter.stat().st_mode)
    fd, temporary = tempfile.mkstemp(
        prefix=".telegram_adapter_",
        suffix=".tmp",
        dir=adapter.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, original_mode)
        os.replace(temporary, adapter)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return True


def _ensure_plugin_choice_bridge(hermes_home: Path) -> bool:
    """Let deterministic plugin commands render native gateway choices.

    Hermes plugin commands normally return only text. Course menus must not
    depend on a language model remembering to call ``clarify``, so setup adds
    one narrowly-scoped structured return type to the existing dispatch block.
    Unknown future versions are left untouched and reported to the caller.
    """
    gateway = hermes_home / "hermes-agent" / "gateway" / "run.py"
    if not gateway.is_file():
        return False

    source = gateway.read_text(encoding="utf-8")
    if PLUGIN_CHOICE_TARGET in source:
        return True
    if PLUGIN_CHOICE_SOURCE not in source:
        return False

    updated = source.replace(PLUGIN_CHOICE_SOURCE, PLUGIN_CHOICE_TARGET, 1)
    compile(updated, str(gateway), "exec")
    original_mode = stat.S_IMODE(gateway.stat().st_mode)
    fd, temporary = tempfile.mkstemp(
        prefix=".gateway_choice_",
        suffix=".tmp",
        dir=gateway.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, original_mode)
        os.replace(temporary, gateway)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return True


def _hermes(*args: str, capture: bool = False) -> str:
    executable = _find_executable("hermes")
    if executable is None:
        raise FileNotFoundError("Hermes 실행 파일을 찾지 못했습니다.")
    done = subprocess.run(
        [executable, *args],
        check=True,
        text=True,
        capture_output=capture,
    )
    return (done.stdout or "").strip()


def _env_values(path: Path) -> dict[str, str]:
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


def _quote_env(value: str) -> str:
    if value and all(ch not in value for ch in " #\t\r\n\"'"):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _update_env(path: Path, updates: dict[str, str], removals: tuple[str, ...] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if path.exists() else []
    wanted = set(updates)
    remove = set(removals)
    output: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        candidate = stripped[7:].lstrip() if stripped.startswith("export ") else stripped
        key = candidate.split("=", 1)[0].strip() if "=" in candidate else ""
        if key in remove:
            continue
        if key in wanted:
            if key not in seen:
                output.append(f"{key}={_quote_env(updates[key])}")
                seen.add(key)
            continue
        output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={_quote_env(value)}")

    fd, temporary = tempfile.mkstemp(prefix=".env_", suffix=".tmp", dir=path.parent)
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


def _install_plugin(hermes_home: Path) -> None:
    target = hermes_home / "plugins" / "thecamp-invest"
    target.mkdir(parents=True, exist_ok=True)
    for source in PLUGIN_SOURCE.iterdir():
        if source.is_file():
            shutil.copy2(source, target / source.name)
    (target / ".repo-path").write_text(str(ROOT) + "\n", encoding="utf-8")
    _hermes("plugins", "enable", "thecamp-invest", "--no-allow-tool-override")


def _install_course_scripts(hermes_home: Path) -> tuple[str, ...]:
    """Install read-only classroom scripts with this repo's exact path."""
    target_dir = hermes_home / "scripts"
    target_dir.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    placeholder = 'REPO = r"__여기에_저장소_절대경로__"'
    for name in COURSE_SCRIPT_NAMES:
        source = ROOT / "hermes" / "scripts" / name
        body = source.read_text(encoding="utf-8")
        if placeholder not in body:
            raise RuntimeError(f"수업 자동화 스크립트의 저장소 경로 자리를 찾지 못했습니다: {name}")
        body = body.replace(placeholder, f"REPO = {str(ROOT)!r}", 1)
        compile(body, str(source), "exec")
        (target_dir / name).write_text(body, encoding="utf-8")
        installed.append(name)
    return tuple(installed)


def _configure_commands() -> None:
    raw = _hermes("config", "get", "skills.external_dirs", capture=True)
    try:
        external = json.loads(raw)
    except json.JSONDecodeError:
        external = []
    if not isinstance(external, list):
        external = []
    skill_path = str(SKILLS)
    external = [str(item) for item in external if str(item)]
    if skill_path not in external:
        external.append(skill_path)
    _hermes("config", "set", "platforms.telegram.extra.command_menu.priority_mode", "prepend")
    # 수업 명령을 맨 위에 두되 Hermes 기본 명령도 함께 보인다.
    _hermes("config", "set", "platforms.telegram.extra.command_menu.max_commands", "60")
    # Telegram native lifecycle feedback: 👀 while working, ✅ on success,
    # ❌ on failure.  This is especially important while Claude/Codex is doing
    # a longer analysis and no text has arrived yet.
    _hermes("config", "set", "telegram.reactions", "true")
    # 수업 중 버튼을 놓쳐도 한 세션이 10분씩 잠기지 않게 한다.
    _hermes(
        "config", "set", "agent.clarify_timeout",
        str(COURSE_CLARIFY_TIMEOUT_SECONDS),
    )

    # `hermes config set` stores JSON-looking values as strings for these
    # dynamic leaves. Use Hermes' own config writer so both external skill dirs
    # and command priority remain real YAML lists.
    hermes_home = Path(_hermes("config", "path", capture=True)).expanduser().parent
    hermes_python = _hermes_python(hermes_home)
    code = (
        "import json,sys; "
        "from hermes_cli.config import read_raw_config,save_config; "
        "c=read_raw_config(); "
        "c.setdefault('skills',{})['external_dirs']=json.loads(sys.argv[1]); "
        "p=c.setdefault('platforms',{}).setdefault('telegram',{}).setdefault('extra',{}).setdefault('command_menu',{}); "
        "p['priority']=json.loads(sys.argv[2]); "
        "save_config(c,strip_defaults=False)"
    )
    subprocess.run(
        [
            str(hermes_python), "-c", code,
            json.dumps(external, ensure_ascii=False),
            json.dumps(PUBLIC_COMMANDS),
        ],
        check=True,
        text=True,
    )


def _configure_router() -> tuple[str, ...]:
    """Nous 추천 목록의 무료 모델만 주 라우터와 폴백으로 고정한다."""
    models = free_models()
    primary = models[0] if models else PRIMARY_FREE_MODEL
    fallbacks = [
        {
            "provider": "nous",
            "model": model,
            "base_url": "https://inference-api.nousresearch.com/v1",
        }
        for model in models[1:]
        if model.endswith(":free")
    ]
    _hermes("config", "set", "model.default", primary)
    _hermes("config", "set", "model.provider", "nous")
    # Dynamic root keys are otherwise stored as one quoted JSON string by
    # `hermes config set`, which `hermes fallback list` correctly ignores.
    hermes_home = Path(_hermes("config", "path", capture=True)).expanduser().parent
    hermes_python = _hermes_python(hermes_home)
    code = (
        "import json,sys; "
        "from hermes_cli.config import read_raw_config,save_config; "
        "c=read_raw_config(); "
        "c['fallback_providers']=json.loads(sys.argv[1]); "
        "c.pop('fallback_model',None); "
        "save_config(c,strip_defaults=False)"
    )
    subprocess.run(
        [str(hermes_python), "-c", code, json.dumps(fallbacks)],
        check=True,
        text=True,
    )
    return models


def _prepare_claude_acp() -> str:
    """공식 SDK 어댑터를 npx 캐시에 준비한다. Claude 로그인은 건드리지 않는다."""
    claude = acp_worker.find_executable("claude")
    if claude is None:
        return "Claude Code 없음 · Codex/무료 폴백 사용"
    command = acp_worker.claude_acp_command()
    if not command:
        return "Node.js 22 또는 claude-agent-acp 필요 · Claude CLI 폴백 사용"
    try:
        done = subprocess.run(
            command,
            input="",
            text=True,
            capture_output=True,
            timeout=120,
            cwd=ROOT,
            env=acp_worker._cli_env(claude, command[0]),
        )
    except (OSError, subprocess.TimeoutExpired):
        return "Claude ACP 준비 실패 · Claude CLI 폴백 사용"
    if done.returncode != 0:
        return "Claude ACP 준비 실패 · Claude CLI 폴백 사용"
    return f"Claude ACP 준비 · {acp_worker.CLAUDE_ACP_PACKAGE} · 기존 Claude 로그인 사용"


def _gateway_is_running(output: str) -> bool:
    lowered = output.lower()
    if any(word in lowered for word in ("not loaded", "not running", "stopped", "inactive")):
        return False
    return "pid " in lowered or "active (running)" in lowered or "supervised" in lowered


def _gateway_call(*args: str) -> subprocess.CompletedProcess[str]:
    executable = _find_executable("hermes")
    if executable is None:
        raise FileNotFoundError("Hermes 실행 파일을 찾지 못했습니다.")
    return subprocess.run(
        [executable, "gateway", *args],
        check=False,
        text=True,
        capture_output=True,
        timeout=45,
    )


def _activate_gateway() -> str:
    """Restart an existing gateway or install and start a first one."""
    status = _gateway_call("status")
    current = (status.stdout or "") + "\n" + (status.stderr or "")
    if _gateway_is_running(current):
        action = _gateway_call("restart")
        label = "다시 연결"
    else:
        action = _gateway_call("start")
        label = "시작"
        if action.returncode != 0:
            installed = _gateway_call("install")
            if installed.returncode != 0:
                raise RuntimeError("Hermes gateway 서비스를 설치하지 못했습니다.")
            action = _gateway_call("start")
    if action.returncode != 0:
        raise RuntimeError("Hermes gateway를 시작하지 못했습니다.")

    deadline = time.monotonic() + GATEWAY_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        checked = _gateway_call("status")
        output = (checked.stdout or "") + "\n" + (checked.stderr or "")
        if checked.returncode == 0 and _gateway_is_running(output):
            return label
        time.sleep(1)
    raise RuntimeError("Hermes gateway가 15초 안에 실행 상태가 되지 않았습니다.")


def _managed_telegram_result(hermes_home: Path) -> tuple[str, str, str]:
    """Create a user-owned Telegram bot through Hermes' official managed flow.

    The child process writes the token to a mode-600 temporary file. The token
    never appears in stdout, argv, shell history, or the AI's response.
    """
    hermes_python = _hermes_python(hermes_home)
    helper = textwrap.dedent(
        r"""
        import json
        import os
        import pathlib
        import sys
        import time
        import webbrowser

        from hermes_cli.telegram_managed_bot import (
            create_pairing,
            poll_pairing_result_once,
            print_qr_code,
        )

        output = pathlib.Path(sys.argv[1])
        timeout = int(sys.argv[2])
        pairing = create_pairing(bot_name="THE CAMP · TS 투자 에이전트")
        if pairing is None:
            raise SystemExit("Hermes Telegram 연결 서비스를 열지 못했습니다.")

        print("\nTelegram에서 열린 화면의 Create Bot만 눌러 주세요.", flush=True)
        print("화면이 열리지 않으면 아래 QR을 휴대폰으로 읽어 주세요.\n", flush=True)
        print_qr_code(pairing.qr_payload, include_link=True)
        sys.stdout.flush()
        webbrowser.open(pairing.deep_link)

        deadline = time.monotonic() + timeout
        result = None
        while time.monotonic() < deadline:
            try:
                result = poll_pairing_result_once(None, pairing)
            except Exception:
                result = None
            if result is not None:
                break
            time.sleep(2)

        if result is None or result.owner_user_id is None:
            raise SystemExit("Telegram 소유 확인이 끝나지 않았습니다. 다시 실행해 주세요.")

        payload = {
            "token": result.token,
            "owner_user_id": str(result.owner_user_id),
            "bot_username": result.bot_username or pairing.suggested_username,
        }
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
        print("✅ 새 Telegram 투자 에이전트 소유 확인 완료")
        """
    )

    with tempfile.TemporaryDirectory(prefix="thecamp-telegram-") as temporary:
        result_path = Path(temporary) / "managed-bot.json"
        subprocess.run(
            [
                str(hermes_python),
                "-c",
                helper,
                str(result_path),
                str(MANAGED_TELEGRAM_TIMEOUT_SECONDS),
            ],
            check=True,
            text=True,
        )
        payload = json.loads(result_path.read_text(encoding="utf-8"))

    token = str(payload.get("token", "")).strip()
    chat_id = str(payload.get("owner_user_id", "")).strip()
    username = str(payload.get("bot_username", "")).strip()
    if not token or not chat_id or not chat_id.lstrip("-").isdigit():
        raise RuntimeError("새 Telegram 봇의 연결 정보를 안전하게 받지 못했습니다.")
    return token, chat_id, username


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes 수업용 Telegram 연결")
    telegram_source = parser.add_mutually_exclusive_group()
    telegram_source.add_argument(
        "--from-project-env",
        action="store_true",
        help="저장소 .env의 Telegram 토큰·대화 ID를 Hermes에 복사",
    )
    telegram_source.add_argument(
        "--managed-telegram",
        action="store_true",
        help="Hermes 공식 Managed Bot으로 사용자 소유의 새 Telegram 봇 생성",
    )
    parser.add_argument(
        "--remove-discord",
        action="store_true",
        help="Hermes에 잘못 넣은 Discord 연결값만 제거",
    )
    args = parser.parse_args()

    if _find_executable("hermes") is None:
        raise SystemExit("Hermes를 찾지 못했습니다. 먼저 Hermes 공식 설치와 무료 로그인을 마쳐 주세요.")
    config_path = Path(_hermes("config", "path", capture=True)).expanduser()
    env_path = Path(_hermes("config", "env-path", capture=True)).expanduser()
    hermes_home = config_path.parent

    _install_plugin(hermes_home)
    installed_scripts = _install_course_scripts(hermes_home)
    _configure_commands()
    reactions_ready = _ensure_telegram_reaction_symbols(hermes_home)
    choices_ready = _ensure_plugin_choice_bridge(hermes_home)
    free_chain = _configure_router()
    claude_route = _prepare_claude_acp()

    updates: dict[str, str] = {}
    managed_username = ""
    if args.managed_telegram:
        token, chat_id, managed_username = _managed_telegram_result(hermes_home)
        _update_env(
            ROOT / ".env",
            {
                "TELEGRAM_BOT_TOKEN": token,
                "TELEGRAM_CHANNEL_ID": chat_id,
            },
        )
        updates = {
            "TELEGRAM_BOT_TOKEN": token,
            "TELEGRAM_ALLOWED_USERS": chat_id,
            "TELEGRAM_HOME_CHANNEL": chat_id,
        }
    elif args.from_project_env:
        project = _env_values(ROOT / ".env")
        token = project.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = project.get("TELEGRAM_CHANNEL_ID", "").strip()
        if not token or not chat_id:
            raise SystemExit(".env에 TELEGRAM_BOT_TOKEN과 TELEGRAM_CHANNEL_ID가 모두 필요합니다.")
        try:
            int(chat_id)
        except ValueError as error:
            raise SystemExit("TELEGRAM_CHANNEL_ID는 숫자여야 합니다.") from error
        updates = {
            "TELEGRAM_BOT_TOKEN": token,
            "TELEGRAM_ALLOWED_USERS": chat_id,
            "TELEGRAM_HOME_CHANNEL": chat_id,
        }

    removals = DISCORD_KEYS if args.remove_discord else ()
    # The running gateway refreshes ~/.hermes/.env between turns. Keeping the
    # same flag here makes reactions take effect without requiring a disruptive
    # mid-class restart, while config.yaml remains the durable source of truth.
    runtime_updates = {"TELEGRAM_REACTIONS": "true", **updates}
    _update_env(env_path, runtime_updates, removals)

    gateway_action = ""
    if updates:
        try:
            gateway_action = _activate_gateway()
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            raise SystemExit(
                "❌ Telegram 값은 안전하게 저장했지만 gateway 연결을 끝내지 못했습니다 · "
                f"{error}\nAI에게 이 문장을 보여 주면 저장된 값은 유지한 채 이어서 고칩니다."
            ) from error

    print(f"✅ Hermes 수업 명령: /ts_* {len(PUBLIC_COMMANDS)}개 연결")
    print(f"✅ 무료 라우터: {free_chain[0] if free_chain else PRIMARY_FREE_MODEL}")
    print(f"✅ 무료 폴백: {max(len(free_chain) - 1, 0)}개 · :free 모델만")
    print(f"✅ {claude_route}" if claude_route.startswith("Claude ACP 준비") else f"🟡 {claude_route}")
    print("✅ AI 검토 순서: Claude ACP → Claude CLI → Codex CLI → Nous 무료 모델")
    if reactions_ready:
        print("✅ Telegram 처리 표시: 👀 작업 중 → ✅ 완료 / ❌ 실패")
    else:
        print("🟡 Telegram 처리 표시: 설치된 Hermes 버전 확인 필요")
    print("✅ Telegram 승인 방식: 번호 복사 없이 승인·보류 버튼")
    print(f"✅ Telegram 자동화 예제: {', '.join(installed_scripts)} 준비")
    if choices_ready:
        print("✅ Telegram 선택 메뉴: AI 호출 없이 즉시 버튼 표시")
    else:
        print("🟡 Telegram 선택 메뉴: 설치된 Hermes 버전 확인 필요")
    if updates:
        print("✅ Telegram 비밀값: Hermes에 저장 (값은 표시하지 않음)")
        print(f"✅ Telegram gateway: {gateway_action} 완료")
        if managed_username:
            print(f"✅ 새 Telegram 투자 에이전트: @{managed_username}")
    elif _env_values(env_path).get("TELEGRAM_BOT_TOKEN"):
        print("✅ Telegram 기존 연결: 유지 (값은 표시하지 않음)")
    else:
        print("다음: hermes gateway setup 에서 Telegram을 연결하세요.")
    if not updates:
        print("설정을 바꾼 경우에만 다음 실행: hermes gateway restart")


if __name__ == "__main__":
    main()
