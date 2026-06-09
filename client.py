# client.py
# 모든 모델 호출이 거치는 "단 하나의 입구"(work_unified 2부 토대).
# 2·3·4 단계는 이 call_model()만 부른다 — limiter/usage를 직접 만지지 않는다.
#
# ★ Vertex 전환판: google-genai SDK 대신 Vertex AI publisher 엔드포인트를 REST로 직접 호출한다.
#   - 엔드포인트: https://aiplatform.googleapis.com/v1/publishers/google/models/<model>:generateContent?key=...
#   - 인증: 환경변수 VERTEX_API_KEY (코드·커밋에 키를 넣지 않는다 — §14 보안)
#   - body: {"contents":[{"role":"user","parts":[{"text":...}]}], "systemInstruction":{...}, "generationConfig":{...}}
#   - 모델: Gemini 3.5 Flash (planner/coder/scripter가 모델명을 넘긴다)
#
# 반드시 지킬 함정:
#   [함정1] maxOutputTokens는 "thinking + 출력 합산 예산". 잘리면 finishReason==MAX_TOKENS → truncated=True.
#   [함정2] thinking 모델은 출력 예산을 안 주면 길어진다 → maxOutputTokens 명시(32000).
#   [함정3] 멀티턴에서 이전 턴의 thinking(thoughtSignature)은 history에 넣지 않는다.
#           이 함수는 응답에서 text만 뽑고 thoughtSignature는 버려서 그걸 돕는다.

import os
import json
import time
import sys
import urllib.request
import urllib.error

from limiter import RateLimitError, PermanentHTTPError


_BASE = "https://aiplatform.googleapis.com/v1/publishers/google/models"


def _parse_retry_after(headers) -> float:
    """Retry-After 헤더를 초(float)로. 정수 초만 신뢰(HTTP-date 형식은 무시→None).
    헤더 없거나 파싱 불가면 None을 반환해 호출부가 지수 백오프로 넘어가게 한다."""
    if headers is None:
        return None
    val = headers.get("Retry-After")
    if not val:
        return None
    try:
        return float(int(str(val).strip()))
    except (ValueError, TypeError):
        return None   # HTTP-date 등은 다루지 않는다 — 지수 백오프로 대체


def _log_call_failure(model, attempt, code, body, *, slept, kind) -> None:
    """최종 실패(또는 영구거부)를 stderr에 한 줄 요약 + 본문으로 남긴다.
    이전엔 본문이 잘려 어떤 한도인지 안 보였다 → 모델·attempt·kind·본문을 통째로 찍는다."""
    head = (f"[client] CALL FAILED kind={kind} model={model} "
            f"code={code} attempts={attempt} slept={slept:.1f}s")
    print(head, file=sys.stderr, flush=True)
    print(f"[client] body: {body}", file=sys.stderr, flush=True)


def _get_key() -> str:
    key = os.environ.get("VERTEX_API_KEY")
    if not key:
        raise RuntimeError(
            "VERTEX_API_KEY 환경변수가 없다. export VERTEX_API_KEY=... 로 걸어라(§14 보안)."
        )
    return key


