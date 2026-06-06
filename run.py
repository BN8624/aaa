# run.py
# v0 직진 조립부. 한 태스크를 "요구사항 → 설계 → 코드 → 실행 → runs.jsonl 한 줄"로
# 끝까지 한 번 흘린다. 이게 H1_RUN §0의 목적 — "첫 산출물은 앱이 아니라 runs.jsonl"을 실제로 만드는 곳.
#
# ★★ H1_RUN §1: 되돌림이 없다. 직진 1회만.
#   work_unified의 run_aaa는 check_consistency·judge_error·max_loops·되돌림 라우팅이
#   다 들어간 풍부한 루프지만, 그건 전부 v0 밖이다. v0는 설계→코드→실행→기록으로 직진하고,
#   실패해도 고치지 않는다 — 그 실패가 수집하려는 데이터다(9.5장).
#
# ★★ H1_RUN §2-1 / §3: 로그엔 '사실'만.
#   exit_code·stderr·runtime·designed_files·generated_files는 사실 → 기록한다.
#   success_rate·성공/실패 버킷·비율은 '계산된 값' → 절대 기록 안 한다(사람이 사후에).
#
# ★ expected_type은 TaskState에 기록만 하고 planner엔 넘기지 않는다(§2-3, 난이도 숨김).
#   여기서 make_design에 requirement만 넘기는 걸로 그 규칙이 코드로 강제된다.

import time

from limiter import Limiter
from state import TaskState
from planner import make_design
from coder import coding_stage
from runner import run_in_subprocess


def run_task(requirement: str, *, expected_type: str = None,
             task_id: str = None, save_dir: str = ".",
             runs_path: str = "runs.jsonl", timeout: int = 20,
             stdin_input: str = None, gen_stdin: bool = False) -> dict:
    """한 태스크를 직진 1회 실행하고 runs.jsonl에 결과 한 줄을 남긴다.

    requirement:   사용자 요구사항 텍스트(planner에 넘어가는 유일한 입력).
    expected_type: 의도한 결합도 A~E. ★ TaskState에만 기록 — planner엔 안 넘긴다(§2-3).
    task_id:       없으면 시각 기반으로 자동 생성.
    stdin_input:   subprocess에 흘릴 표준입력(H2_RUN 길1). 기본 None=종전대로 EOF.
                   ★ 측정장치(runner)에만 닿고 planner/coder엔 안 닿는다 — 모델 행동 불개입(§2-3 보존).
    gen_stdin:     True면 H4_RUN 길B — 생성된 코드+acceptance로 stdin 대본을 만들어 주입(scripter).
                   기본 False=H1·H2 그대로. 대본 생성 실패 시 들어온 stdin_input으로 fallback.
    반환: 이번 실행 요약 dict(사람이 바로 보기 위한 것 — 로그 파일엔 사실만 따로 적힌다).

    실패는 예외로 터뜨리지 않고 가능한 한 끝까지 진행해 기록한다(데이터 수집이 목적).
    단 한도 초과(RPDExceeded)·키 없음 같은 '진행 불가'는 그대로 올린다(짐작 금지).
    """
    if task_id is None:
        task_id = time.strftime("%Y%m%d_%H%M%S")

    limiter = Limiter()   # 토대 기본값(rpm=15, rpd_limit=1450)
    state = TaskState(task_id, expected_type=expected_type, save_dir=save_dir)

    # 실행 결과(runner가 못 가면 기본값) — runs.jsonl에 넣을 '사실'
    exit_code = None
    stderr = ""
    runtime = 0.0

    t0 = time.time()
    try:
        # ① 설계 (26B) — requirement'만' 넘긴다(expected_type 숨김)
        state.stage = "design"
        state.save()
        design = make_design(requirement, limiter=limiter)
        state.designed_files = [f.get("name") for f in design.get("files", [])]  # H1a 원재료
        state.save()

        # ② 코딩 (31B) — 시그니처만 공유로 파일별 생성
        state.stage = "coding"
        state.save()
        codes = coding_stage(design, limiter=limiter)
        state.generated_files = codes   # H1b 원재료(designed와 대조)
        state.save()

        # ②.5 입력 대본 (H4_RUN 길B) — gen_stdin일 때만. 생성된 코드+acceptance를 읽어 stdin 대본 생성.
        #   measurement(stdin)에만 닿고 planner/coder엔 안 닿음(§2-3). 못 만들면 들어온 stdin_input 유지(fallback).
        if gen_stdin:
            from scripter import make_input
            stdin_input = make_input(design, codes, limiter=limiter) or stdin_input

        # ④ 실행 (subprocess, 격리 아님 §1) — 실측. ③ 정합성검토는 v0 밖이라 건너뜀.
        state.stage = "run"
        state.save()
        entry = design.get("entry_point") or "main.py"
        run_result = run_in_subprocess(codes, entry, timeout=timeout,
                                       stdin_input=stdin_input)

        exit_code = run_result["exit_code"]
        stderr = run_result["stderr"]
        runtime = round(time.time() - t0, 2)

        # 상태 기록(사실). success 같은 '판정'은 status에 굳이 안 박고 사실만:
        # exit_code==0이면 done, 아니면 failed로 둔다(이건 기계 판정이라 사실에 가깝다).
        state.status = "done" if exit_code == 0 else "failed"
        if exit_code != 0:
            # 실패 '사실'을 Failure Log에 (해석 안 함, stderr 원문)
            state.add_failure(state.stage, stderr[:2000])
        state.save()

    except Exception as e:
        # 설계/코딩 단계에서 진행이 막힌 경우(파싱 실패 등) — 그것도 사실로 기록하고 넘어간다.
        # 단 RPDExceeded처럼 '오늘 더는 못 함'은 기록 후 그대로 올려 상위가 멈추게 한다.
        runtime = round(time.time() - t0, 2)
        stderr = f"{type(e).__name__}: {e}"
        exit_code = -1
        state.status = "failed"
        state.add_failure(state.stage, stderr[:2000])
        state.save()

        from limiter import RPDExceeded
        if isinstance(e, RPDExceeded):
            # 기록은 남기고(아래 dump) 멈춤 신호로 올린다
            state.dump_to_dataset(exit_code=exit_code, stderr=stderr, runtime=runtime, path=runs_path, stdin=stdin_input)
            raise

    # ★ 종료 시(성공·실패 가리지 않고) runs.jsonl에 결과 한 줄 — 0단계 사실 필드만(§3)
    state.dump_to_dataset(exit_code=exit_code, stderr=stderr, runtime=runtime, path=runs_path, stdin=stdin_input)

    # 사람이 바로 볼 요약 반환(이건 화면용 — 로그 파일과 별개, 계산값 아님)
    return {
        "task_id": task_id,
        "expected_type": expected_type,
        "designed_files": state.designed_files,
        "generated_files": list(state.generated_files.keys()),
        "exit_code": exit_code,
        "runtime": runtime,
        "status": state.status,
        "stderr_head": stderr[:300],
    }


