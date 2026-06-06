# scripter.py
# ④' 입력 대본 생성 단계 (H4_RUN 길B). 대화형 CLI에 흘릴 stdin 시퀀스를 만든다.
#
# 배경(FINDINGS): 무료 모델은 작은 CLI를 input() 메뉴루프로 짜는데, runner가 stdin=EOF만 주면
#   메뉴 첫 프롬프트에서 EOFError로 다 죽어(메뉴앞EOF) '메뉴 너머' 파일 간 동작(H1b)을 못 본다.
#   H2 길1(a)의 고정 더미(DUMMY_STDIN)는 메뉴 구조가 다르면 헛입력이라 한계였다(§10).
#   길B: acceptance(의도) + ★생성된 코드의 실제 프롬프트★를 보고 그 프로그램에 맞는 대본을 만들어
#   메뉴를 실제로 넘긴다. 설계만 보면 안 되는 이유 — 메뉴 프롬프트 문자열은 coder가 지어내며 설계엔 없음(§10).
#
#   [h4b_1 관측 → 개선] 1회차에서 B·C가 여전히 EOFError: 대본은 생성·주입됐으나 (1)액션 하위입력이
#   모자라거나 (2)루프를 끝내는 종료옵션을 못 골라 굶어 죽었다. → 프롬프트를 "코드 줄단위 추적 +
#   하위입력 타입 맞춰 전부 + 종료옵션 찾아 끝에 여러 번 패딩"으로 강화(아래 _SCRIPTER_INSTRUCTION).
#
# ★ §2-3 보존: 이 단계는 measurement(측정장치) 쪽이다.
#   - expected_type(난이도 A~E)을 안 본다(design·codes에 애초에 없음).
#   - 출력(stdin 대본)은 runner의 표준입력으로만 가고, planner/coder로 절대 되돌아가지 않는다.
#   - 코드 생성이 끝난 뒤(이미 굳은 산출물)를 '읽기만' 한다 — 모델의 코딩 행동에 개입하지 않는다.
#   - call_model 단일 입구를 거치므로 usage·limiter·backoff가 그대로 적용된다.
#
# 실패하면 빈 문자열("")을 돌려준다 — run.py가 `or stdin_input`으로 받아 DUMMY_STDIN fallback,
# 그래도 안 먹으면 timeout 20s가 받친다(이중 안전망). 즉 '있으면 더 본다'지 필수 의존이 아니다.

import re

# 입력 대본 생성은 '구조 해석' 작업 → 설계 담당과 같은 26B(코더 31B 연타 경로와 분리, §8).
_M26 = "gemini-3.5-flash"

_SCRIPTER_INSTRUCTION = """\
You are given a small multi-file Python program and its acceptance criteria.
It is interactive: it reads stdin via input() calls, usually a menu loop.
Produce the exact sequence of stdin lines that drives it through one or two MAIN
features and then makes it EXIT cleanly.

READ THE CODE AND TRACE EXECUTION LINE BY LINE. Rules:
- Output ONLY raw input lines, one per line. No prose, comments, numbering, markdown, backticks, or quotes.
- Match each input() in order. If a value is parsed (int(input()), float(input())), give a valid NUMBER.
  Give realistic text where text is expected.
- For every menu action you select, supply EVERY follow-up input that action requests
  before it returns to the menu. Do not stop in the middle of an action.
- Find the menu choice that ENDS the program (breaks the loop / returns from main / sys.exit) and select it.
- IMPORTANT: end the script by repeating that EXIT choice on 3 separate lines, then 2 empty lines,
  so the program terminates even if it loops more times than you expect.
- Keep the useful part focused: about 6 to 16 lines before the exit padding.
"""


