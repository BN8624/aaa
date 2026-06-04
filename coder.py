# coder.py
# ② 코딩 단계(work_unified 4·5장). 확정된 설계 JSON을 받아 파일별로 코드를 생성한다(31B).
#
# ★★ 이 프로젝트의 급소가 여기 있다 — 컨텍스트 관리(5장).
#   파일 B를 짤 때 다른 파일들의 '전체 코드'가 아니라 'provides(시그니처 + input/output_schema)'만 준다.
#   비유: 동료 코드를 다 읽는 게 아니라 API 문서만 보고 짜는 것.
#   이유: 멀티파일 정합성의 약점이 '긴 입력에서 놓치기'인데, 시그니처만 넣으면 입력이 짧게 유지돼
#         그 약점을 정면 회피한다. 파일 수십 개여도 시그니처 몇 줄이면 된다.
#
# ★ H1_RUN §2-4: "가능하면 타입 힌트" 권장만. 강제 금지.
#   강제하면 H1이 "설계 JSON + 강한 타입 규율"이라는 다른 실험으로 바뀌고,
#   소형 모델은 로직을 형식 코드로 밀어낸다. 타입힌트는 자연 발생량을 '관측'만 한다.
#
# 이 단계가 H1b의 원재료(generated_files)를 만든다 — coder가 설계된 결합도를 코드에서
# '유지'하는가(designed_files ↔ generated_files 대조)를 나중에 본다.
#
# 순차 생성(H1_RUN: depends_on 순서대로 한 파일씩). 병렬은 한도 슬롯 경쟁만 늘려 가능성 단계엔 불필요.

import re


def _topo_order(files: list) -> list:
    """files를 depends_on 위상정렬해 '의존 대상이 먼저' 오도록 정렬한 리스트로.
    (코더는 의존 파일의 '스키마'만 받으므로 순서가 정합성에 큰 영향은 없으나,
     의존 순으로 짜는 게 자연스럽고 디버깅도 읽기 쉽다.)
    순환이 있거나 못 푸는 건 원래 순서 뒤에 그냥 붙인다(여기서 설계를 판정하지 않는다 — v0).
    """
    by_name = {f["name"]: f for f in files}
    done = []
    done_set = set()

    def visit(f, stack):
        name = f["name"]
        if name in done_set:
            return
        if name in stack:
            # 순환 — 여기서 막지 않고(판정 아님) 그냥 진행. 순환이면 도커에서 드러난다.
            return
        stack = stack | {name}
        for dep in f.get("depends_on", []):
            if dep in by_name:
                visit(by_name[dep], stack)
        if name not in done_set:
            done.append(f)
            done_set.add(name)

    for f in files:
        visit(f, set())
    return done


def build_context(target_file: dict, design: dict) -> str:
    """target을 짤 때 31B에게 줄 컨텍스트 문자열.
    담는 것: target의 name·role·provides(구현할 것)
            + depends_on에 적힌 다른 파일들의 provides(시그니처 + input/output_schema만! 코드 아님)
            + entry_point 여부.
    ★ 스키마까지 줘야 데이터 계약 불일치(list[dict] vs list[Task] 같은)를 코더가 보고 이을 수 있다(5장).
    """
    by_name = {f["name"]: f for f in design["files"]}
    lines = []

    # 1) 의존 파일들의 인터페이스(시그니처 + 스키마)만 — 전체 코드 절대 안 넣는다
    deps = target_file.get("depends_on", [])
    if deps:
        lines.append("You may import from these other files. Here are their interfaces")
        lines.append("(signatures and data shapes ONLY — you do NOT see their code):\n")
        for dep in deps:
            dep_file = by_name.get(dep)
            if not dep_file:
                continue
            lines.append(f"# {dep} — {dep_file.get('role', '')}")
            for p in dep_file.get("provides", []):
                sig = p.get("sig", "")
                ins = p.get("input_schema", "")
                outs = p.get("output_schema", "")
                lines.append(f"  {sig}    # in: {ins}  -> out: {outs}")
            lines.append("")
    else:
        lines.append("This file has no dependencies on other files.\n")

    # 2) 이 파일이 제공해야 할 것(구현 대상)
    lines.append(f"You are writing: {target_file['name']}")
    lines.append(f"Role: {target_file.get('role', '')}")
    lines.append("This file MUST provide exactly these functions (match signatures and data shapes):")
    for p in target_file.get("provides", []):
        sig = p.get("sig", "")
        ins = p.get("input_schema", "")
        outs = p.get("output_schema", "")
        lines.append(f"  {sig}    # in: {ins}  -> out: {outs}")

    # 3) entry_point면 실행 진입점임을 알린다
    if target_file["name"] == design.get("entry_point"):
        lines.append(f"\nThis is the ENTRY POINT. It should run the program when executed "
                     f"(e.g. an `if __name__ == '__main__':` block calling the main flow).")

    return "\n".join(lines)


