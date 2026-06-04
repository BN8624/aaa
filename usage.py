# usage.py
# 모델 호출 1건마다 calls·in·out·sec 네 가지를 PT 날짜별·모델별로 누적한다(work_unified 11장).
# 비용 시뮬은 나중에 붙이지만, 데이터는 지금부터 쌓아야 나중에 단가표만 곱하면 된다.
#
# 두 가지가 이 파일의 핵심 책임:
#   1) record_call: 호출 1건을 오늘(PT) 항목에 누적하고 즉시 저장.
#   2) today_calls: 오늘(PT) 누적 호출수 반환 — limiter가 RPD 체크에 쓴다.
#
# ★ 날짜 키는 반드시 PT 기준(util.today_pt). RPD 리셋이 PT 자정이라(6장),
#   로컬시간으로 끊으면 카운터가 RPD와 어긋난다. usage와 RPD가 같은 경계를 봐야 한다.

import json
import os

from util import today_pt, atomic_write_json

USAGE_PATH = "usage.json"


def load_usage(path: str = USAGE_PATH) -> dict:
    """usage.json을 읽어 dict로 반환. 없으면 빈 구조({})."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def record_call(model: str, in_tokens: int, out_tokens: int, seconds: float,
                path: str = USAGE_PATH) -> None:
    """호출 1건을 오늘(PT) model 항목에 누적(calls+1, in/out/sec 더함). 즉시 저장.

    구조 예(11장):
      {"2026-06-01": {"gemma-4-26b-a4b-it": {"calls":12,"in":30000,"out":18000,"sec":145.2}}}
    """
    usage = load_usage(path)
    day = today_pt()
    # 날짜 -> 모델 -> 4지표 순으로 없으면 만들며 들어간다
    day_bucket = usage.setdefault(day, {})
    m = day_bucket.setdefault(model, {"calls": 0, "in": 0, "out": 0, "sec": 0.0})
    m["calls"] += 1
    m["in"] += in_tokens
    m["out"] += out_tokens
    m["sec"] += seconds
    atomic_write_json(path, usage)   # 즉시 저장(원자적 — util 공유)


def today_calls(model: str, path: str = USAGE_PATH) -> int:
    """오늘(PT) 해당 model 누적 호출수. limiter가 RPD 안전선 체크에 쓴다.
    오늘·이 모델 기록이 아직 없으면 0."""
    usage = load_usage(path)
    return usage.get(today_pt(), {}).get(model, {}).get("calls", 0)


# ======================================================================
# 단독 테스트: python3 usage.py
# 키·네트워크 불요 — 파일 누적 로직만 본다.
# ======================================================================
if __name__ == "__main__":
    import shutil

    TEST_DIR = "/tmp/aaa_usage_test"
    shutil.rmtree(TEST_DIR, ignore_errors=True)
    os.makedirs(TEST_DIR, exist_ok=True)
    P = os.path.join(TEST_DIR, "usage.json")

    M26 = "gemma-4-26b-a4b-it"
    M31 = "gemma-4-31b-it"

    print("=== usage.py 누적 단독 테스트 ===\n")

    # 0) 기록 없을 때 today_calls는 0
    assert today_calls(M26, path=P) == 0, "초기 호출수가 0이 아님"
    assert load_usage(P) == {}, "없는 파일은 빈 dict여야"
    print("[0] 초기 상태 0 ✓")

    # 1) 26B 3번, 31B 1번 기록
    record_call(M26, 1000, 500, 2.0, path=P)
    record_call(M26, 2000, 800, 3.5, path=P)
    record_call(M26, 1500, 600, 1.5, path=P)
    record_call(M31, 3000, 1200, 4.0, path=P)
    print("[1] 26B 3건 + 31B 1건 기록 완료")

    # 2) 누적이 맞나 — calls 개수
    assert today_calls(M26, path=P) == 3, f"26B calls 불일치: {today_calls(M26, path=P)}"
    assert today_calls(M31, path=P) == 1, f"31B calls 불일치: {today_calls(M31, path=P)}"
    print("[2] calls 누적 ✓ (26B=3, 31B=1)")

    # 3) in/out/sec 합산이 맞나
    usage = load_usage(P)
    day = today_pt()
    m26 = usage[day][M26]
    assert m26["in"] == 4500, f"in 합산 불일치: {m26['in']}"
    assert m26["out"] == 1900, f"out 합산 불일치: {m26['out']}"
    assert abs(m26["sec"] - 7.0) < 1e-9, f"sec 합산 불일치: {m26['sec']}"
    print(f"[3] in/out/sec 합산 ✓ (26B: in={m26['in']}, out={m26['out']}, sec={m26['sec']})")

    # 4) 두 모델이 같은 날짜 아래 따로 쌓이나(섞이지 않나)
    assert set(usage[day].keys()) == {M26, M31}, "모델 분리 실패"
    assert usage[day][M31]["calls"] == 1, "31B 항목 오염"
    print("[4] 모델별 분리 ✓ (같은 날짜 아래 26B/31B 독립)")

    # 5) 디스크에서 다시 읽어도 그대로(재시작 비손실)
    reloaded = load_usage(P)
    assert reloaded == usage, "디스크 재읽기 불일치"
    print("[5] 디스크 재읽기 일치 ✓ (재시작 비손실)")

    print("\n=== 전체 통과 ✓ ===")
    print("    (날짜 키는 PT 기준:", day, "— RPD 리셋 경계와 동일)")

    shutil.rmtree(TEST_DIR, ignore_errors=True)
