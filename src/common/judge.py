"""판단 층 — 규칙이 못 하는 일을 AI에게 넘긴다.

이 저장소는 두 층으로 되어 있다. 섞지 않는 것이 요점이다.

  · 규칙(코드)  — 계산하고, 견주고, 차단한다.
                  같은 입력이면 늘 같은 답. 공짜. agent.py · routines/*.py
  · 판단(AI)    — 「이게 무슨 뜻인가」, 「내가 놓친 게 있나」.
                  답이 매번 조금 다르다. 그래서 **주문에는 닿지 않는다.**

주문은 언제나 규칙이 낸다. AI는 읽고 말할 뿐이다. 이 선을 지켜라.

부르는 순서: Claude → Codex → Nous 무료 폴백 체인. Hermes는 이 순서를 조율하는 라우터다.
Claude나 Codex를 쓸 수 있으면 실제 검토를 맡기고, 둘 다 막혔을 때만 무료 모델이 직접
답한다. 모두 실패하면 각 경로의 상태를 보여 주고 규칙 결과만 계속 돌린다.
"""
from __future__ import annotations

import shutil
import subprocess
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from . import acp_worker
except ImportError:  # ``python src/common/judge.py`` 직접 실행용
    import acp_worker  # type: ignore

# 한 작업자가 응답하지 않는다고 수업 전체가 잠기지 않게 한다. 3분은
# Telegram의 생존 신호이지 강제 종료 시간이 아니다. ACP는 이벤트가 오는
# 동안 계속 기다리고, CLI 폴백과 전체 체인에만 넉넉한 안전 상한을 둔다.
TIMEOUT = 180
TOTAL_TIMEOUT = 420
PRIMARY_FREE_MODEL = "upstage/solar-pro4:free"
STEPFUN_MODEL = "stepfun/step-3.7-flash:free"
PREFERRED_FREE_MODELS = (
    PRIMARY_FREE_MODEL,
    STEPFUN_MODEL,
    "meituan/longcat-2.0:free",
    "tencent/hy3:free",
    "poolside/laguna-s-2.1:free",
    "poolside/laguna-xs-2.1:free",
)
NOUS_MODEL_CACHE = Path.home() / ".hermes" / "cache" / "nous_recommended_cache.json"

# 앞에 있는 것부터 쓴다. 무료 모델은 마지막 안전망이며 평소에는 라우팅만 맡는다.
ENGINES = ("claude", "codex", "free")

DEFAULT_RULES = """\
너는 투자 조언자가 아니다. 아래 재료를 읽고 사람이 확인할 거리만 짚는다.

지켜라.
- 사라거나 팔라고 하지 마라. 수익을 단정하지 마라.
- **재료에 없는 숫자를 지어내지 마라.** 이게 가장 중요하다.
- 한 줄을 쓸 때마다 그 근거가 재료의 어느 줄인지 끝에 대괄호로 밝혀라.
  예: 삼성전자가 목표보다 16.9%p 높다 [내 계좌]
- 재료만으로 판단이 안 되면 그렇게 적어라. 예: 판단 불가 — 재무 자료가 재료에 없음
- 짧게. 세 줄을 넘기지 마라.
- 짚을 게 없으면 「특별히 짚을 것 없음」 한 줄로 끝내라."""

# 재료가 어디서 왔는지. 알림 아래에 그대로 붙여 학생이 출처를 보게 한다.
SOURCE_NOTE = {
    "kis": "한국투자증권 모의투자 (공식)",
    "market": "Yahoo Finance — 과거시세·지수·환율·업종 (학습용 조회 경로)",
    "crypto": "업비트 시세 (공식)",
    "spec": "내-투자-스펙.md (내가 적음)",
}


def sources_line(used: list[str]) -> str:
    """근거 한 줄. 어떤 데이터를 보고 한 말인지 남긴다."""
    names = [SOURCE_NOTE[k] for k in used if k in SOURCE_NOTE]
    return "근거: " + " · ".join(names) if names else ""


def available() -> str:
    """지금 쓸 수 있는 AI 도구 이름. 없으면 빈 문자열."""
    for name in ENGINES:
        executable = "hermes" if name == "free" else name
        if shutil.which(executable):
            return name
    return ""


@dataclass(frozen=True)
class RouteAttempt:
    """학생에게 공개할 수 있게 정리한 한 경로의 실행 상태."""

    engine: str
    status: str
    model: str = ""
    effort: str = ""
    transport: str = ""