# 31B에게 주는 코딩 지시. 타입힌트는 '권장만'(§2-4). 코드만 내라고 박아 추출을 안정시킨다.
_CODER_INSTRUCTION = """\
You are an expert Python developer. Write the complete code for ONE file of a multi-file program.

Output ONLY the Python code for this file. No markdown fences, no explanation before or after.

Guidelines:
- Implement exactly the functions listed under "MUST provide", matching their signatures and data shapes.
- Import what you need from the other files using their interfaces shown above.
- Use type hints where natural/possible, but do not force them.
- Write working, runnable code — not stubs or placeholders.

"""


def _extract_code(text: str) -> str:
    """모델 응답에서 코드를 뽑는다. '코드만' 지시해도 ```python ... ```로 감싸 오는 경우가 흔하므로
    코드펜스가 있으면 그 안을, 없으면 응답 전체를 코드로 본다."""
    s = text.strip()
    fence = re.search(r"```(?:python|py)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        return fence.group(1).strip() + "\n"
    return s + "\n"


def code_one_file(target_file: dict, design: dict, *, limiter, max_retries: int = 2) -> str:
    """② 31B에게 build_context + '이 파일 코드를 완성하라'를 주고 코드를 받는다.
    반환: 파일 코드 문자열. truncated면 재요청(끝내 잘리면 마지막 부분코드라도 반환 — '큰 파일 쪼개기'는 13장).

    ※ feedback/dead_end 주입은 지금 안 켠다(§1 — 되돌림은 v0 밖). 깨끗한 1회 생성만 관측한다.
    """
    from client import call_model

    M31 = "gemma-4-31b-it"   # 코딩 담당(3장)
    context = build_context(target_file, design)
    prompt = _CODER_INSTRUCTION + context + "\n\nNow write the complete code for this file:\n"

    last_text = ""
    for _ in range(max_retries + 1):
        r = call_model(M31, prompt, limiter=limiter)
        last_text = r["text"]
        code = _extract_code(r["text"])
        # 잘리지 않았고 내용이 있으면 채택
        if not r["truncated"] and code.strip():
            return code
        # 잘렸으면 재요청(작은 파일이라 보통 한 번에 끝남)
    # 끝내 truncated거나 비었으면 마지막 받은 것이라도 코드로 반환(관측을 위해 — 판정 안 함)
    return _extract_code(last_text)


def coding_stage(design: dict, *, limiter) -> dict:
    """설계의 files 전체를 순차 코딩(depends_on 순). 반환: {파일명: 코드문자열}.
    이 dict가 generated_files가 되어 designed_files와 대조된다(H1b — 9.5장)."""
    ordered = _topo_order(design["files"])
    codes = {}
    for f in ordered:
        codes[f["name"]] = code_one_file(f, design, limiter=limiter)
    return codes


# ======================================================================
# 단독 테스트: python3 coder.py
# 두 부분:
#   (A) build_context — 키 없이. '다른 파일 전체 코드가 안 새고 시그니처만' 들어갔나(5장 급소 검증).
#   (B) coding_stage  — 실호출(키 필요). planner 설계로 코드가 파일 수만큼 나오나,
#                       각 파일이 자기 provides 함수를 실제 정의했나.
# ======================================================================
if __name__ == "__main__":
    import os
    import json

    # 테스트용 미니 설계(planner 출력과 같은 모양). build_context는 이걸로 키 없이 검증.
    DESIGN = {
        "assumptions": [],
        "files": [
            {"name": "storage.py", "role": "save/load todos to file",
             "provides": [
                 {"sig": "load_todos()", "input_schema": "None", "output_schema": "list[dict]"},
                 {"sig": "save_todos(todos)", "input_schema": "list[dict]", "output_schema": "None"},
             ],
             "depends_on": []},
            {"name": "todo.py", "role": "todo business logic",
             "provides": [
                 {"sig": "add_todo(todos, text)", "input_schema": "(list, str)", "output_schema": "list"},
             ],
             "depends_on": ["storage.py"]},
            {"name": "main.py", "role": "CLI entry",
             "provides": [{"sig": "main()", "input_schema": "None", "output_schema": "None"}],
             "depends_on": ["todo.py"]},
        ],
        "entry_point": "main.py",
        "acceptance_criteria": [],
    }

    print("=== coder.py 단독 테스트 ===\n")

    # ---------- (A) build_context: 시그니처만 새는지 (키 불요) ----------
    print("[A] build_context — 시그니처만 공유되나(5장 급소)")
    todo_file = next(f for f in DESIGN["files"] if f["name"] == "todo.py")
    ctx = build_context(todo_file, DESIGN)
    # storage.py의 '시그니처'는 있어야
    assert "load_todos()" in ctx and "save_todos(todos)" in ctx, "의존 파일 시그니처가 컨텍스트에 없음"
    # 데이터 스키마도 실려야(list[dict] 등)
    assert "list[dict]" in ctx, "input/output_schema가 컨텍스트에 없음"
    # 이 파일이 구현할 것도 있어야
    assert "add_todo(todos, text)" in ctx, "target provides가 컨텍스트에 없음"
    # 위상정렬 확인
    order = [f["name"] for f in _topo_order(DESIGN["files"])]
    assert order.index("storage.py") < order.index("todo.py") < order.index("main.py"), \
        f"위상정렬 순서 이상: {order}"
    print(f"    의존 파일 시그니처+스키마 포함 ✓ / 위상정렬: {order}")
    print("    --- todo.py용 컨텍스트(눈으로 확인) ---")
    print("    " + ctx.replace("\n", "\n    "))
    print("[A] 통과 ✓ (전체 코드가 아니라 시그니처만 들어감)\n")

    # ---------- (B) coding_stage: 실호출로 코드 생성 ----------
    if not os.environ.get("GOOGLE_API_KEY"):
        print("[B] 건너뜀 — GOOGLE_API_KEY 없음(build_context만 검증됨)")
        raise SystemExit(0)

    from limiter import Limiter
    lim = Limiter(rpm=15, rpd_limit=1450)

    print("[B] coding_stage — 3파일 순차 생성(31B, 각 십수 초)…")
    codes = coding_stage(DESIGN, limiter=lim)
    assert set(codes.keys()) == {"storage.py", "todo.py", "main.py"}, f"생성 파일 불일치: {list(codes)}"
    print(f"    생성된 파일: {list(codes.keys())}")

    # 각 파일이 자기 provides 함수를 def 했나(문자열 'def 함수명' 존재로 최소 확인)
    assert "def load_todos" in codes["storage.py"], "storage.py에 load_todos 정의 없음"
    assert "def save_todos" in codes["storage.py"], "storage.py에 save_todos 정의 없음"
    assert "def add_todo" in codes["todo.py"], "todo.py에 add_todo 정의 없음"
    assert "def main" in codes["main.py"], "main.py에 main 정의 없음"
    print("    각 파일이 자기 provides 함수를 정의함 ✓")

    # 각 파일이 파이썬으로 파싱되나(문법 OK)
    import ast
    for name, code in codes.items():
        try:
            ast.parse(code)
            print(f"    {name}: 문법 OK ({len(code)}자)")
        except SyntaxError as e:
            print(f"    {name}: ✗ 문법 에러 {e}  ← H1b 관측 지점(코더가 깨뜨림)")

    print("\n=== 통과 ✓ ===")
    print("    (시그니처만 공유로 코드 생성. dict↔객체 경계를 코더가 어떻게 이었는지는 도커 실측에서 본다)")
    print("\n--- 생성 코드 전문(눈으로 확인용) ---")
    for name, code in codes.items():
        print(f"\n##### {name} #####")
        print(code)
