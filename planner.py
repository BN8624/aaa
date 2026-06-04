# planner.py
# ① 설계 단계(work_unified 4·5장). 26B에게 요구사항을 주고
#    "파일 구조 + 각 파일 역할 + 시그니처(provides) + 데이터 계약(input/output_schema)
#     + assumptions + acceptance_criteria"를 JSON으로 받는다.
#
# 이 단계가 H1a의 원재료(designed_files)를 만든다 — planner가 의도한 결합도를
# '설계'하는가를 나중에 보려면, 여기서 나온 files의 name들이 그대로 증거가 된다.
#
# ★★ H1_RUN §2의 절대 규칙이 여기서 처음 실전으로 걸린다:
#   [§2-3] expected_type(난이도 A~E)을 프롬프트에 절대 넣지 않는다.
#          난이도를 알면 모델이 실험에 적응한다 → 요구사항 텍스트'만' 준다.
#          expected_type은 TaskState에만 기록하고 여기선 안 쓴다(인자로도 안 받는다).
#
# ★ H1_RUN §1: review_design(AI 설계 검문)은 만들지 않는다. 설계 JSON 생성까지가 v0.
#   ①.5 검문소는 0단계 로그가 "실패가 H1a에 몰린다"를 보여줄 때 켠다(호명될 때).
#
# 5장 상한선: provides의 schema는 "데이터가 어떻게 생겼나"(Data Contract)만.
#   도메인 로직·구현 규칙은 JSON에 넣지 않는다(JSON을 DSL로 만들지 않기).

import json
import re


# 26B에게 주는 설계 지시. "구조만, JSON만, 백틱 금지"를 박아 파싱을 안정시킨다(5장).
# expected_type은 이 어디에도 없다 — 의도적이다(§2-3).
_PLANNER_INSTRUCTION = """\
You are a software architect. Given a requirement, design a multi-file Python program.

Output ONLY a JSON object. No markdown, no backticks, no prose before or after.

The JSON must have exactly this shape:
{
  "assumptions": ["..."],
  "files": [
    {
      "name": "xxx.py",
      "role": "what this file is responsible for",
      "provides": [
        {"sig": "func_name(args)", "input_schema": "shape of inputs", "output_schema": "shape of output"}
      ],
      "depends_on": ["other_file.py"]
    }
  ],
  "entry_point": "main.py",
  "acceptance_criteria": ["..."]
}

Rules:
- Split the program into separate files by responsibility. Define clear interfaces between them.
- "provides" lists the functions each file exposes, with input_schema/output_schema describing
  the SHAPE of the data (e.g. "list[ {text:str, done:bool} ]", "(str, int)", "bool").
  Describe data shape ONLY. Do NOT put domain logic, algorithms, or implementation rules in the schema.
- "depends_on" lists which other files this file imports.
- "assumptions": if the requirement is unclear, do NOT invent extra features. State the assumptions
  you made here so a human can see them. Add NO functionality that was not requested.
- "acceptance_criteria": what the program must achieve, in plain statements.
- Output the JSON and nothing else.

Requirement:
"""


def _extract_json(text: str) -> dict:
    """모델 응답에서 JSON을 방어적으로 추출한다.
    '백틱 금지'를 지시해도 모델이 ```json ... ```로 감싸 오는 경우가 흔하므로,
    1) 그대로 파싱 시도 → 2) 코드펜스 벗겨 재시도 → 3) 첫 '{'~마지막 '}' 구간 파싱.
    셋 다 실패하면 ValueError(상위가 재요청).
    """
    s = text.strip()

    # 1) 그대로
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # 2) ```json ... ``` 또는 ``` ... ``` 코드펜스 제거
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        inner = fence.group(1).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            pass

    # 3) 첫 '{'부터 마지막 '}'까지 — 앞뒤 잡소리가 붙은 경우
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        chunk = s[start:end + 1]
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            pass

    raise ValueError("설계 JSON 파싱 실패: 모델 응답에서 유효한 JSON을 못 찾음")


