# util.py
# 여러 토대 파일(state·usage·limiter)이 함께 의존하는 공통 함수 모음.
# "진실의 출처가 하나"여야 하는 것들만 여기 둔다 — 특히 PT 날짜 경계.
#
# 왜 PT인가(work_unified 6·11장):
#   무료 티어 RPD(하루 호출 상한)가 PT(태평양시) 자정에 리셋된다.
#   usage 누적·RPD 체크·runs.jsonl의 created_at이 모두 같은 날짜 경계를 봐야
#   카운터가 어긋나지 않는다. 그래서 날짜 함수를 한 곳에 두고 다 같이 쓴다.
#   (이걸 파일마다 복붙하면, 나중에 경계를 손볼 때 한쪽만 고치는 사고가 난다.)

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta

# PT = UTC-8 고정. 서머타임(DST)은 가능성 단계에선 무시한다 —
# 날짜 경계의 "정합성"(usage·RPD·created_at이 같은 기준)만 맞으면 되고,
# DST로 한 시간 어긋나는 건 하루 한 번 리셋 경계에서나 문제라 지금은 과한 정밀도.
# 필요해지면 zoneinfo("America/Los_Angeles")로 바꾼다(그때 한 줄).
PT = timezone(timedelta(hours=-8))


def now_pt() -> datetime:
    """현재 시각을 PT 기준 datetime으로. (날짜 키 계산·경과시간 등)"""
    return datetime.now(PT)


def now_pt_iso() -> str:
    """현재 시각을 PT 기준 ISO 문자열로. created_at 등 '사실' 기록에 쓴다."""
    return now_pt().isoformat()


def today_pt() -> str:
    """오늘 날짜를 PT 기준 'YYYY-MM-DD'로. usage.json·RPD 체크의 날짜 키."""
    return now_pt().strftime("%Y-%m-%d")


def atomic_write_json(path: str, data) -> None:
    """data를 JSON으로 path에 '원자적으로' 저장.
    임시파일에 다 쓴 뒤 os.replace로 교체 — 쓰다 죽어도 기존 파일이 반쪽으로 안 깨진다.
    state.save()·usage 저장이 공유한다(둘 다 '즉시·안전 저장'이 필요).
    """
    d = os.path.dirname(path) or "."
    # 같은 디렉터리에 임시파일을 둬야 rename이 원자적(파일시스템 경계를 넘으면 보장 안 됨)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())   # 디스크에 실제로 내려쓰게 강제
        os.replace(tmp, path)      # 원자적 교체
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