# ======================================================================
# 단독 테스트: python3 run.py
# ★ 실호출(키 필요) — planner+coder+runner를 한 바퀴 돌려 runs.jsonl 한 줄이 생기나 본다.
#   작은 요구사항 1개. expected_type='B'(멀티파일 CRUD)로 기록만(planner엔 안 감).
#   결과가 성공이든 실패든 runs.jsonl에 0단계 8필드가 적히면 통과 — 실패도 데이터다.
# ======================================================================
if __name__ == "__main__":
    import os
    import json

    print("=== run.py v0 직진 조립부 단독 테스트 ===\n")

    if not os.environ.get("GOOGLE_API_KEY"):
        print("✗ GOOGLE_API_KEY 없음. .bashrc 확인.")
        raise SystemExit(1)

    TEST_RUNS = "/tmp/aaa_test_runs.jsonl"
    TEST_DIR = "/tmp/aaa_run_test"
    if os.path.exists(TEST_RUNS):
        os.remove(TEST_RUNS)
    os.makedirs(TEST_DIR, exist_ok=True)

    req = "간단한 CLI 메모장. 메모 추가/목록 2기능. 저장은 로컬 파일."
    print(f"[요구사항] {req}")
    print("[expected_type] B (기록만 — planner엔 숨김)\n")
    print("[1] 직진 실행: 설계→코드→실행→기록 (모델 호출 여러 번, 1~2분)…")

    summary = run_task(req, expected_type="B", task_id="test_b01",
                       save_dir=TEST_DIR, runs_path=TEST_RUNS)

    print("[1] 한 바퀴 완료 ✓\n")
    print("[2] 실행 요약(화면용):")
    for k, v in summary.items():
        print(f"    {k}: {v}")

    # runs.jsonl에 한 줄 적혔나 + 0단계 8필드만 + 계산값 없는지
    assert os.path.exists(TEST_RUNS), "runs.jsonl이 안 생김"
    with open(TEST_RUNS, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1, f"runs.jsonl 줄 수가 1이 아님: {len(lines)}"
    row = json.loads(lines[0])
    expected_keys = {"task_id", "expected_type", "designed_files",
                     "generated_files", "exit_code", "stderr", "runtime", "stdin", "created_at"}
    assert set(row.keys()) == expected_keys, f"0단계 필드 불일치: {set(row.keys())}"
    for forbidden in ("success", "success_rate", "status", "verdict", "bucket"):
        assert forbidden not in row, f"금지된 계산/판정 필드: {forbidden}"
    print("\n[3] runs.jsonl 한 줄 ✓ — 0단계 8필드만, 계산값 없음")
    print(f"    expected_type={row['expected_type']} / designed={row['designed_files']}")
    print(f"    generated={list(row['generated_files'].keys())} / exit_code={row['exit_code']}")

    # H1a/H1b 사각지대 한눈에: designed와 generated 파일명 대조
    designed = set(row["designed_files"])
    generated = set(row["generated_files"].keys())
    print(f"\n[관측] designed({len(designed)}) vs generated({len(generated)}):")
    print(f"    설계만 있고 코드 없음: {designed - generated or '없음'}")
    print(f"    코드만 있고 설계 없음: {generated - designed or '없음'}")
    print("    (파일명은 맞아도 '내용이 서로 안 부르는' 사각지대는 0단계가 못 잡음 — §3·§6 계측기 후보)")

    print("\n=== 통과 ✓ === (실패였어도 runs.jsonl에 적혔으면 그게 데이터다)")
    print("\n--- runs.jsonl 줄 전문 ---")
    print(json.dumps(row, ensure_ascii=False, indent=2))