@dataclass(frozen=True)
class AskResult:
    """AI 호출 결과. 실패를 숨기지 않되 규칙 루틴은 계속 돌 수 있게 한다."""

    text: str
    engine: str
    status: str
    notice: str
    attempts: tuple[RouteAttempt, ...] = ()
    model: str = ""
    effort: str = ""
    transport: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.text)


def _short_model(model: str) -> str:
    return model.rsplit("/", 1)[-1].removesuffix(":free")


def engine_label(engine: str, model: str = "") -> str:
    """내부 실행 파일 이름을 수업 화면의 역할 이름으로 바꾼다."""
    return {
        "claude": "Claude",
        "codex": "Codex",
        "free": f"무료 폴백 · {_short_model(model)}" if model else "Nous 무료 폴백",
    }.get(engine, "AI 작업자")


def engine_details(
    engine: str, model: str = "", effort: str = "", transport: str = ""
) -> str:
    """보고서에 실제 작업자 설정을 짧고 명확하게 표시한다."""
    parts = [engine_label(engine, model)]
    if transport:
        parts.append(transport)
    if engine in {"claude", "codex"} and model:
        parts.append(f"모델 {model}")
    if engine in {"claude", "codex"} and effort:
        parts.append(f"effort {effort}")
    return " · ".join(parts)


def configured_profile(
    engine: str,
    *,
    claude_settings: Path | None = None,
    codex_config: Path | None = None,
    routed_model: str = "",
) -> tuple[str, str]:
    """Claude/Codex가 실제 호출에 쓸 모델과 effort를 설정에서 읽는다."""
    if engine == "free":
        return routed_model, ""
    if engine == "claude":
        path = claude_settings
        if path is None:
            config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude")).expanduser()
            path = config_dir / "settings.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return "", ""
        if not isinstance(data, dict):
            return "", ""
        return str(data.get("model", "") or ""), str(data.get("effortLevel", "") or "")
    if engine == "codex":
        path = codex_config
        if path is None:
            path = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser() / "config.toml"
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            return "", ""

        def value(key: str) -> str:
            match = re.search(
                rf'^\s*{re.escape(key)}\s*=\s*["\']([^"\']+)["\']\s*$',
                body,
                re.MULTILINE,
            )
            return match.group(1).strip() if match else ""

        return value("model"), value("model_reasoning_effort")
    return "", ""


_ROUTE_STATUS_LABELS = {
    "ok": "응답",
    "not_installed": "설치되지 않음",
    "usage_limit": "사용 한도·호출 제한",
    "login_required": "로그인 필요",
    "timeout": "응답 시간 초과",
    "failed": "호출 실패",
}


def route_attempt_line(attempt: RouteAttempt) -> str:
    """라우팅 한 경로를 모델 설정까지 포함해 한 줄로 만든다."""
    parts = [
        engine_label(attempt.engine, attempt.model),
    ]
    if attempt.transport:
        parts.append(attempt.transport)
    parts.append(_ROUTE_STATUS_LABELS.get(attempt.status, "확인 필요"))
    if attempt.engine in {"claude", "codex"} and attempt.model:
        parts.append(f"모델 {attempt.model}")
    if attempt.engine in {"claude", "codex"} and attempt.effort:
        parts.append(f"effort {attempt.effort}")
    return " · ".join(parts)


def route_report(result: AskResult) -> str:
    """성공과 실패를 숨기지 않는 짧은 라우팅 상태 카드."""
    attempts = result.attempts or (
        (RouteAttempt(
            result.engine, result.status, result.model, result.effort, result.transport
        ),)
        if result.engine else ()
    )
    lines = ["[AI 경로 · Hermes 라우팅]"]
    for attempt in attempts:
        mark = "✅" if attempt.status == "ok" else "↪"
        lines.append(f"{mark} {route_attempt_line(attempt)}")
    if not attempts:
        lines.append("↪ 연결된 AI 작업자 없음")
    return "\n".join(lines)


