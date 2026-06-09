# limiter.py
# 공유 슬롯 관리자(work_unified 6장). 모델 호출 직전에 acquire()를 불러
# "지금 호출해도 한도에 안 걸리나"를 통과시킨다. 워커 여러 개가 같은 Limiter를
# 공유하면 자연히 줄을 선다(병렬도 가능하나 순차로도 충분 — 6장).
#
# ★ 핵심: TPM(분당 토큰)은 무제한이라 token bucket이 불필요하다.
#   남은 건 RPM·RPD 둘 다 "횟수"라, 토큰이 아니라 호출 횟수 슬롯만 관리한다.
#
# RPM vs RPD — 저장 위치가 다른 이유:
#   RPM(분당 15) = "최근 60초"라 휘발성. 1분 지나면 의미 소멸 → 메모리에만 둔다.
#                  (디스크에 저장하면 죽기 전 타임스탬프가 남아 재시작 직후를 과하게 막음)
#   RPD(하루 1450) = "오늘 누적"이라 재시작에도 살아야 함 → usage.json(디스크)을 본다.
#   성격이 달라 저장 위치가 갈린다.

import time
import threading
import random

from usage import today_calls


class RPDExceeded(Exception):
    """오늘(PT) RPD 안전선을 넘었을 때. 자동 루프에서 자정까지 대기는 위험하므로(6장)
    대기하지 않고 이 예외로 멈춘다 — 상위(loop)가 받아 사람에게 넘긴다(디스코드 통지)."""


class RateLimitError(Exception):
    """429(RESOURCE_EXHAUSTED) 최종 실패. 4xx 영구거부(400/401/403/404)와 명확히 구분한다.
    호출부가 '일시적 한도'와 '재시도 무의미한 거부'를 다르게 다룰 수 있게 별도 타입으로 올린다."""


class PermanentHTTPError(Exception):
    """400/401/403/404 등 재시도해도 의미 없는 클라이언트 오류. 즉시 멈춘다(재시도 금지)."""


class Limiter:
    """호출 횟수 슬롯 관리자.

    rpm: 분당 허용 호출수(무료 티어 15).
    rpd_limit: 하루 안전선(1500이 천장, 안전선 1450 — 6장).
    """

    def __init__(self, rpm: int = 15, rpd_limit: int = 1450):
        self.rpm = rpm
        self.rpd_limit = rpd_limit
        self._calls = []          # 최근 호출 타임스탬프(메모리, RPM용) — monotonic 초
        self._lock = threading.Lock()   # 워커 병렬 대비(슬롯 경쟁 보호)
        # 모델별 global cooldown: 429를 맞은 모델은 이 시각(monotonic)까지 새 호출 금지.
        # 한 칸이 429를 맞으면 같은 모델 다음 칸들이 줄줄이 처박히던 문제(vtx_21 A/B/C)를 막는다.
        self._cooldown_until = {}   # {model: monotonic_deadline}

    def acquire(self, model: str) -> None:
        """호출 가능해질 때까지 블록 후 리턴. 순서:
          1) RPD: today_calls(model)가 rpd_limit 미만인가 — 아니면 RPDExceeded(멈춤, 6장).
          2) RPM: 최근 60초 호출이 rpm개 미만이 될 때까지 (필요하면) 잔다.
          통과하면 현재 타임스탬프를 기록.
        ※ RPD를 먼저 본다 — RPM은 '기다리면 풀리는' 한도지만 RPD는 '오늘은 끝'이라,
          괜히 RPM에서 잠들었다 깨어나 RPD에 막히느니 먼저 끊는 게 맞다.
        """
        # --- 0) global cooldown: 이 모델이 직전에 429를 맞아 쉬는 중이면 그만큼 잔다 ---
        #     (RPD/RPM 검사보다 먼저 — 429 직후 곧장 다음 칸이 같은 한도로 돌진하는 걸 끊는다)
        with self._lock:
            deadline = self._cooldown_until.get(model, 0.0)
            wait = deadline - time.monotonic()
        if wait > 0:
            time.sleep(wait)

        # --- 1) RPD: 기다려도 안 풀리는 한도라 먼저, 락 밖에서 본다 ---
        if today_calls(model) >= self.rpd_limit:
            raise RPDExceeded(
                f"RPD 안전선({self.rpd_limit}) 도달: model={model}, "
                f"today={today_calls(model)}. 자정(PT)까지 대기 대신 멈춤(6장)."
            )

        # --- 2) RPM: 최근 60초 창이 rpm개 미만이 될 때까지 ---
        while True:
            with self._lock:
                now = time.monotonic()
                # 60초보다 오래된 타임스탬프는 창에서 버린다
                self._calls = [t for t in self._calls if now - t < 60.0]
                if len(self._calls) < self.rpm:
                    # 슬롯 있음 → 지금 호출로 기록하고 통과
                    self._calls.append(now)
                    return
                # 슬롯 꽉 참 → 가장 오래된 호출이 60초를 넘길 때까지의 대기시간 계산
                oldest = min(self._calls)
                wait = 60.0 - (now - oldest)
            # 락 밖에서 잔다(자는 동안 다른 워커가 락을 쓸 수 있게)
            if wait > 0:
                time.sleep(wait)
            # 깨어나면 다시 while 처음으로 — 창을 새로 정리하고 재확인

    def backoff(self, attempt: int, retry_after: float = None,
                cap: float = 60.0) -> float:
        """429/5xx 재시도 전 대기. 반환값은 실제로 잔 초(로깅용).

        우선순위:
          1) retry_after(서버 Retry-After 헤더)가 있으면 그 값을 그대로 따른다(상한 cap).
          2) 없으면 지수 백오프 2**attempt + jitter(0~1초 무작위), 상한 cap.
             (jitter는 여러 칸이 동시에 깨어나 같은 순간 재돌진하는 thundering herd를 흩는다)
        attempt는 0,1,2,... → 1, 2, 4, ... cap에서 멈춤.
        """
        if retry_after is not None and retry_after >= 0:
            wait = min(float(retry_after), cap)
        else:
            wait = min(2.0 ** attempt, cap) + random.random()
            wait = min(wait, cap)
        time.sleep(wait)
        return wait

    def set_cooldown(self, model: str, seconds: float) -> None:
        """이 모델을 앞으로 seconds초 동안 global cooldown 상태로 둔다(429 직후 호출).
        같은 모델의 다음 acquire가 그 시간만큼 자도록 만들어, 연쇄 429를 끊는다."""
        if seconds <= 0:
            return
        with self._lock:
            self._cooldown_until[model] = time.monotonic() + seconds


