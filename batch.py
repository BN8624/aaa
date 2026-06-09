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

# Windows 콘솔 기본 cp949에선 한글·화살표·em-dash 등 print가 즉시 크래시한다
# (vtx_19 빈손 사고: batch.py:75 '\u2014'에서 UnicodeEncodeError로 생성 0칸).
# 출력 스트림을 UTF-8로 재설정해 모든 진행 메시지를 안전하게(인코딩 무관) 만든다.
# 관측·생성 로직 불변, 화면 출력 인코딩만 교정.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from run import run_task
from limiter import RPDExceeded, RateLimitError, PermanentHTTPError


# ★ 관측 천장 해소 입력 (A 과제 구현).
#   문제: 메뉴형 프로그램은 stdin=EOF면 메뉴 루프에 도달 못 함. argparse 프로그램은 argv 없으면 exit=1.
#   해법: ①DUMMY_STDIN — 메뉴 숫자+텍스트 고정 시퀀스로 메뉴 경로 실행. ②DUMMY_ARGV — positional arg를
#   항상 주입해 argparse 프로그램도 진입.
#   ※ 측정장치(runner)에만 닿음 — planner/coder엔 안 닿아 모델 행동 불개입(§2-3 보존).
#   ※ '정답 입력'이 아니라 '관측 기회를 여는 입력'. 헛입력이면 그 결과도 데이터.
#   ※ gen_stdin(scripter)은 비활성화 — 대본이 짧아 EOFError 유발(FINDINGS §4), 일관성 저해.
DUMMY_STDIN = (
    "1\n테스트 입력\n"
    "2\n샘플 데이터\n"
    "3\n1\n"
    "4\nexample\n"
    "1\nhello world\n"
    "2\n"
    "0\nquit\nexit\n"
)
# "1" = 유효한 산술식(단일 숫자 리터럴)이자 유효한 문자열 positional → 표현식 파서(C·D)·
# argparse·int(argv[1]) 계열 모두 통과. "test input"은 표현식 토크나이저에서 즉사(§25 C1).
DUMMY_ARGV = ["1"]


# A~E 각 2개. work_unified 리스크 레지스터의 칸별 예시를 그대로 쓴다.
# (요구사항 문구는 한국어 — coder 주석도 한국어 눈높이라 일관, §14)
#
# ★ vtx_14: 도메인을 그래프/트리/파서 계열로 교체(Q7 — 객체가 자연스러운 도메인에서도 dict 수렴하나).
#   자료구조(dict/class/dataclass)는 한 글자도 지정하지 않는다(유도 금지, work §7).
#   결합도 의미·etype·라벨·3-튜플 구조는 vtx_13과 동일하게 보존.
TASKS = [
    # A. 단일 파일 (멀티파일 이전의 바닥선)
    ("A1", "A", "이진 탐색 트리 CLI. 정수 키를 insert/find/delete하고, 중위 순회로 정렬된 키 목록을 출력."),
    ("A2", "A", "괄호 짝 검사 CLI. 한 줄 문자열을 받아 (), [], {} 괄호가 올바르게 짝지어졌는지 출력."),

    # B. 멀티파일 CRUD (파일 간 인터페이스 등장)
    ("B1", "B", "방향 그래프 관리. 정점·간선 추가/삭제/목록, 한 정점의 이웃 조회. 저장은 로컬 JSON 파일."),
    ("B2", "B", "태그 계층 관리. 부모-자식 태그 추가/삭제/목록, 한 태그의 모든 하위 태그 조회. 저장은 로컬 파일."),

    # C. 상태 공유 (데이터 계약이 진짜 시험되는 곳 — 5장)
    ("C1", "C", "산술식 평가기. 괄호와 +,-,*,/ 를 포함한 식을 토큰화·파싱·계산하는 세 단계로 나눠 결과 출력."),
    ("C2", "C", "S-식 평가기. (add 1 (mul 2 3)) 같은 중첩 표현을 읽어 구조로 만들고 재귀적으로 평가."),

    # D. 이벤트 체인 (한 동작이 여러 파일을 연쇄로 건드림)
    ("D1", "D", "들여쓰기 트리 처리. 들여쓰기 텍스트를 계층 구조로 읽어, 각 노드에 누적 깊이를 매기고, 다시 텍스트로 직렬화하는 연쇄."),
    ("D2", "D", "표현식 트리 재작성. 식을 트리로 파싱한 뒤, 상수 부분식을 접고(예 2*3→6), 접힌 트리를 다시 식 문자열로 출력하는 연쇄."),

    # E. 의도적 실패 영역 (무너지는 걸 보려고 일부러 어렵게)
    ("E1", "E", "그래프 연결요소 파이프라인. 무방향 그래프에서 연결요소를 찾고, 각 요소의 대표·크기를 요약하고, 요약을 받아 가장 큰 요소만 다시 출력하는 상호참조."),
    ("E2", "E", "의존성 해소. 모듈 간 의존을 받아 위상정렬로 빌드 순서를 내고, 순환 의존이 맞물리면 순환에 든 모듈 집합을 보고."),
]


