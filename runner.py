# runner.py
# ④ 실측 실행(work_unified 7장). 생성된 멀티파일 프로그램을 실제로 돌려
#    exit_code / stdout / stderr / runtime을 받는다. 이게 자동 디버깅의 연료다.
#
# ★ H1_RUN §1: 격리 Docker가 아니다. 지금 runner는 그냥 subprocess 실행만.
#   (안전 격리 Docker는 v0 밖 — 작은 파이썬 프로그램을 VM에서 직접 돌린다.)
#   work_unified 7장 블랙박스 계약의 입출력 dict 모양은 지키되, 알맹이는 subprocess다.
#   도커 본문은 나중에 이 계약을 유지한 채 갈아끼운다.
#
# stdin 처리(이번 결정): stdin을 빈 것(EOF)으로 준다.
#   → main.py의 input()이 EOFError를 받고 끝난다. "입력 없이 어떻게 반응하나"가 stderr에 남는다(관측).
#   timeout은 그래도 둔다 — EOFError를 무시하고 도는 무한루프 방어(이중 안전망).
#
# 멀티파일을 임시 폴더에 다 풀고 entry_point를 실행한다.
#   → 'from todo import add_todo' 같은 파일 간 import가 실제로 맞물리는지가 런타임에서 검증된다(H1b).

import os
import sys
import shutil
import tempfile
import subprocess


def run_in_subprocess(codes: dict, entry_point: str, *, timeout: int = 20,
                      stdin_input: str = None) -> dict:
    """생성 파일들을 임시 폴더에 쓰고 entry_point를 subprocess로 실행, 결과 실측 반환.

    [입력]
      codes:       {파일명: 코드문자열}  (coder 출력)
      entry_point: 실행 시작 파일 (설계 JSON의 entry_point, 예 'main.py')
      timeout:     실행 제한 시간(초). input 대기/무한루프 방어.
      stdin_input: subprocess에 흘릴 표준입력 문자열(H2_RUN 길1). 기본 None=종전대로 EOF(DEVNULL).
                   값을 주면 그 문자열을 stdin으로 주입 → 대화형 CLI가 메뉴를 통과하는지 실측.

    [출력] dict (work_unified 7장 블랙박스 계약과 같은 모양):
      {
        "success":   bool,           # exit_code==0 이고 timed_out 아님 (※ '정상 동작' 보장은 아님 — looks_alive로 보강)
        "exit_code": int,
        "stdout":    str,
        "stderr":    str,            # judge 단계의 연료(지금은 그냥 기록)
        "timed_out": bool,
        "stage":     "build"|"run"   # 지금은 설치가 없어 항상 "run"(requirements 채우면 "build" 생김)
      }
    ※ '격리'는 안 한다(§1). VM에서 직접 실행 — AI 생성 코드를 직접 돌리는 위험은 가능성 단계라 감수.
      (나중에 도커 본문으로 이 함수를 갈아끼우면 격리가 들어온다. 계약은 그대로.)
    """
    workdir = tempfile.mkdtemp(prefix="aaa_run_")
    try:
        # 1) codes를 임시 폴더에 파일로 쓴다(파일 간 import가 맞물리도록 같은 폴더에)
        for name, code in codes.items():
            # 하위 경로(예 'pkg/x.py')도 대비
            fpath = os.path.join(workdir, name)
            os.makedirs(os.path.dirname(fpath), exist_ok=True) if os.path.dirname(fpath) else None
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(code)

        # 2) entry_point를 그 폴더 안에서 실행. stdin은 stdin_input에 따라:
        #    None이면 종전대로 빈 파이프(EOF) → input()은 EOFError(H1과 동일 조건).
        #    문자열이면 그걸 stdin으로 주입(input=...) → 대화형 CLI가 메뉴를 통과하나 실측.
        #    sys.executable로 지금 파이썬과 같은 인터프리터 사용(/usr/bin/python3).
        try:
            proc = subprocess.run(
                [sys.executable, entry_point],
                cwd=workdir,
                stdin=(subprocess.DEVNULL if stdin_input is None else None),
                input=stdin_input,               # None이면 무효(stdin=DEVNULL), 문자열이면 주입
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
            )
            return {
                "success": (proc.returncode == 0),
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "timed_out": False,
                "stage": "run",
            }
        except subprocess.TimeoutExpired as e:
            # 무한루프 등으로 시간 초과 — 그때까지의 출력은 e에 담겨 옴
            return {
                "success": False,
                "exit_code": -1,
                "stdout": e.stdout or "" if isinstance(e.stdout, str) else (e.stdout.decode() if e.stdout else ""),
                "stderr": (e.stderr or "" if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else ""))
                          + f"\n[runner] TimeoutExpired after {timeout}s",
                "timed_out": True,
                "stage": "run",
            }
    finally:
        # 3) 임시 폴더 폐기(매번 깨끗한 환경)
        shutil.rmtree(workdir, ignore_errors=True)


