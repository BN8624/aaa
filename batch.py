# batch.py
# §5 7번 "5~10회 실행": A~E 난이도 계단에서 각 2개(=10개) 요구사항을 순차로 던져
# runs.jsonl에 결과를 쌓는다. 이게 §6(첫 계측기)·리스크 레지스터(H1a/H1b)의 입력이 된다.
#
# ★ 핵심은 성공률이 아니라 '어느 칸부터 무너지기 시작하나'의 분포(9.5장).
#   A=바닥선(멀티파일 이전), B=멀티파일 CRUD, C=상태공유(데이터계약 시험), D=이벤트체인, E=의도적 실패영역.
#
# ★ expected_type은 여기서 칸 라벨로 붙이지만 planner엔 넘기지 않는다(§2-3).
#   run_task가 requirement만 planner에 주고 expected_type은 TaskState/runs.jsonl로만 흘리므로,
#   이 파일은 라벨을 task에 '기록'만 한다 — 모델은 자기가 몇 번 칸인지 모른다.
#
# 한 개가 실패하거나 파싱이 깨져도 멈추지 않고 다음으로 간다(실패도 데이터).
# 단 RPDExceeded(오늘 호출 한도 소진)면 그 자리에서 멈춘다 — 진행 불가라 §6 정책상 사람이 본다.

import time
import sys

from run import run_task
from limiter import RPDExceeded


# ★ H2_RUN 길1(a): 태스크 무관 '공통 더미 입력' 하나.
#   FINDINGS 사실 B — 무료 모델이 작은 CLI를 input()/메뉴루프로 짜서, stdin=EOF면 메뉴 앞 EOFError로 다 죽어
#   멀티파일이 멀쩡히 물려도 '메뉴 너머'(=H1b 파일간 동작)를 못 본다. 그 눈가림을 벗기는 최소 입력.
#   설계 사상: 메뉴 진입 숫자 + 더미 문자열을 섞어 흘리고, 안 먹으면 timeout이 받친다(이중 안전망).
#   ※ 측정장치(runner stdin)에만 닿는다 — planner/coder엔 안 닿아 모델 행동 불개입(§2-3 보존, 길2와의 차이).
#   ※ 이게 '정답 입력'은 아니다. 메뉴 구조가 다르면 헛입력일 수 있고, 그 결과(통과/실패)도 그대로 데이터다.
#     1~2개에 먼저 시험(H2_RUN §3) → 통과 확인됨. 정교화(설계서 기반 대본)는 데이터가 부르면 그때.
DUMMY_STDIN = "1\n테스트\n2\n3\n2\n1\n0\n"


# A~E 각 2개. work_unified 리스크 레지스터의 칸별 예시를 그대로 쓴다.
# (요구사항 문구는 한국어 — coder 주석도 한국어 눈높이라 일관, §14)
TASKS = [
    # A. 단일 파일 (멀티파일 이전의 바닥선)
    ("A1", "A", "2D 점 사이 거리 계산 CLI. 두 점의 좌표를 받아 유클리드 거리를 출력."),
    ("A2", "A", "시각(시:분:초) 덧셈 CLI. 두 시각을 받아 합을 24시간제로 출력."),

    # B. 멀티파일 CRUD (파일 간 인터페이스 등장)
    ("B1", "B", "2D 벡터 모음 관리. 벡터 추가/삭제/목록/합 벡터 계산. 저장은 로컬 JSON 파일."),
    ("B2", "B", "색상 팔레트 관리. RGB 색 추가/수정/삭제/목록. 저장은 로컬 파일."),

    # C. 상태 공유 (데이터 계약이 진짜 시험되는 곳 — 5장)
    ("C1", "C", "도형 캔버스. 원/사각형을 좌표·크기로 추가하고, 전체 넓이 합과 겹침 여부 조회. 저장은 로컬 파일."),
    ("C2", "C", "일정 블록 관리. 시작·끝 시각 블록 추가, 겹치는 일정 탐지, 빈 시간 조회. 저장은 로컬 파일."),

    # D. 이벤트 체인 (한 동작이 여러 파일을 연쇄로 건드림)
    ("D1", "D", "입자 이동 시뮬레이션 한 스텝. 위치·속도를 가진 입자들에 힘을 적용하면 속도·위치가 연쇄 갱신되고 경계 충돌 시 반사."),
    ("D2", "D", "유한상태기계 실행기. 상태·전이 정의를 받아 이벤트 입력열을 처리, 각 전이가 다음 상태와 출력으로 연쇄."),

    # E. 의도적 실패 영역 (무너지는 걸 보려고 일부러 어렵게)
    ("E1", "E", "3D 변환 파이프라인. 이동/회전/스케일 행렬을 합성해 점 집합에 순서대로 적용, 단계별 결과 보존."),
    ("E2", "E", "물리 충돌 해결. 질량·속도를 가진 물체들의 충돌을 운동량 보존으로 풀고, 다중 충돌이 서로 맞물려 갱신."),
]


