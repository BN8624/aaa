# probe_quota.py
# Vertex(aiplatform) 엔드포인트에 작은 호출을 빠르게 연사해 quota 한도를 건드리고,
# 429 응답 본문에서 "막힌 metric 이름 + 한도값 + Retry-After"를 그대로 찍는다.
# 콘솔을 못 볼 때 한도를 경험적으로 확인하는 용도.
#
# 토큰 최소(maxOutputTokens=16)라 '요청 횟수(RPM)' 차원만 건드린다(토큰 차원 격리).
#
# 사용:  export VERTEX_API_KEY="..."
#        python probe_quota.py [최대콜수=80]
#
# 해석:
#   429 나옴   → body의 metric/limit이 진짜 한도. Retry-After도 같이.
#   429 안 나옴 → 한도 ≥ (성공수)/창. h4_12 429는 고정 RPM 아니라 공유quota(DSQ) 순간 혼잡
#                 → 고정 숫자 쫓을 것 없이 §13 backoff로 충분. /연속도커만 끊어 돌리면 됨.

import os
import sys
import json
import time
import urllib.request
import urllib.error

MODEL = "gemini-3.5-flash"
KEY = os.environ.get("VERTEX_API_KEY")
BASE = f"https://aiplatform.googleapis.com/v1/publishers/google/models/{MODEL}:generateContent"
MAX_CALLS = int(sys.argv[1]) if len(sys.argv) > 1 else 80

BODY = json.dumps({
    "contents": [{"role": "user", "parts": [{"text": "ok"}]}],
    "generationConfig": {"maxOutputTokens": 16, "temperature": 0},
}).encode("utf-8")


def dump_429(e, err_body, n_ok, elapsed):
    print(f"\n*** 429 at call #{n_ok+1} (성공 {n_ok}건 / {elapsed:.1f}s 만에) ***")
    retry_after = e.headers.get("Retry-After") if e.headers else None
    print(f"Retry-After: {retry_after}")
    print("--- full body ---")
    print(err_body)
    # error.details에서 QuotaFailure / metric / limit 뽑기
    try:
        ej = json.loads(err_body)
        details = ej.get("error", {}).get("details") or []
        for d in details:
            t = d.get("@type", "")
            if "QuotaFailure" in t:
                for v in d.get("violations", []):
                    print(f"  >> metric : {v.get('quotaMetric') or v.get('subject')}")
                    print(f"  >> limit  : {v.get('quotaValue') or v.get('description')}")
                    print(f"  >> id     : {v.get('quotaId')}")
            elif "Help" in t:
                for ln in d.get("links", []):
                    print(f"  >> help   : {ln.get('url')}")
    except Exception as ex:
        print(f"(detail 파싱 실패: {ex})")


def main():
    if not KEY:
        raise SystemExit("VERTEX_API_KEY 없음. export VERTEX_API_KEY=... 먼저.")
    url = f"{BASE}?key={KEY}"
    print(f"=== quota probe: {MODEL} 에 최대 {MAX_CALLS}콜 연사 ===")
    t0 = time.time()
    n_ok = 0
    for i in range(MAX_CALLS):
        req = urllib.request.Request(
            url, data=BODY,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
            n_ok += 1
            if n_ok % 10 == 0:
                print(f"  ... {n_ok} OK ({time.time()-t0:.1f}s)")
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                err_body = ""
            if e.code == 429 or "RESOURCE_EXHAUSTED" in err_body:
                dump_429(e, err_body, n_ok, time.time() - t0)
                return
            print(f"\n[비-429 HTTP {e.code}] {err_body[:300]}")
            return
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {e}")
            return
    print(f"\n=== {MAX_CALLS}콜 전부 통과 ({time.time()-t0:.1f}s), 429 없음 ===")
    print(f"→ per-minute 요청 한도 ≥ {MAX_CALLS} (이 창에서). h4_12 429는 고정 RPM 아닌")
    print("  공유quota(DSQ) 순간 혼잡으로 추정 → 고정 숫자 불필요, §13 backoff로 충분.")


if __name__ == "__main__":
    main()