def looks_alive(run_result: dict, expected: str = None) -> bool:
    """'에러 없이 종료 ≠ 정상 동작' 보강(work_unified 7·9장).
    success가 아니면 당연히 False. expected가 주어지면 그 문자열이 stdout에 실제로 찍혔는지로 한 겹 더 본다.
    (빈 프로그램·삼킨 예외·입력 대기 후 즉시 종료가 success로 보이는 함정을 거른다.)
    ※ 이건 '판정'이 아니라 사실 확인 보조다 — 가능성 1층에서 사람이 참고할 신호."""
    if not run_result.get("success"):
        return False
    if expected:
        return expected in run_result.get("stdout", "")
    return True


# ======================================================================
# 단독 테스트: python3 runner.py
# ★ 키·네트워크 불요. 손으로 만든 코드 묶음 몇 개를 직접 돌려 계약(반환 dict)을 검증한다.
#   - 정상 실행 → success=True, stdout에 기대출력
#   - import 어긋남 → success=False, stderr에 ImportError
#   - 무한루프 → timed_out=True
#   - input() 대기 → stdin=EOF라 EOFError로 끝남(멈추지 않음)
# ======================================================================
if __name__ == "__main__":
    print("=== runner.py subprocess 실행 단독 테스트 ===\n")

    # ---------- [1] 정상 멀티파일: a.py를 main.py가 import해서 출력 ----------
    codes_ok = {
        "a.py": "def greet():\n    return 'hello from a'\n",
        "main.py": "from a import greet\nprint(greet())\n",
    }
    r = run_in_subprocess(codes_ok, "main.py")
    assert r["success"] is True, f"정상인데 실패: {r}"
    assert r["exit_code"] == 0, f"exit_code != 0: {r['exit_code']}"
    assert "hello from a" in r["stdout"], f"기대출력 없음: {r['stdout']!r}"
    assert r["timed_out"] is False
    assert r["stage"] == "run"
    print(f"[1] 정상 멀티파일 import 실행 ✓ (stdout={r['stdout'].strip()!r})")
    # looks_alive: 기대출력 확인
    assert looks_alive(r, expected="hello from a") is True
    assert looks_alive(r, expected="NOT THERE") is False
    print("    looks_alive 기대출력 보강 ✓")

    # ---------- [2] import 어긋남: 없는 함수 부름 → ImportError ----------
    codes_bad = {
        "a.py": "def greet():\n    return 'hi'\n",
        "main.py": "from a import nonexistent\nprint(nonexistent())\n",
    }
    r = run_in_subprocess(codes_bad, "main.py")
    assert r["success"] is False, "import 어긋났는데 성공으로 나옴"
    assert "ImportError" in r["stderr"] or "cannot import" in r["stderr"], f"stderr에 ImportError 없음: {r['stderr']!r}"
    print(f"[2] import 어긋남 → success=False, stderr에 ImportError ✓")

    # ---------- [3] 무한루프: timeout으로 잘리나 ----------
    codes_loop = {"main.py": "while True:\n    pass\n"}
    r = run_in_subprocess(codes_loop, "main.py", timeout=3)
    assert r["timed_out"] is True, "무한루프인데 timed_out 아님"
    assert r["success"] is False
    print(f"[3] 무한루프 → timed_out=True (timeout=3s) ✓")

    # ---------- [4] input() 대기: stdin=EOF라 EOFError로 끝남(멈추지 않음) ----------
    codes_input = {"main.py": "x = input('enter: ')\nprint('got', x)\n"}
    r = run_in_subprocess(codes_input, "main.py", timeout=5)
    # EOFError로 비정상 종료하지만, '멈추지 않고 끝났다'가 핵심(timed_out=False)
    assert r["timed_out"] is False, "input 대기인데 timeout까지 감(stdin EOF가 안 먹음)"
    assert "EOFError" in r["stderr"], f"EOFError가 stderr에 없음: {r['stderr']!r}"
    print(f"[4] input() → stdin EOF로 EOFError, 멈추지 않고 종료 ✓ (timed_out=False)")

    # ---------- [5] 런타임 에러: 0으로 나누기 → exit_code!=0, stderr에 ZeroDivision ----------
    codes_err = {"main.py": "print(1/0)\n"}
    r = run_in_subprocess(codes_err, "main.py")
    assert r["success"] is False
    assert "ZeroDivisionError" in r["stderr"], f"stderr에 ZeroDivisionError 없음: {r['stderr']!r}"
    print(f"[5] 런타임 에러 → success=False, stderr에 ZeroDivisionError ✓")

    print("\n=== 전체 통과 ✓ ===")
    print("    (격리 아님 — subprocess 직접 실행. §7 블랙박스 계약 dict 모양 유지)")