def run_batch(*, save_dir: str = ".", runs_path: str = "runs.jsonl",
              timeout: int = 20, tag: str = None,
              stdin_input: str = DUMMY_STDIN, gen_stdin: bool = False) -> list:
    """TASKS를 순서대로 run_task로 실행. 각 결과 요약을 모아 반환하고, runs.jsonl엔 run_task가 한 줄씩 쌓는다.
    tag가 있으면 task_id 앞에 붙여 회차를 구분(예 tag='r1' → r1_A1).
    stdin_input: 모든 태스크에 흘릴 공통 stdin(H2_RUN 길1). 기본 DUMMY_STDIN. None으로 주면 H1과 동일(EOF).
    gen_stdin: True면 H4_RUN 길B — 태스크별로 생성된 코드+acceptance에서 stdin 대본을 만들어 주입.
               대본 생성 실패 시 위 stdin_input(=DUMMY_STDIN)으로 fallback."""
    results = []
    n = len(TASKS)
    print(f"=== batch 시작: {n}개 (A~E × 2) ===")
    print(f"    runs_path={runs_path}, timeout={timeout}s")
    print(f"    stdin: {'공통 더미 주입(길1)' if stdin_input is not None else 'EOF(H1 동일)'} "
          f"{repr(stdin_input) if stdin_input is not None else ''}")
    print(f"    대본: {'태스크별 생성(길B) — 실패 시 위로 fallback' if gen_stdin else '고정(생성 없음)'}\n")

    for i, (label, etype, req) in enumerate(TASKS, 1):
        task_id = f"{tag}_{label}" if tag else label
        print(f"[{i}/{n}] {task_id} (칸 {etype}) 시작 — {req[:30]}…")
        t0 = time.time()
        try:
            summary = run_task(req, expected_type=etype, task_id=task_id,
                               save_dir=save_dir, runs_path=runs_path, timeout=timeout,
                               stdin_input=stdin_input, gen_stdin=gen_stdin)
            dt = time.time() - t0
            designed = summary["designed_files"]
            generated = summary["generated_files"]
            # 화면용 한 줄 요약(판정 아님 — 사실 나열). designed≠generated면 눈에 띄게.
            mismatch = "" if set(designed) == set(generated) else "  ⚠designed≠generated"
            print(f"      → exit={summary['exit_code']} status={summary['status']} "
                  f"files: d{len(designed)}/g{len(generated)}{mismatch} ({dt:.0f}s)")
            if summary["stderr_head"].strip():
                print(f"      stderr: {summary['stderr_head'][:120]}")
            results.append(summary)

        except RPDExceeded as e:
            # 오늘 호출 한도 소진 — 더 못 간다. 여기까지 쌓인 건 runs.jsonl에 이미 있다.
            print(f"\n[중단] RPD 안전선 도달 — 오늘은 여기까지. ({e})")
            print(f"       지금까지 {len(results)}개 완료. 자정(PT) 지나 이어서 돌려라.")
            break
        except Exception as e:
            # 예상 못 한 예외도 멈추지 않고 다음으로(단 화면엔 남긴다)
            print(f"      → ✗ 예외(기록 후 계속): {type(e).__name__}: {e}")
            results.append({"task_id": task_id, "expected_type": etype,
                            "error": f"{type(e).__name__}: {e}"})

    print(f"\n=== batch 끝: {len(results)}/{n} 실행됨 ===")
    return results


if __name__ == "__main__":
    import os
    import json

    if not os.environ.get("VERTEX_API_KEY"):
        print("✗ VERTEX_API_KEY 없음. .bashrc 확인.")
        raise SystemExit(1)

    # 실제 데이터는 ~/aaa/runs.jsonl에 쌓는다(.gitignore에 있어 커밋 안 됨 — §14).
    # 회차 태그를 시각으로 붙여 재실행해도 task_id가 안 겹치게.
    tag = sys.argv[1] if len(sys.argv) > 1 else "r" + time.strftime("%m%d")
    results = run_batch(runs_path="runs.jsonl", tag=tag, gen_stdin=True)   # H4 길B 켬

    # 끝나고 분포를 칸별로 한눈에(이건 화면 요약 — 로그엔 비율 저장 안 함, §3).
    # '사실 나열'이지 성공률 계산이 아니다: 칸별로 exit_code와 d/g 일치만 보여준다.
    print("\n--- 칸별 관측(화면용, runs.jsonl엔 사실만 따로 적힘) ---")
    by_cat = {}
    for r in results:
        if "error" in r:
            by_cat.setdefault(r["expected_type"], []).append("ERR")
            continue
        d = set(r["designed_files"]); g = set(r["generated_files"])
        mark = f"exit{r['exit_code']}{'=' if d==g else '≠'}"  # = : d/g 파일명 일치
        by_cat.setdefault(r["expected_type"], []).append(mark)
    for cat in ["A", "B", "C", "D", "E"]:
        if cat in by_cat:
            print(f"    {cat}: {by_cat[cat]}")
    print("\n    (exit0=정상종료지만 '동작'은 아닐 수 있음 — argparse 무동작 등. 줄 전문을 사람이 읽어라)")
    print(f"    전체 로그: cat runs.jsonl  (또는 tail)")
