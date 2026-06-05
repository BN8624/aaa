# client.py
# 모든 모델 호출이 거치는 "단 하나의 입구"(work_unified 2부 토대).
# 2·3·4 단계는 이 call_model()만 부른다 — limiter/usage를 직접 만지지 않는다.
# 그래야 한도 관리·사용량 기록이 한 곳에서만 일어나 새지 않는다.
#
# 호출 문법은 3장 확정본(공식 문서로 재확인). 반드시 지킬 함정 3가지:
#   [함정1] max_output_tokens는 "출력 상한"이 아니라 "thinking + 출력 합산 예산"이다.
#           thinking이 예산을 다 먹으면 코드가 잘린다 → finish_reason==MAX_TOKENS면 truncated=True.
#   [함정2] thinking 모델은 max_output_tokens를 안 주면 무한 thinking으로 멈춘다(공식 이슈 #2062).
#           → 항상 32000 명시. 절대 빼지 말 것.
#   [함정3] 멀티턴에서 이전 턴의 thinking은 history에 넣지 않는다. 최종 text만 쌓는다.
#           (call_model은 받은 contents를 그대로 보낼 뿐 — thinking을 history에 넣고 말고는
#            호출하는 쪽 책임. 이 함수는 thinking을 반환하지 않음으로써 그걸 돕는다.)

import os
import time

from google import genai
from google.genai import types


# 클라이언트는 한 번만 만들어 재사용(매 호출 새로 만들 필요 없음).
# 환경변수 GOOGLE_API_KEY에서 키를 읽는다 — 코드·커밋에 키를 넣지 않는다(§14 보안).
_client = None


def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError(
                "GOOGLE_API_KEY 환경변수가 없다. export GOOGLE_API_KEY=... 로 걸어라(§14 보안)."
            )
        _client = genai.Client(api_key=key)
    return _client


