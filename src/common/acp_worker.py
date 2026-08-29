"""Claude Agent SDK를 ACP로 호출하는 작은 읽기 전용 클라이언트.

ACP 자체는 인증 토큰을 보관하지 않는다. 공식 ``claude-agent-acp``가
Claude Code의 네이티브 로그인 저장소를 사용하며, 이 모듈은 JSON-RPC만 주고받는다.
분석 세션에는 웹 조회 외의 내장 도구를 노출하지 않아 주문·파일 수정에 닿지 않는다.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


CLAUDE_ACP_PACKAGE = "@agentclientprotocol/claude-agent-acp@0.70.0"
IDLE_TIMEOUT_SECONDS = 120
HARD_TIMEOUT_SECONDS = 420


class ACPError(RuntimeError):
    """ACP 세션이 정상적으로 끝나지 않았을 때."""


class ACPIdleTimeout(TimeoutError):
    """작업 이벤트가 일정 시간 동안 하나도 오지 않았을 때."""


def find_executable(name: str) -> str | None:
    """Find CLIs hidden from GUI apps' shorter PATH on macOS and Windows."""
    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    local_app_data = os.environ.get("LOCALAPPDATA")
    roots = [
        home / ".local" / "bin",
        home / "bin",
        home / ".npm-global" / "bin",
        home / "AppData" / "Roaming" / "npm",
        home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links",
    ]
    if local_app_data:
        roots.insert(0, Path(local_app_data) / "hermes" / "bin")
    for root in roots:
        for candidate_name in (name, f"{name}.exe", f"{name}.cmd"):
            candidate = root / candidate_name
            if candidate.is_file():
                return str(candidate)
    return None


def _cli_env(*executables: str | None) -> dict[str, str]:
    env = os.environ.copy()
    parents = [str(Path(item).parent) for item in executables if item]
    current = env.get("PATH", "")
    env["PATH"] = os.pathsep.join([*dict.fromkeys(parents), current])
    return env


@dataclass(frozen=True)
class ACPResult:
    text: str
    thought: str = ""
    tools: tuple[str, ...] = ()


def claude_acp_command() -> list[str]:
    """설치된 어댑터를 우선하고, 없으면 npx의 고정 버전을 쓴다."""
    installed = find_executable("claude-agent-acp")
    if installed:
        return [installed]
    npx = find_executable("npx")
    if npx:
        return [npx, "--yes", CLAUDE_ACP_PACKAGE]
    return []


def available() -> bool:
    return bool(find_executable("claude") and claude_acp_command())