def _failure(
    status: str,
    engine: str = "",
    attempts: tuple[RouteAttempt, ...] = (),
    model: str = "",
    effort: str = "",
    transport: str = "",
) -> AskResult:
    name = engine_label(engine, model) if engine else "Claude/Codex/무료 모델"
    notices = {
        "not_installed": (
            "Claude/Codex/Hermes 실행 파일을 찾지 못해 AI 검토를 건너뛰었습니다. "
            "규칙 계산·가드레일·주문 미리보기는 그대로 동작합니다."
        ),
        "usage_limit": (
            f"{name}의 사용 한도 또는 호출 제한 때문에 이번 AI 검토를 받지 못했습니다. "
            "한도가 풀린 뒤 다시 시도할 수 있고, 규칙 계산은 그대로 동작합니다."
        ),
        "login_required": (
            f"{name} 로그인이 필요해 이번 AI 검토를 받지 못했습니다. "
            "노트북에서 로그인한 뒤 다시 시도하세요. 규칙 계산은 그대로 동작합니다."
        ),
        "timeout": (
            f"{name} 응답 시간이 초과되어 이번 AI 검토를 받지 못했습니다. "
            "잠시 뒤 다시 시도할 수 있고, 규칙 계산은 그대로 동작합니다."
        ),
        "failed": (
            f"{name} 호출이 실패해 이번 AI 검토를 받지 못했습니다. "
            "노트북의 오류를 확인해 주세요. 규칙 계산은 그대로 동작합니다."
        ),
    }
    return AskResult(
        "", engine, status, notices[status], attempts, model, effort, transport
    )


def _classify_failure(stderr: str) -> str:
    lower = stderr.lower()
    if any(word in lower for word in ("quota", "rate limit", "usage limit", "credit", "capacity")):
        return "usage_limit"
    if any(word in lower for word in ("login", "unauthorized", "authentication", "api key", "sign in")):
        return "login_required"
    return "failed"


def unavailable_result() -> AskResult:
    """호출 가능한 라우터·작업자가 없을 때의 공개 상태."""
    return _failure("not_installed")


def free_models(cache_path: Path = NOUS_MODEL_CACHE) -> tuple[str, ...]:
    """안정 순서 뒤에 Nous가 추천한 현재 ``:free`` 모델만 덧붙인다."""
    candidates = list(PREFERRED_FREE_MODELS)
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        for portal in cache.values() if isinstance(cache, dict) else ():
            data = portal.get("data", {}) if isinstance(portal, dict) else {}
            recommended = data.get("freeRecommendedModels", [])
            for item in recommended if isinstance(recommended, list) else ():
                model = str(item.get("modelName", "")) if isinstance(item, dict) else ""
                if model.endswith(":free"):
                    candidates.append(model)
    except (OSError, TypeError, ValueError):
        pass
    return tuple(dict.fromkeys(model for model in candidates if model.endswith(":free")))


def _command(
    engine: str,
    prompt: str,
    *,
    research: bool,
    model: str = "",
    effort: str = "",
) -> list[str]:
    """각 작업자를 쓰기 권한 없이 한 번 호출한다."""
    if engine == "claude":
        tools = "WebSearch,WebFetch" if research else ""
        command = [
            "claude", "-p", prompt,
            "--max-turns", "4" if research else "1",
            "--tools", tools,
            "--no-session-persistence",
            "--safe-mode",
        ]
        if model:
            command += ["--model", model]
        if effort:
            command += ["--effort", effort]
        return command
    if engine == "codex":
        command = [
            "codex", "exec", "--sandbox", "read-only", "--ephemeral",
            "--color", "never", prompt,
        ]
        if model:
            command[2:2] = ["-m", model]
        if effort:
            command[2:2] = ["-c", f'model_reasoning_effort="{effort}"']
        return command
    if engine == "free":
        if not model.endswith(":free"):
            raise ValueError("무료 폴백에는 :free 모델만 사용할 수 있습니다.")
        return [
            "hermes", "-z", prompt,
            "--provider", "nous",
            "--model", model,
            "--ignore-rules",
        ]
    raise ValueError(f"지원하지 않는 AI 경로: {engine}")


