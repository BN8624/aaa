# probe_endpoints.py
# 같은 VERTEX_API_KEY로 두 서비스를 각각 1번씩 때려 어느 quota가 막혔는지 가른다.
#   - generativelanguage.googleapis.com  (AI Studio / Gemini API — 대시보드에서 보는 RPM1k/TPM2M/RPD10k)
#   - aiplatform.googleapis.com          (Vertex AI — client.py가 실제로 때리는 곳)
# 출력: 각 엔드포인트의 HTTP 상태코드 + 본문 앞부분(quota metric 있으면 같이). 키는 안 찍는다.
#
# 사용: export VERTEX_API_KEY="..."  후  python probe_endpoints.py
#
# 해석:
#   genlang=200, aiplatform=429  → 엔드포인트가 범인. client.py _BASE를 genlang으로.
#   둘 다 429                    → 일일/프로젝트 quota 실제 소진. 콘솔 확인/리셋/증액.
#   둘 다 200                    → 그 시점만 일시적(공유 quota 혼잡). backoff로 충분, 재개.

import os
import json
import urllib.request
import urllib.error

MODEL = "gemini-3.5-flash"
KEY = os.environ.get("VERTEX_API_KEY")

ENDPOINTS = {
    "generativelanguage (AI Studio)":
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
    "aiplatform (Vertex, 현재 코드)":
        f"https://aiplatform.googleapis.com/v1/publishers/google/models/{MODEL}:generateContent",
}

BODY = json.dumps({
    "contents": [{"role": "user", "parts": [{"text": "Reply with just: ok"}]}],
    "generationConfig": {"maxOutputTokens": 16, "temperature": 0},
}).encode("utf-8")


def probe(name, base):
    url = f"{base}?key={KEY}"
    req = urllib.request.Request(
        url, data=BODY,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        cands = data.get("candidates") or []
        txt = ""
        if cands:
            parts = (cands[0].get("content") or {}).get("parts") or []
            txt = "".join(p.get("text", "") for p in parts if "text" in p)
        print(f"[{name}] HTTP 200  finish={cands[0].get('finishReason') if cands else None}  text={txt[:40]!r}")
    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8")
        except Exception:
            err = ""
        # quota metric/violation이 있으면 뽑아본다
        detail = ""
        try:
            ej = json.loads(err)
            for d in (ej.get("error", {}).get("details") or []):
                if "violations" in d or "quotaMetric" in json.dumps(d):
                    detail = " | " + json.dumps(d, ensure_ascii=False)[:300]
        except Exception:
            pass
        retry_after = e.headers.get("Retry-After") if e.headers else None
        print(f"[{name}] HTTP {e.code}  Retry-After={retry_after}  body={err[:200]}{detail}")
    except Exception as e:
        print(f"[{name}] ERROR {type(e).__name__}: {e}")


if __name__ == "__main__":
    if not KEY:
        raise SystemExit("VERTEX_API_KEY 없음. export VERTEX_API_KEY=... 먼저.")
    print(f"=== probe (model={MODEL}) ===")
    for name, base in ENDPOINTS.items():
        probe(name, base)