def _windows_creationflags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def run_claude(
    prompt: str,
    *,
    cwd: Path,
    research: bool = False,
    model: str = "",
    effort: str = "",
    idle_timeout: int = IDLE_TIMEOUT_SECONDS,
    hard_timeout: int = HARD_TIMEOUT_SECONDS,
    on_progress: Callable[[str], None] | None = None,
) -> ACPResult:
    """한 개의 Claude ACP 세션을 열고 최종 텍스트를 돌려준다.

    ``idle_timeout``은 총 실행시간이 아니라 마지막 ACP 이벤트 이후의 시간이다.
    따라서 정상적으로 진행 중인 긴 분석을 3분에 일괄 중단하지 않는다.
    """
    command = claude_acp_command()
    if not command:
        raise FileNotFoundError("claude-agent-acp 또는 npx를 찾지 못했습니다.")
    claude = find_executable("claude")
    if claude is None:
        raise FileNotFoundError("Claude Code CLI를 찾지 못했습니다.")

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=str(cwd.resolve()),
            env=_cli_env(claude, command[0]),
            creationflags=_windows_creationflags(),
        )
    except OSError as error:
        raise ACPError(f"Claude ACP 시작 실패: {error}") from error

    if process.stdin is None or process.stdout is None:
        process.kill()
        raise ACPError("Claude ACP가 표준 입출력을 열지 못했습니다.")

    inbox: queue.Queue[dict] = queue.Queue()
    stderr_tail: deque[str] = deque(maxlen=30)

    def read_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                value = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict):
                inbox.put(value)

    def read_stderr() -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            stderr_tail.append(line.rstrip())

    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()

    next_id = 0
    started = time.monotonic()
    last_activity = started
    text_parts: list[str] = []
    thought_parts: list[str] = []
    tools_used: list[str] = []

    def stop() -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass

    def reply(message_id: object, result: object) -> None:
        payload = {"jsonrpc": "2.0", "id": message_id, "result": result}
        process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        process.stdin.flush()

    def handle_server(message: dict) -> bool:
        nonlocal last_activity
        method = message.get("method")
        if not isinstance(method, str):
            return False
        last_activity = time.monotonic()
        params = message.get("params") or {}
        if method == "session/update":
            update = params.get("update") or {}
            kind = str(update.get("sessionUpdate") or "")
            content = update.get("content") or {}
            chunk = str(content.get("text") or "") if isinstance(content, dict) else ""
            if kind == "agent_message_chunk" and chunk:
                text_parts.append(chunk)
            elif kind == "agent_thought_chunk" and chunk:
                thought_parts.append(chunk)
            elif kind in {"tool_call", "tool_call_update"}:
                title = str(update.get("title") or update.get("kind") or "도구 사용")
                if title and title not in tools_used:
                    tools_used.append(title)
                    if on_progress:
                        on_progress(title)
            return True
        if method == "session/request_permission":
            # 분석 세션이므로 쓰기·셸 실행 요청은 모두 거절한다.
            reply(message.get("id"), {"outcome": {"outcome": "cancelled"}})
            return True
        if message.get("id") is not None:
            process.stdin.write(json.dumps({
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32601, "message": "수업 분석 세션에서 지원하지 않는 ACP 요청입니다."},
            }, ensure_ascii=False) + "\n")
            process.stdin.flush()
            return True
        return True

    def request(method: str, params: dict) -> object:
        nonlocal next_id, last_activity
        next_id += 1
        request_id = next_id
        process.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
        }, ensure_ascii=False) + "\n")
        process.stdin.flush()
        last_activity = time.monotonic()
        while True:
            now = time.monotonic()
            if now - started > hard_timeout:
                raise ACPIdleTimeout("Claude ACP 분석이 수업용 최대 실행시간을 넘었습니다.")
            if now - last_activity > idle_timeout:
                raise ACPIdleTimeout("Claude ACP에서 진행 신호가 없어 중단했습니다.")
            if process.poll() is not None:
                detail = "\n".join(stderr_tail).strip()
                raise ACPError(detail or "Claude ACP 프로세스가 일찍 종료되었습니다.")
            try:
                message = inbox.get(timeout=0.2)
            except queue.Empty:
                continue
            last_activity = time.monotonic()
            if handle_server(message):
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message.get("error") or {}
                raise ACPError(str(error.get("message") or error))
            return message.get("result")

    try:
        request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {},
            "clientInfo": {
                "name": "thecamp-hermes-router",
                "title": "The Camp Hermes Router",
                "version": "1.0.0",
            },
        })
        options: dict[str, object] = {
            "tools": ["WebSearch", "WebFetch"] if research else [],
            "disallowedTools": [
                "Bash", "Write", "Edit", "NotebookEdit", "Task", "TaskCreate", "TaskUpdate",
            ],
        }
        if model:
            options["model"] = model
        if effort:
            options["effort"] = effort
        session = request("session/new", {
            "cwd": str(cwd.resolve()),
            "mcpServers": [],
            "_meta": {"claudeCode": {"options": options}},
        })
        session_id = str((session or {}).get("sessionId") or "") if isinstance(session, dict) else ""
        if not session_id:
            raise ACPError("Claude ACP가 sessionId를 반환하지 않았습니다.")
        if on_progress:
            on_progress("Claude ACP 연결 완료")
        request("session/prompt", {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": prompt}],
        })
        text = "".join(text_parts).strip()
        if not text:
            raise ACPError("Claude ACP가 빈 응답을 반환했습니다.")
        return ACPResult(text, "".join(thought_parts).strip(), tuple(tools_used))
    finally:
        stop()
