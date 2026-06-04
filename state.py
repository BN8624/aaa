# state.py
# 루프 전체가 읽고 쓰는 단일 상태 객체(work_unified 8장).
# AI 머릿속(대화 히스토리)이 아니라 이 객체가 진실의 출처다.
# 재접속·재시작에도 안 잃도록 JSON으로 "즉시" 저장한다(임시파일 -> rename, 쓰다 죽어도 원본 안 깨짐).
#
# 이 파일은 토대 중 유일하게 독립이다(다른 토대에 안 기댐) -> H1_RUN §5 첫 타자.
# 스키마 필드는 H1_RUN §3 기준: expected_type / designed_files / generated_files
#   + stage / attempt / status / failures / dead_end.
#
# ★ 주의(H1_RUN §2): 여기엔 "사실"만 담는다.
#   success_rate, 성공/실패 버킷, 비율 같은 "계산된 값"은 저장하지 않는다.
#   비율·분류는 로그가 쌓인 뒤 사람이 사후에 만든다.

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta

# PT(태평양시) = UTC-8 기준. RPD 리셋이 PT 자정이라 created_at도 PT로 맞춘다(work_unified 11장).
# (서머타임은 가능성 단계에선 무시 — 날짜 경계 정합성만 맞추면 됨. 필요해지면 그때 정교화)
PT = timezone(timedelta(hours=-8))


def _now_pt() -> str:
    """현재 시각을 PT 기준 ISO 문자열로. created_at에 쓴다."""
    return datetime.now(PT).isoformat()