def ask_with_status(
    재료: str,
    질문: str,
    규칙: str = DEFAULT_RULES,
    *,
    research: bool = False,
    prefer_acp: bool = True,
) -> AskResult:
    """재료를 주고 답과 호출 상태를 함께 돌려준다."""
    prompt = f"{규칙}\n\n[질문]\n{질문}\n\n[재료]\n{재료}"
    found = False
    last_failure: AskResult | None = None
    attempts: list[RouteAttempt] = []
    routes: list[tuple[str, str, str]] = []
    if prefer_acp:
        routes.append(("claude", "", "ACP"))
    routes += [("claude", "", "CLI"), ("codex", "", "CLI")]
    routes.extend(("free", model, "Nous") for model in free_models())
    started = time.monotonic()
    skip_claude_cli = False
    for name, routed_model, transport in routes:
        if name == "claude" and transport == "CLI" and skip_claude_cli:
            continue
        model, effort = configured_profile(name, routed_model=routed_model)
        executable = "hermes" if name == "free" else name
        route_available = (
            acp_worker.available()
            if name == "claude" and transport == "ACP"
            else bool(shutil.which(executable))
        )
        if not route_available:
            attempts.append(RouteAttempt(
                name, "not_installed", model, effort, transport
            ))
            if name == "free":
                break
            continue
        found = True
        remaining = TOTAL_TIMEOUT - (time.monotonic() - started)
        if remaining <= 0:
            attempts.append(RouteAttempt(name, "timeout", model, effort, transport))
            return _failure(
                "timeout", name, tuple(attempts), model, effort, transport
            )
        if name == "claude" and transport == "ACP":
            try:
                acp_result = acp_worker.run_claude(
                    prompt,
                    cwd=Path.cwd(),
                    research=research,
                    model=model,
                    effort=effort,
                    hard_timeout=max(1, min(
                        acp_worker.HARD_TIMEOUT_SECONDS, int(remaining)
                    )),
                )
            except acp_worker.ACPIdleTimeout:
                attempts.append(RouteAttempt(
                    name, "timeout", model, effort, transport
                ))
                last_failure = _failure(
                    "timeout", name, tuple(attempts), model, effort, transport
                )
                # 모델이 이미 일을 시작한 뒤 멈췄다면 같은 Claude 요청을 CLI로
                # 중복 실행하지 않고 Codex로 넘긴다.
                skip_claude_cli = True
                continue
            except (OSError, acp_worker.ACPError) as error:
                status = _classify_failure(str(error))
                attempts.append(RouteAttempt(
                    name, status, model, effort, transport
                ))
                last_failure = _failure(
                    status, name, tuple(attempts), model, effort, transport
                )
                # 로그인·한도 문제는 전송 방식만 바꿔도 같으므로 Claude를
                # 다시 부르지 않는다. 어댑터 시작 실패만 공식 CLI로 폴백한다.
                if status in {"usage_limit", "login_required"}:
                    skip_claude_cli = True
                continue
            attempts.append(RouteAttempt(name, "ok", model, effort, transport))
            return AskResult(
                acp_result.text,
                name,
                "ok",
                "",
                tuple(attempts),
                model,
                effort,
                transport,
            )
        try:
            done = subprocess.run(
                _command(
                    name, prompt, research=research, model=model, effort=effort
                ),
                capture_output=True,
                text=True,
                timeout=max(1, min(TIMEOUT, int(remaining))),
            )
        except subprocess.TimeoutExpired:
            attempts.append(RouteAttempt(name, "timeout", model, effort, transport))
            last_failure = _failure(
                "timeout", name, tuple(attempts), model, effort, transport
            )
            continue
        except OSError:
            attempts.append(RouteAttempt(name, "failed", model, effort, transport))
            last_failure = _failure(
                "failed", name, tuple(attempts), model, effort, transport
            )
            continue
        out = (done.stdout or "").strip()
        if done.returncode == 0 and out:
            attempts.append(RouteAttempt(name, "ok", model, effort, transport))
            return AskResult(
                out, name, "ok", "", tuple(attempts), model, effort, transport
            )
        status = _classify_failure(done.stderr or done.stdout or "")
        attempts.append(RouteAttempt(name, status, model, effort, transport))
        last_failure = _failure(
            status, name, tuple(attempts), model, effort, transport
        )
    if not found:
        return _failure("not_installed", attempts=tuple(attempts))
    return last_failure or _failure("failed")


def ask(재료: str, 질문: str, 규칙: str = DEFAULT_RULES) -> str:
    """기존 호출부용 문자열 API. 자세한 실패 이유는 ask_with_status를 쓴다."""
    return ask_with_status(재료=재료, 질문=질문, 규칙=규칙).text


def demo() -> None:
    """python src/common/judge.py — 도구가 있으면 실제로 한 번 물어본다."""
    tool = available()
    if not tool:
        print("OK — 쓸 수 있는 AI 도구가 없습니다. 판단 층은 건너뜁니다(정상).")
        return
    answer = ask(재료="삼성전자 36.9% (목표 20%) · 현대차 9.8% (목표 20%)",
                 질문="비중이 목표와 벌어진 종목을 짚어라.")
    assert answer, f"{tool} 가 빈 답을 줬습니다"
    assert len(answer) < 2000, "답이 너무 깁니다"
    print(f"OK — {tool} 응답 {len(answer)}자\n{answer[:200]}")


if __name__ == "__main__":
    demo()
