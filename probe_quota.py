# probe_quota.py
# Vertex(aiplatform) 엔드포인트에 작은 호출을 빠르게 연사해 quota 한도를 건드리고,
# 429 응답 본문에서 "막힌 metric 이름 + 한도값 + Retry-After"를 그대로 찍는다.
# 콘솔을 못 볼 때 한도를 경험적으로 확인하는 용도.
#
# 토큰 최소(maxOutputTokens=16)라 '요청 횟수(RPM)' 차원만 건드린다(토큰 차원 격리).
#
# 사용:  export VERTEX_API_KEY="..."
#        python probe_quota.py [최대콜수=80] [콜간격초=0]
#
#   콜간격초=0  → 연사(버스트 한도만 건드림). "성공 N건"은 콜당 지연 누적일 뿐,
#                 분당 지속 한도는 말해주지 않음(FINDINGS §28의 약한 고리).
#   콜간격초>0  → 그 간격으로 페이싱. run.py의 min_interval(현재 4.0)을 그대로 넣어
#                 "이 페이싱이면 429 안 나는가"를 직접 검증한다.
#
# 해석(★ B 검증):
#   `python probe_quota.py 20 4` 처럼 돌려서 —
#     20콜 다 통과 → min_interval=4.0이 버스트를 끊는다(=버스트 가설). B 정당.
#     여전히 ~6에서 429 → 분당 고정 저(低)캡 → rpm을 ≤5로 더 낮추거나 정식 Vertex 인증(C안).
#   429 본문에 metric/limit 있으면 그게 진짜 한도(Retry-After도). 없으면(generic) 경험값이 전부.

import sys
import json
import time
import urllib.request
import urllib.error

import client  # 인증 경로(SA OAuth ↔ express API키)를 그대로 재사용 — §30

MODEL = "gemini-3.5-flash"
MAX_CALLS = int(sys.argv[1]) if len(sys.argv) > 1 else 80
INTERVAL = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0  # 콜 간 sleep(초). 0=연사.

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
    # 인증 경로는 client가 환경변수로 자동 선택(SA 3종 있으면 OAuth, 없으면 express 키).
    auth = "SA OAuth(정식)" if client.os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") \
        and client.os.environ.get("VERTEX_PROJECT") and client.os.environ.get("VERTEX_LOCATION") \
        else "express API키"
    mode = f"{INTERVAL}초 간격 페이싱" if INTERVAL > 0 else "연사(간격 0)"
    print(f"=== quota probe: {MODEL} / {auth} / 최대 {MAX_CALLS}콜 / {mode} ===")
    t0 = time.time()
    n_ok = 0
    for i in range(MAX_CALLS):
        if INTERVAL > 0 and i > 0:
            time.sleep(INTERVAL)
        url, headers = client._endpoint_and_headers(MODEL)
        req = urllib.request.Request(
            url, data=BODY, headers=headers, method="POST",
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
    if INTERVAL > 0:
        print(f"→ {INTERVAL}초 간격이면 {MAX_CALLS}콜까지 429 없음. **이 페이싱이 버스트를 끊는다(B 검증).**")
        print(f"  run.py min_interval={INTERVAL}로 회차 돌려도 안전하다는 직접 근거. → h4_16 진행 OK.")
    else:
        print(f"→ per-minute 요청 한도 ≥ {MAX_CALLS} (이 창에서). h4_12 429는 고정 RPM 아닌")
        print("  공유quota(DSQ) 순간 혼잡으로 추정 → 고정 숫자 불필요, §13 backoff로 충분.")


if __name__ == "__main__":
    main()