def _clean(text: str) -> str:
    """모델 응답에서 대본만 남긴다. 코드펜스로 감싸 오면 안쪽만, 아니면 그대로.
    (입력 줄을 지울 위험이 있어 과한 정제는 안 한다 — 못 쓰면 어차피 ""→fallback.)"""
    s = (text or "").strip()
    fence = re.search(r"```(?:\w+)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    return s


def _pack_codes(codes: dict, *, per_file: int = 2000, total: int = 6000) -> str:
    """생성된 파일들을 '파일명 + 코드'로 이어붙인다(너무 길면 잘라 토큰 보호)."""
    parts, used = [], 0
    for name, code in (codes or {}).items():
        code = code or ""
        chunk = f"===== {name} =====\n{code[:per_file]}\n"
        if used + len(chunk) > total:
            break
        parts.append(chunk)
        used += len(chunk)
    return "".join(parts)


def make_input(design: dict, codes: dict, *, limiter, max_retries: int = 2) -> str:
    """생성된 코드의 실제 프롬프트 + acceptance를 보고 stdin 대본을 만든다.

    design: 설계 JSON(여기선 entry_point·acceptance_criteria만 쓴다 — expected_type 없음).
    codes:  {파일명: 코드문자열} 생성 결과(실제 메뉴 프롬프트가 여기 있다).
    반환:   개행으로 끝나는 stdin 문자열. 못 만들면 "" (caller가 fallback).

    ★ stdin이 무의미한 코드는 호출 자체를 건너뛴다:
      어느 파일에도 input(이 없으면 대화형이 아님(argparse/데모형) → stdin 무력(§10). "" 반환.
    """
    blob = _pack_codes(codes)
    if "input(" not in blob:
        return ""   # 대화형 아님 — stdin 줘봐야 헛것(§10 argparse·데모). 호출 절약.

    from client import call_model   # 단일 입구(usage·limiter 한 곳). 함수 안 import로 순환 회피.

    entry = (design or {}).get("entry_point") or "main.py"
    criteria = (design or {}).get("acceptance_criteria") or []
    crit_text = "\n".join(f"- {c}" for c in criteria) if criteria else "- (none given)"

    prompt = (
        _SCRIPTER_INSTRUCTION
        + f"\nENTRY POINT: {entry}\n"
        + f"\nACCEPTANCE CRITERIA:\n{crit_text}\n"
        + f"\nPROGRAM FILES:\n{blob}\n"
    )

    for _ in range(max_retries + 1):
        r = call_model(_M26, prompt, limiter=limiter)
        if r["truncated"]:
            continue   # 잘렸으면 대본 불완전 → 재시도
        script = _clean(r["text"])
        if script:
            return script if script.endswith("\n") else script + "\n"
    return ""   # 끝내 못 만들면 fallback에 맡긴다


# ======================================================================
# 단독 테스트: python3 scripter.py
#   [0] 키 없이: 코드펜스 정제 + 비대화형(input 없음) 건너뛰기 확인.
#   [1~2] 키 있으면 실호출 1회 — 메뉴형 가짜 프로그램에 대본이 메뉴를 넘겨 종료까지 가나 본다.
# ======================================================================
if __name__ == "__main__":
    import os

    print("=== scripter.py 단독 테스트 ===\n")

    assert _clean("```\n1\nhi\n0\n```") == "1\nhi\n0", "_clean 펜스 제거 실패"
    assert make_input({}, {"main.py": "import argparse\nargparse.ArgumentParser()"},
                      limiter=None) == "", "argparse(=input 없음)는 ''여야"
    print("[0] 정제·비대화형 건너뛰기 ✓ (키 불필요)\n")

    if not os.environ.get("GOOGLE_API_KEY"):
        print("[!] GOOGLE_API_KEY 없음 — 실호출 테스트는 건너뜀. 위 [0]만 통과.")
        raise SystemExit(0)

    from limiter import Limiter
    lim = Limiter(rpm=15, rpd_limit=1450)

    fake_design = {"entry_point": "main.py",
                   "acceptance_criteria": ["할 일을 추가할 수 있다", "목록을 볼 수 있다"]}
    fake_codes = {"main.py":
        "while True:\n"
        "    print('1.add 2.list 3.quit')\n"
        "    c = input('choice: ')\n"
        "    if c == '1':\n"
        "        t = input('task: '); print('added', t)\n"
        "    elif c == '2':\n"
        "        print('LIST')\n"
        "    elif c == '3':\n"
        "        break\n"}

    print("[1] 26B에 대본 요청…")
    script = make_input(fake_design, fake_codes, limiter=lim)
    print("[1] 수신 ✓\n")
    print("[2] 생성된 stdin 대본:")
    print(repr(script))
    assert script.endswith("\n"), "개행으로 끝나야(마지막 input 전달)"
    print("\n=== 통과 ✓ === (대본 끝에 종료옵션 '3'이 여러 번 들어가 메뉴를 넘겨 끝나면 길B가 먹는다)")