def call_model(model: str, contents, *, limiter, system: str = None,
               max_retries: int = 5) -> dict:
    """모델 1회 호출(Vertex REST). 순서:
       acquire(한도 슬롯) → time 시작 → POST generateContent → 경과초 계산·record_call
       → 5xx/429면 backoff 후 재시도.

    반환 dict: {"text", "finish_reason", "truncated", "in", "out", "sec"}  ← 기존과 동일(호출부 불변).
      - truncated = (finishReason == 'MAX_TOKENS')  ← 함정1 방어.

    contents: 문자열 또는 멀티턴 리스트.
      - 문자열이면 단일 user 턴으로 감싼다.
      - 리스트면 [{"role":..., "parts":[{"text":...}]}, ...] 형태로 그대로 보낸다(이전 thinking은 호출부가 뺀다 — 함정3).
    system: 시스템 프롬프트(있으면 systemInstruction).
    """
    from usage import record_call

    key = _get_key()
    url = f"{_BASE}/{model}:generateContent?key={key}"

    # contents 정규화: 문자열 → 단일 user 턴
    if isinstance(contents, str):
        contents_payload = [{"role": "user", "parts": [{"text": contents}]}]
    else:
        contents_payload = contents

    body = {
        "contents": contents_payload,
        "generationConfig": {
            "temperature": 1,
            "topP": 0.95,
            "topK": 64,
            "maxOutputTokens": 32000,   # 함정2: 항상 명시
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    data = json.dumps(body).encode("utf-8")

    attempt = 0
    while True:
        # --- 한도 슬롯 확보(RPM/RPD). RPD 초과면 RPDExceeded가 올라온다(멈춤) ---
        limiter.acquire(model)

        start = time.time()
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8")
            response = json.loads(raw)
        except urllib.error.HTTPError as e:
            # 응답 본문(에러 메시지)을 읽어 둔다 — 분류와 최종 로깅 양쪽에 쓴다
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                err_body = ""

            # --- 분류: 영구거부 / 일시한도(429) / 일시오류(5xx) ---
            #   400/401/403/404 = 재시도해도 의미 없는 클라이언트 오류 → 즉시 멈춤.
            #   단, 403+RESOURCE_EXHAUSTED는 '쿼터 거부'라 일시한도(429)와 같은 줄로 본다.
            is_quota = ("RESOURCE_EXHAUSTED" in err_body) or (e.code == 429)
            is_permanent = (e.code in (400, 401, 403, 404)) and not is_quota
            is_transient = (e.code in (500, 503)
                            or "INTERNAL" in err_body
                            or "UNAVAILABLE" in err_body)

            if is_permanent:
                # 재시도 금지 — 키/권한/요청 자체 문제. 본문째로 올려 호출부가 멈추게.
                _log_call_failure(model, attempt, e.code, err_body, slept=0.0,
                                  kind="permanent")
                raise PermanentHTTPError(f"{e.code}: {err_body[:500]}")

            if (is_quota or is_transient) and attempt < max_retries:
                # Retry-After 헤더 우선(초 단위 정수 또는 HTTP-date — 정수만 신뢰)
                retry_after = _parse_retry_after(e.headers)
                slept = limiter.backoff(attempt, retry_after=retry_after)
                if is_quota:
                    # 같은 모델 다음 칸이 곧장 같은 429를 맞지 않게 global cooldown.
                    limiter.set_cooldown(model, slept)
                attempt += 1
                continue

            # 재시도 소진 — 최종 실패. 본문·모델·attempt·누적대기까지 남기고 분리해 올린다.
            _log_call_failure(model, attempt, e.code, err_body, slept=0.0,
                              kind="quota" if is_quota else "transient")
            if is_quota:
                raise RateLimitError(f"{e.code} RESOURCE_EXHAUSTED after "
                                     f"{attempt} retries: {err_body[:500]}")
            raise RuntimeError(f"Vertex HTTPError {e.code} after "
                               f"{attempt} retries: {err_body[:500]}")
        except (urllib.error.URLError, TimeoutError) as e:
            # 네트워크/타임아웃도 일시오류로 재시도(서버 헤더 없음 → 지수+jitter)
            if attempt < max_retries:
                slept = limiter.backoff(attempt)
                attempt += 1
                continue
            _log_call_failure(model, attempt, "NET", repr(e), slept=0.0,
                              kind="network")
            raise

        sec = time.time() - start

        # --- 토큰 수: usageMetadata에서 ---
        in_tok = out_tok = 0
        um = response.get("usageMetadata") or {}
        in_tok = um.get("promptTokenCount", 0) or 0
        out_tok = um.get("candidatesTokenCount", 0) or 0

        # --- finishReason + text 추출 ---
        finish_reason = None
        text = ""
        cands = response.get("candidates") or []
        if cands:
            c0 = cands[0]
            finish_reason = c0.get("finishReason")
            # parts[].text만 모은다 — thoughtSignature 등 다른 키는 버린다(함정3)
            parts = (c0.get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts if "text" in p)

        truncated = (finish_reason == "MAX_TOKENS")

        # --- 사용량 기록(단일 입구에서만) ---
        record_call(model, in_tok, out_tok, sec)

        return {
            "text": text,
            "finish_reason": finish_reason,
            "truncated": truncated,
            "in": in_tok,
            "out": out_tok,
            "sec": sec,
        }


# ======================================================================
# 단독 테스트: python3 client.py
# ★ 실제 모델 호출이 필요하다(VERTEX_API_KEY + 네트워크).
# ======================================================================
if __name__ == "__main__":
    from limiter import Limiter

    MODEL = "gemini-3.5-flash"

    print("=== client.py 실호출 단독 테스트 (Vertex REST) ===\n")

    if not os.environ.get("VERTEX_API_KEY"):
        print("✗ VERTEX_API_KEY가 없다. 먼저: export VERTEX_API_KEY=\"...\"")
        raise SystemExit(1)

    import usage as usage_mod
    REAL_USAGE = usage_mod.USAGE_PATH

    lim = Limiter(rpm=15, rpd_limit=1450)
    before = usage_mod.today_calls(MODEL, path=REAL_USAGE)

    print(f"[1] {MODEL}에 '1+1=?' 호출…")
    r = call_model(MODEL, "What is 1+1? Answer with just the number.", limiter=lim)

    for k in ("text", "finish_reason", "truncated", "in", "out", "sec"):
        assert k in r, f"반환 dict에 '{k}' 없음"
    assert isinstance(r["truncated"], bool), "truncated가 bool이 아님"
    assert isinstance(r["in"], int) and isinstance(r["out"], int), "토큰 수 타입 이상"
    assert r["sec"] > 0, "경과시간이 0 이하"
    print(f"    응답: {r['text'][:80]!r}")
    print(f"    finish_reason={r['finish_reason']}, truncated={r['truncated']}")
    print(f"    in={r['in']}, out={r['out']}, sec={r['sec']:.2f}")
    print("[1] 반환 dict 형태 ✓")

    after = usage_mod.today_calls(MODEL, path=REAL_USAGE)
    assert after == before + 1, f"calls 증가분이 1이 아님: {before} -> {after}"
    print(f"[2] usage 기록 ✓ (calls {before} -> {after})")

    print("\n=== 전체 통과 ✓ ===")