def run_batch(*, save_dir: str = ".", runs_path: str = "runs.jsonl",
              timeout: int = 20, tag: str = None,
              stdin_input: str = DUMMY_STDIN, gen_stdin: bool = False,
              argv: list[str] | None = DUMMY_ARGV,
              use_docker: bool = False, docker_image: str = "python:3.11-slim",
              docker_network: str = "none") -> list:
    """TASKS를 순서대로 run_task로 실행. 각 결과 요약을 모아 반환하고, runs.jsonl엔 run_task가 한 줄씩 쌓는다.
    tag가 있으면 task_id 앞에 붙여 회차를 구분(예 tag='r1' → r1_A1).
    stdin_input: 모든 태스크에 흘릴 공통 stdin. 기본 DUMMY_STDIN. None으로 주면 EOF.
    argv: 프로그램에 넘길 CLI 인수 목록. 기본 DUMMY_ARGV(argparse 프로그램 진입용). None이면 인수 없음.
    gen_stdin: True면 태스크별 LLM 대본 생성(scripter). 기본 False — 대본 짧아 EOFError 유발(FINDINGS §4).
    use_docker: True면 H4 Docker 실측 runner를 사용. 기본 False는 기존 subprocess 실측."""
    results = []
    n = len(TASKS)
    print(f"=== batch 시작: {n}개 (A~E × 2) ===")
    print(f"    runs_path={runs_path}, timeout={timeout}s")
    print(f"    stdin: {'더미 주입' if stdin_input is not None else 'EOF'} "
          f"{repr(stdin_input[:30] + '...') if stdin_input is not None else ''}")
    print(f"    argv: {argv!r}")
    print(f"    대본: {'태스크별 생성(길B) — 실패 시 위로 fallback' if gen_stdin else '고정(생성 없음)'}")
    print(f"    runner: {'docker' if use_docker else 'subprocess'}"
          f"{f' image={docker_image} network={docker_network}' if use_docker else ''}\n")

    for i, (label, etype, req) in enumerate(TASKS, 1):
        task_id = f"{tag}_{label}" if tag else label
        print(f"[{i}/{n}] {task_id} (칸 {etype}) 시작 — {req[:30]}…")
        t0 = time.time()
        try:
            summary = run_task(req, expected_type=etype, task_id=task_id,
                               save_dir=save_dir, runs_path=runs_path, timeout=timeout,
                               stdin_input=stdin_input, gen_stdin=gen_stdin, argv=argv,
                               use_docker=use_docker, docker_image=docker_image,
                               docker_network=docker_network)
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

        except (RPDExceeded, RateLimitError, PermanentHTTPError) as e:
            # 진행 불가 인프라 사실(RPD 소진 / 429 지속 거부 / 키·권한 문제) — 더 못 간다.
            # 여기까지 쌓인 건 runs.jsonl에 이미 있다. 남은 칸을 fake로 채우지 않고 멈춘다(§3).
            kind = type(e).__name__
            print(f"\n[중단] {kind} — 진행 불가. ({e})")
            print(f"       지금까지 {len(results)}개 완료. 원인 해소 후 이어서 돌려라.")
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
    import argparse

    if not os.environ.get("VERTEX_API_KEY"):
        print("✗ VERTEX_API_KEY 없음. .bashrc 확인.")
        raise SystemExit(1)

    # 실제 데이터는 ~/aaa/runs.jsonl에 쌓는다(.gitignore에 있어 커밋 안 됨 — §14).
    # 회차 태그를 시각으로 붙여 재실행해도 task_id가 안 겹치게.
    parser = argparse.ArgumentParser(description="Run aaa batch measurements.")
    parser.add_argument("tag", nargs="?", default="r" + time.strftime("%m%d"))
    parser.add_argument("--docker", action="store_true", help="use Docker runner for H4 measurement")
    parser.add_argument("--docker-image", default="python:3.11-slim")
    parser.add_argument("--docker-network", default="none")
    args = parser.parse_args()

    results = run_batch(
        runs_path="runs.jsonl",
        tag=args.tag,
        gen_stdin=False,
        use_docker=args.docker,
        docker_image=args.docker_image,
        docker_network=args.docker_network,
    )

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