def make_design(requirement: str, *, limiter, max_retries: int = 2) -> dict:
    """① 26B에게 요구사항을 주고 설계 JSON을 받는다.

    requirement: 사용자 요구사항 텍스트. ★ 이게 전부다 — expected_type은 받지도, 넣지도 않는다(§2-3).
    limiter: 토대 Limiter(한도 슬롯).
    max_retries: JSON 파싱 실패·잘림(truncated) 시 재요청 횟수.

    반환: 설계 JSON dict(assumptions·files·entry_point·acceptance_criteria).
    파싱이 끝내 안 되면 마지막 예외를 올린다(상위가 사람에게 보고).
    """
    # 단일 입구 call_model만 거친다(한도·usage가 한 곳에서). 26B = 설계 담당(3장).
    from client import call_model

    M26 = "gemma-4-26b-a4b-it"
    prompt = _PLANNER_INSTRUCTION + requirement.strip() + "\n"

    last_err = None
    for _ in range(max_retries + 1):
        r = call_model(M26, prompt, limiter=limiter)

        # 잘렸으면(thinking이 예산 다 먹음 등 — 3장 함정1) 설계가 불완전 → 재요청
        if r["truncated"]:
            last_err = ValueError("설계 응답이 잘림(truncated=MAX_TOKENS) — 재요청")
            continue

        try:
            design = _extract_json(r["text"])
        except ValueError as e:
            last_err = e
            continue

        # 최소 형태 검증: files가 리스트로 있고 비어있지 않은가(빈 껍데기 방지).
        # ※ 여기서 "설계가 좋은가"를 판정하지 않는다(그건 AI 판정 = v0 밖, §1).
        #   단지 다음 단계(coder)가 읽을 수 있는 모양인지 최소 확인만.
        if not isinstance(design.get("files"), list) or not design["files"]:
            last_err = ValueError("설계 JSON에 files 배열이 없거나 비어 있음")
            continue

        return design

    raise last_err if last_err else ValueError("설계 생성 실패")


# ======================================================================
# 단독 테스트: python3 planner.py
# ★ 실호출 1회(GOOGLE_API_KEY 필요). 간단한 요구사항으로 설계 JSON이 제대로 나오나만 본다.
#   - files/provides/input_schema/assumptions가 채워졌나
#   - depends_on이 있나(파일 간 관계를 설계했나)
#   ※ "설계 품질"은 판정하지 않는다(v0는 관측만). 구조가 나오는지만 확인.
# ======================================================================
if __name__ == "__main__":
    import os
    from limiter import Limiter

    print("=== planner.py 설계 JSON 단독 테스트 ===\n")

    if not os.environ.get("GOOGLE_API_KEY"):
        print("✗ GOOGLE_API_KEY가 없다. .bashrc에 export 했는지 확인.")
        raise SystemExit(1)

    lim = Limiter(rpm=15, rpd_limit=1450)
    req = "간단한 CLI 할일 관리. 추가/삭제/완료/목록 4기능. 저장은 로컬 파일."

    print(f"[요구사항] {req}\n")
    print("[1] 26B에 설계 요청…(thinking high라 십수 초 걸릴 수 있음)")
    design = make_design(req, limiter=lim)
    print("[1] 설계 JSON 수신·파싱 ✓\n")

    # --- 구조 확인(판정 아님, 모양만) ---
    assert isinstance(design.get("files"), list) and design["files"], "files 없음"
    names = [f.get("name") for f in design["files"]]
    print(f"[2] 설계된 파일({len(names)}): {names}")

    # provides에 시그니처+스키마가 있나(최소 한 파일이라도)
    has_schema = False
    for f in design["files"]:
        for p in f.get("provides", []):
            if "sig" in p and "input_schema" in p and "output_schema" in p:
                has_schema = True
                break
        if has_schema:
            break
    assert has_schema, "provides에 sig+input_schema+output_schema가 안 보임"
    print("[3] provides에 시그니처+데이터계약(input/output_schema) ✓")

    # depends_on이 어디라도 채워졌나(파일 간 관계 설계 여부 — 빈 리스트여도 키는 있어야)
    has_depends_key = all("depends_on" in f for f in design["files"])
    assert has_depends_key, "일부 파일에 depends_on 키가 없음"
    deps = {f["name"]: f.get("depends_on", []) for f in design["files"]}
    print(f"[4] depends_on 관계: {deps}")

    # assumptions / entry_point / acceptance_criteria 존재
    print(f"[5] assumptions({len(design.get('assumptions', []))}개): {design.get('assumptions')}")
    print(f"    entry_point: {design.get('entry_point')}")
    print(f"    acceptance_criteria({len(design.get('acceptance_criteria', []))}개)")

    print("\n=== 전체 통과 ✓ ===")
    print("    (expected_type은 프롬프트에 넣지 않았다 — 난이도 숨김 §2-3)")
    print("\n--- 설계 JSON 전문(눈으로 확인용) ---")
    print(json.dumps(design, ensure_ascii=False, indent=2))