class TaskState:
    """한 태스크의 루프 상태. 매 단계 변화 직후 save()를 불러 디스크에 박는다.

    하는 일:
      - 루프 관리(지금 어느 stage, 몇 번째 attempt)
      - 종료 조건 판정 근거(attempt가 max_loops에 닿았나)
      - 실패 추적(failures: 무엇이 났나 / dead_end: 무엇을 하지 마라)
      - 루프 종료 시 결과 한 줄을 runs.jsonl에 떨굼(Failure Dataset)
    """

    def __init__(self, task_id: str, expected_type: str = None,
                 save_dir: str = "."):
        # --- 식별 ---
        self.task_id = task_id
        # 의도한 결합도 A~E. ★ planner 프롬프트엔 절대 넣지 않는다(난이도 알면 모델이 적응 — §2-3).
        # 여기엔 기록만 하고 runs.jsonl로 흘려보낸다.
        self.expected_type = expected_type

        # --- H1 원재료 (이 둘의 대조가 0단계의 핵심 신호) ---
        self.designed_files = []      # planner가 설계한 파일명들(설계 JSON files의 name). H1a 원재료.
        self.generated_files = {}     # coder가 실제 만든 {파일명: 코드}. H1b 원재료.

        # --- 루프 진행 ---
        self.stage = "design"         # design / coding / review / docker / output
        self.attempt = 0              # 같은 단계 재시도 횟수 (3회 롤백·max_loops 판정 근거)
        self.status = "running"       # running / stopped / done / failed

        # --- 실패 기록 (두 종류로 분리 — work_unified 8장) ---
        self.failures = []            # Failure Log: "무엇이 났나" [{attempt, stage, error}] 단순 누적
        self.dead_end = []            # known_failures: "무엇을 하지 마라" 시도했다 실패한 접근 목록

        # --- 메타 ---
        self.created_at = _now_pt()   # PT 기준
        self._path = os.path.join(save_dir, f"task_{task_id}.json")

    # ---------- 직렬화 ----------

    def to_dict(self) -> dict:
        """저장/복원에 쓰는 순수 dict. 사실 필드만 — 계산값 없음."""
        return {
            "task_id": self.task_id,
            "expected_type": self.expected_type,
            "designed_files": self.designed_files,
            "generated_files": self.generated_files,
            "stage": self.stage,
            "attempt": self.attempt,
            "status": self.status,
            "failures": self.failures,
            "dead_end": self.dead_end,
            "created_at": self.created_at,
        }

    def save(self) -> None:
        """JSON으로 즉시 저장. 임시파일에 다 쓴 뒤 rename(원자적 교체) —
        쓰다 죽어도 기존 파일이 반쪽으로 깨지지 않는다."""
        d = os.path.dirname(self._path) or "."
        # 같은 디렉터리에 임시파일을 만들어야 rename이 원자적(다른 파일시스템 간 rename은 안 그럼)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".task_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())   # 디스크에 실제로 내려쓰게 강제
            os.replace(tmp, self._path)   # 원자적 교체
        except Exception:
            # 실패하면 임시파일 청소하고 예외 그대로 올림(조용히 삼키지 않음)
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    @classmethod
    def load(cls, task_id: str, save_dir: str = ".") -> "TaskState":
        """task_id로 저장된 상태를 복원. 만료·점수화는 두지 않는다(§2 단순함, 8장)."""
        path = os.path.join(save_dir, f"task_{task_id}.json")
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        obj = cls(d["task_id"], expected_type=d.get("expected_type"),
                  save_dir=save_dir)
        obj.designed_files = d.get("designed_files", [])
        obj.generated_files = d.get("generated_files", {})
        obj.stage = d.get("stage", "design")
        obj.attempt = d.get("attempt", 0)
        obj.status = d.get("status", "running")
        obj.failures = d.get("failures", [])
        obj.dead_end = d.get("dead_end", [])
        obj.created_at = d.get("created_at", _now_pt())
        return obj

    # ---------- 상태 갱신 ----------

    def add_failure(self, stage: str, error: str) -> None:
        """이번 시도에서 난 에러를 Failure Log에 누적하고 attempt를 1 올린다.
        (error는 stderr 원문 등 '사실'을 그대로 — 해석하지 않는다.)"""
        self.attempt += 1
        self.failures.append({
            "attempt": self.attempt,
            "stage": stage,
            "error": error,
        })

    def add_dead_end(self, approach: str) -> None:
        """시도했다 실패한 '접근'을 known_failures에 누적(중복 제거).
        다음 프롬프트에 '재시도 금지'로 박는 통로 — 단 태스크 1회 한정(루프 끝나면 폐기).
        ※ H1_RUN §1상 dead_end '주입'은 지금 안 켠다. 이 메서드는 그릇만 — 주입은 v1 이후."""
        if approach not in self.dead_end:
            self.dead_end.append(approach)

    # ---------- Failure Dataset 적재 ----------

    def dump_to_dataset(self, exit_code: int, stderr: str, runtime: float,
                        path: str = "runs.jsonl") -> None:
        """루프 종료 시(성공·실패·중단 가리지 않고) 결과 '한 줄'을 runs.jsonl에 append.
        ★ 0단계 필드 = 관측 사실만. 계산된 값(success/실패 버킷·비율) 금지 — 사람이 사후에(§2-1).
        observer 키(py_compile/ruff/mypy)는 0단계 로그가 호명할 때만 추가(§6).

        exit_code/stderr/runtime은 runner 결과라 TaskState가 안 들고 있으므로 인자로 받는다.
        """
        row = {
            "task_id": self.task_id,
            "expected_type": self.expected_type,
            "designed_files": self.designed_files,
            "generated_files": self.generated_files,
            "exit_code": exit_code,
            "stderr": stderr,
            "runtime": runtime,
            "created_at": self.created_at,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ======================================================================
# 단독 테스트: python3 state.py
# save -> load 왕복에서 상태가 그대로 복원되나(상태 비손실)만 본다.
# 모델 호출·한도 없음 — state.py는 독립이라 이것만으로 끝.
# ======================================================================
if __name__ == "__main__":
    import shutil

    TEST_DIR = "/tmp/aaa_state_test"
    # 깨끗한 환경에서 시작
    shutil.rmtree(TEST_DIR, ignore_errors=True)
    os.makedirs(TEST_DIR, exist_ok=True)

    print("=== state.py save->load 단독 테스트 ===\n")

    # 1) 상태를 하나 만들고 이런저런 값을 채운다
    s = TaskState("t001", expected_type="C", save_dir=TEST_DIR)
    s.designed_files = ["model.py", "service.py", "storage.py"]
    s.generated_files = {"main.py": "print('hi')\n"}
    s.stage = "coding"
    s.add_failure("coding", "ImportError: cannot import name foo")  # attempt -> 1
    s.add_failure("coding", "SyntaxError: invalid syntax")          # attempt -> 2
    s.add_dead_end("requirements 수정 방식")
    s.add_dead_end("requirements 수정 방식")  # 중복 -> 무시돼야 함
    s.status = "stopped"
    s.save()
    print("[1] save 완료:", s._path)

    # 2) 다른 객체로 load 해서 복원
    loaded = TaskState.load("t001", save_dir=TEST_DIR)
    print("[2] load 완료\n")

    # 3) 필드별로 원본과 일치하는지 assert
    assert loaded.task_id == "t001", "task_id 불일치"
    assert loaded.expected_type == "C", "expected_type 불일치"
    assert loaded.designed_files == ["model.py", "service.py", "storage.py"], "designed_files 불일치"
    assert loaded.generated_files == {"main.py": "print('hi')\n"}, "generated_files 불일치"
    assert loaded.stage == "coding", "stage 불일치"
    assert loaded.attempt == 2, f"attempt 불일치: {loaded.attempt}"
    assert loaded.status == "stopped", "status 불일치"
    assert len(loaded.failures) == 2, f"failures 개수 불일치: {len(loaded.failures)}"
    assert loaded.failures[0]["error"].startswith("ImportError"), "failures 내용 불일치"
    assert loaded.dead_end == ["requirements 수정 방식"], f"dead_end 중복제거 실패: {loaded.dead_end}"
    assert loaded.created_at == s.created_at, "created_at 불일치"
    print("[3] 모든 필드 복원 일치 ✓ (save->load 비손실)\n")

    # 4) runs.jsonl 적재 확인 — 0단계 필드만, 계산값 없는지 눈으로
    runs_path = os.path.join(TEST_DIR, "runs.jsonl")
    loaded.dump_to_dataset(exit_code=1,
                           stderr="ImportError: cannot import name foo",
                           runtime=2.4,
                           path=runs_path)
    with open(runs_path, encoding="utf-8") as f:
        line = f.readline()
    row = json.loads(line)
    expected_keys = {"task_id", "expected_type", "designed_files",
                     "generated_files", "exit_code", "stderr",
                     "runtime", "created_at"}
    assert set(row.keys()) == expected_keys, f"runs.jsonl 키가 0단계와 다름: {set(row.keys())}"
    # 계산된 값이 새어들지 않았는지 확인
    for forbidden in ("success", "success_rate", "status", "verdict"):
        assert forbidden not in row, f"금지된 계산/판정 필드 발견: {forbidden}"
    print("[4] runs.jsonl 한 줄 적재 ✓ — 0단계 8개 필드만, 계산값 없음")
    print("    기록된 키:", sorted(row.keys()))

    print("\n=== 전체 통과 ✓ ===")

    # 테스트 흔적 청소
    shutil.rmtree(TEST_DIR, ignore_errors=True)