# ======================================================================
# 단독 테스트: python3 limiter.py
# ★ 키·네트워크 불요. usage.today_calls를 가짜로 갈아끼워(monkeypatch) RPD를 흉내내고,
#   RPM은 time.monotonic을 가짜 시계로 바꿔 '실제로 60초 안 자고' 간격 로직만 검증한다.
#   (진짜로 자면 테스트가 1분씩 걸리므로, 시계를 손으로 돌려 로직만 본다.)
# ======================================================================
if __name__ == "__main__":
    import usage as usage_mod
    import limiter as limiter_mod

    M = "gemma-4-26b-a4b-it"
    print("=== limiter.py 슬롯 단독 테스트 ===\n")

    # ---- 가짜 시계: time.monotonic / time.sleep을 갈아끼워 실제 대기 없이 시간만 흐르게 ----
    fake = {"t": 0.0, "slept": []}

    def fake_monotonic():
        return fake["t"]

    def fake_sleep(sec):
        # 자는 대신 가짜 시계만 그만큼 앞으로 — 테스트가 즉시 끝난다
        fake["slept"].append(sec)
        fake["t"] += sec

    limiter_mod.time.monotonic = fake_monotonic
    limiter_mod.time.sleep = fake_sleep

    # ---- 가짜 RPD: today_calls를 우리가 정한 값으로 ----
    rpd_value = {"n": 0}
    limiter_mod.today_calls = lambda model: rpd_value["n"]

    # ---------- [1] RPM: 15개까진 시간 0에 즉시 통과 ----------
    lim = limiter_mod.Limiter(rpm=15, rpd_limit=1450)
    for i in range(15):
        lim.acquire(M)
    assert len(lim._calls) == 15, f"15개 안 채워짐: {len(lim._calls)}"
    assert fake["slept"] == [], "15개 안에서 잠들면 안 됨"
    assert fake["t"] == 0.0, "시간이 흐르면 안 됨"
    print("[1] RPM: 15개 즉시 통과(대기 0) ✓")

    # ---------- [2] RPM: 16번째는 60초 창이 풀릴 때까지 자야 함 ----------
    lim.acquire(M)   # 16번째 — 슬롯 꽉 참 → fake_sleep으로 60초 점프
    assert len(fake["slept"]) == 1, f"16번째에서 한 번 자야: {fake['slept']}"
    assert abs(fake["slept"][0] - 60.0) < 1e-9, f"대기가 60초가 아님: {fake['slept'][0]}"
    # 60초 지났으니 앞의 15개는 창에서 빠지고, 16번째만 남아야
    assert len(lim._calls) == 1, f"창 정리 후 1개여야: {len(lim._calls)}"
    print(f"[2] RPM: 16번째는 60초 대기 후 통과 ✓ (잔 시간={fake['slept'][0]}초)")

    # ---------- [3] RPD: 안전선 도달 시 대기 말고 예외 ----------
    rpd_value["n"] = 1450   # 오늘 이미 1450건
    lim2 = limiter_mod.Limiter(rpm=15, rpd_limit=1450)
    raised = False
    try:
        lim2.acquire(M)
    except limiter_mod.RPDExceeded as e:
        raised = True
        msg = str(e)
    assert raised, "RPD 초과인데 예외 안 남(자정 대기하면 안 됨)"
    assert "안전선" in msg, "예외 메시지 이상"
    print("[3] RPD: 안전선 도달 시 RPDExceeded로 멈춤(자정 대기 안 함) ✓")

    # ---------- [4] RPD: 안전선 미만이면 통과 ----------
    rpd_value["n"] = 1449
    lim2.acquire(M)   # 1449 < 1450 → 통과해야
    print("[4] RPD: 1449 < 1450 통과 ✓")

    # ---------- [5] backoff: 지수적으로 늘고 cap에서 멈추나 (jitter 0~1초 포함) ----------
    fake["slept"] = []
    for a in range(8):
        lim.backoff(a, cap=60.0)
    # base = 1,2,4,8,16,32, 그 뒤 cap=60. 각 항에 0~1초 jitter가 붙되 cap은 안 넘는다.
    base = [1, 2, 4, 8, 16, 32, 60, 60]
    assert len(fake["slept"]) == 8, f"8회 안 잠: {fake['slept']}"
    for got, b in zip(fake["slept"], base):
        if b < 60:
            assert b <= got < b + 1.0 + 1e-9, f"jitter 범위 벗어남: {got} (base {b})"
        else:
            assert got == 60.0, f"cap 초과/미달: {got}"
    print(f"[5] backoff: 지수+jitter 후 cap=60 고정 ✓")

    # ---------- [6] backoff: Retry-After가 있으면 그 값을 따른다(jitter 무시) ----------
    fake["slept"] = []
    w = lim.backoff(0, retry_after=12.0, cap=60.0)
    assert w == 12.0 and fake["slept"] == [12.0], f"Retry-After 무시됨: {fake['slept']}"
    w2 = lim.backoff(0, retry_after=999.0, cap=60.0)   # cap으로 잘려야
    assert w2 == 60.0, f"Retry-After가 cap 안 넘김: {w2}"
    print("[6] backoff: Retry-After 우선 + cap 적용 ✓")

    # ---------- [7] set_cooldown: 모델이 쿨다운 중이면 acquire가 그만큼 잔다 ----------
    fake["slept"] = []
    rpd_value["n"] = 0
    lim3 = limiter_mod.Limiter(rpm=15, rpd_limit=1450)
    lim3.set_cooldown(M, 30.0)          # 이 모델 30초 쿨다운
    lim3.acquire(M)                     # 쿨다운만큼(30초) 자고 통과해야
    assert 30.0 in fake["slept"], f"쿨다운 대기 안 함: {fake['slept']}"
    print("[7] set_cooldown: 쿨다운 중 acquire가 대기 ✓")

    # ---------- [8] 다른 모델은 쿨다운에 안 걸린다 ----------
    fake["slept"] = []
    lim3.set_cooldown(M, 30.0)
    lim3.acquire("other-model")         # 다른 모델 → 즉시 통과
    assert fake["slept"] == [], f"무관 모델이 쿨다운에 걸림: {fake['slept']}"
    print("[8] cooldown: 모델별 격리(무관 모델 즉시 통과) ✓")

    print("\n=== 전체 통과 ✓ ===")
    print("    (RPM은 메모리 타임스탬프, RPD는 usage.json — 성격이 달라 저장 위치 분리)")