def call_model(model: str, contents, *, limiter, system: str = None,
               max_retries: int = 5) -> dict:
    """모델 1회 호출. 순서:
       acquire(한도 슬롯) → time 시작 → generate_content → 경과초 계산·record_call
       → 429면 backoff 후 재시도.

    반환 dict: {"text", "finish_reason", "truncated", "in", "out", "sec"}
      - truncated = (finish_reason == 'MAX_TOKENS')  ← 함정1 방어. 상위 단계가 보고 '잘림' 처리.

    contents: 문자열 또는 멀티턴 리스트(3장). 멀티턴이면 호출하는 쪽이 이전 thinking을 빼고 줘야 함(함정3).
    system: 시스템 프롬프트(있으면 config의 system_instruction으로).
    """
    # usage 기록은 여기서(단일 입구). import는 함수 안에 둬서 토대 import 순환을 피한다.
    from usage import record_call

    client = _get_client()

    # 3장 확정 설정. max_output_tokens=32000 절대 포함(함정2).
    config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="high"),  # Gemma4: on이면 high
        temperature=1,
        top_p=0.95,
        top_k=64,
        max_output_tokens=32000,
        system_instruction=system,   # None이면 무시됨
    )

    attempt = 0
    while True:
        # --- 한도 슬롯 확보(RPM/RPD). RPD 초과면 여기서 RPDExceeded가 올라온다(멈춤) ---
        limiter.acquire(model)

        start = time.time()
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            # 429(Too Many Requests)로 보이면 백오프 후 재시도(대시보드-실제 어긋남 대비, 6장).
            # 그 외 예외는 그대로 올린다(조용히 삼키지 않음 — 짐작 금지).
            msg = str(e)
            is_429 = "429" in msg or "RESOURCE_EXHAUSTED" in msg or "rate" in msg.lower()
            if is_429 and attempt < max_retries:
                limiter.backoff(attempt)
                attempt += 1
                continue
            raise

        sec = time.time() - start

        # --- 토큰 수: usage_metadata에서(3장). 없을 수도 있으니 방어적으로 ---
        in_tok = out_tok = 0
        um = getattr(response, "usage_metadata", None)
        if um is not None:
            in_tok = getattr(um, "prompt_token_count", 0) or 0
            out_tok = getattr(um, "candidates_token_count", 0) or 0

        # --- finish_reason 추출(함정1: MAX_TOKENS면 잘림) ---
        finish_reason = None
        cands = getattr(response, "candidates", None)
        if cands:
            fr = getattr(cands[0], "finish_reason", None)
            # enum일 수도, 문자열일 수도 → 이름으로 통일
            finish_reason = getattr(fr, "name", None) or (str(fr) if fr is not None else None)
        truncated = (finish_reason == "MAX_TOKENS")

        # --- 텍스트: truncated여도 부분 텍스트는 받는다(상위가 판단) ---
        # response.text가 None일 수 있어(잘림·차단) 방어
        text = getattr(response, "text", None) or ""

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
# ★ 실제 모델 호출이 필요하다(GOOGLE_API_KEY + 네트워크).
#   - 26B에 "1+1=?"를 던져 답이 오나, usage.json에 calls=1/in/out/sec가 찍히나.
#   - 반환 dict에 필요한 키가 다 있나, truncated 플래그가 bool인가.
# 한도(RPM 15)를 진짜로 쓰므로 호출은 최소(1~2회)만.
# ======================================================================
if __name__ == "__main__":
    import os as _os
    from limiter import Limiter

    M26 = "gemma-4-26b-a4b-it"

    print("=== client.py 실호출 단독 테스트 ===\n")

    if not _os.environ.get("GOOGLE_API_KEY"):
        print("✗ GOOGLE_API_KEY가 없다. 먼저: export GOOGLE_API_KEY=\"...\"")
        raise SystemExit(1)

    # usage를 테스트 전용 파일로 돌려 실제 usage.json을 더럽히지 않는다.
    # ★ record_call/load_usage에 path를 '명시적으로' 넘긴다 — 모듈변수(USAGE_PATH)를
    #   바꿔도 call_model 안의 record_call은 import 시점 기본값을 써서 안 먹기 때문.
    #   call_model은 record_call을 기본 경로로 부르므로, 호출 전후로 그 기본 경로를
    #   잠시 갈아끼우는 대신, 여기선 호출이 쓴 '실제 usage.json'을 직접 확인한다.
    import usage as usage_mod
    REAL_USAGE = usage_mod.USAGE_PATH   # call_model이 실제로 기록하는 곳("usage.json")

    lim = Limiter(rpm=15, rpd_limit=1450)

    # 호출 전 현재 calls 수를 기억(이미 기록이 있을 수 있으니 '증가분'으로 검증)
    before = usage_mod.today_calls(M26, path=REAL_USAGE)

    print("[1] 26B에 '1+1=?' 호출…")
    r = call_model(M26, "What is 1+1? Answer with just the number.", limiter=lim)

    # 반환 dict 형태 검증
    for k in ("text", "finish_reason", "truncated", "in", "out", "sec"):
        assert k in r, f"반환 dict에 '{k}' 없음"
    assert isinstance(r["truncated"], bool), "truncated가 bool이 아님"
    assert isinstance(r["in"], int) and isinstance(r["out"], int), "토큰 수 타입 이상"
    assert r["sec"] > 0, "경과시간이 0 이하"
    print(f"    응답: {r['text'][:80]!r}")
    print(f"    finish_reason={r['finish_reason']}, truncated={r['truncated']}")
    print(f"    in={r['in']}, out={r['out']}, sec={r['sec']:.2f}")
    print("[1] 반환 dict 형태 ✓")

    # usage.json에 1건 늘었나(증가분으로 확인 — 절대값이 아니라 +1)
    after = usage_mod.today_calls(M26, path=REAL_USAGE)
    assert after == before + 1, f"calls 증가분이 1이 아님: {before} -> {after}"
    print(f"[2] usage 기록 ✓ (calls {before} -> {after}, 이번 호출 in={r['in']}, out={r['out']})")

    print("\n=== 전체 통과 ✓ ===")
    print("    (truncated 방어·usage 단일입구 기록 확인. 한도는 limiter가 관리)")
