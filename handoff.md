# aaa — HANDOFF (작업용)

> 이 문서 = 살아있는 현재 상태만. **얇게 유지(1~2화면).** 정의·명세·근거는 베끼지 않고 가리킨다.
> 
> - 왜·무엇·구현 명세·가설 정의 → **정본 `work_unified.md`**
> - 회차별 날 사실(rows·코드 대조) → **repo `FINDINGS.md`**
> - 여기엔: ①현재 위치 ②다음 한 수 ③작업 체크리스트 만.
>   기준일 2026-06-08.

-----

## 1. 현재 위치

- **H1 (a/b/c) 종료.** H1b = 부재(Gemini 누적 ~130칸 표면 0, 진짜 부재 3중 확인). → 정본 리스크 레지스터 / FINDINGS §1~10.
- **Q7 (왜 dict 수렴) 종료.** 객체를 파일 내부 격리, 경계는 dict → 멤버 계약 충돌 구조적 미발생.
- **Q8 (실패=실행채널 문제?) 진행 중 — 현재 주 질문.** stdin 대본 불일치·JSON 포맷·timeout·argv/stdin 채널 불일치. analyzer가 STDIN_EXIT_MISMATCH·STDIN_FORMAT_MISMATCH 분류 중.
- 보류: H2(모델 통일로 비교군 소멸), H4(도커 미구현). 미착수: H3. → 정본 리스크 레지스터.

## 2. 다음 한 수 (하나만 고르고 그것만)

후보:

1. **analyzer + verify_channel 통합** ★ 추천. 현재 analyze_h1b.py 단독은 `exit0가짜`로 뭉뚱그려 Q8 관점에서 거의 무의미. verify_channel(stdout 재생)을 매 회차 자동으로 태워 alive/reject/silent/broken로 풀어야 “Q8 실행 실패 분석기”가 완성. 도구 통합이라 절대 제약 무관(§3).
- 남은 분류 갭: `H1B_IMPORT`/`H1B_SIGNATURE` 분리, `TIMEOUT_REAL`(무한루프 vs STDIN_EXIT), `RUNTIME_EXCEPTION` 통일.
1. **FINDINGS §11 작성** — vtx_14~17(40칸, H1b 0) 아직 미반영. 닫고 기록.
1. **Q8 새 회차** — vtx_19부터(키 확인 → arun.sh). vtx_18은 봇 테스트 잔재(빈손), 폐기.

## 3. 작업 체크리스트 (까먹지 말 것 — 정의는 정본/아래 참조)

회차 돌리기 전:

- [ ] **키 확인**: `echo $VERTEX_API_KEY` (미설정 시 files=[]·exit=-1 가짜 행 오염)
- [ ] **새 tag**: `<세션>_<회차>` 형식, `_숫자_` 유지(analyze 정규식 요구). 부분/실패 tag 재사용 금지 → 새 번호.
- [ ] **한글 파일(batch.py TASKS) 편집은 GitHub 웹 Edit** — 폰 sed 금지(인코딩 깨짐, vtx_11·12 무효 전례). 편집 후 폰에서 `git fetch && git reset --hard origin/main`.

돌리기:

- `/실행 <tag>` (Discord) 또는 tmux에서 `bash arun.sh <tag>` (analysis_out 생성됨). `python3 -u batch.py`만 쓰면 rows.csv 안 생김.
- **0실행 빈손 push 주의**: batch 미실행인데 빈 analysis push되는 사고(vtx_18). 결과 확인 = runs.jsonl에 해당 tag 행 ≥1.

절대 제약 (→ 정본, 자연발생량 관측 중이라 엄수):

- planner/coder 프롬프트로 모델 행동 제약 금지.
- expected_type(A~E 라벨) planner에 넘기기 금지.
- 깸을 *줄이는* 수정 금지(계측기는 데이터가 호명할 때만).
- 한 번에 한 곳/한 변수만. 단일 회차로 판정 금지(비결정적, 누적 필요).

## 4. repo 상태 · 읽는 법

- `github.com/BN8624/aaa` (main). tip = `57cde53` (vtx_18 — 잔재).
- 모델: 전 역할 gemini-3.5-flash, Vertex REST, 키 VERTEX_API_KEY. → 정본 3장.
- 핵심 도구: `analyze_h1b.py`(관측, rows.csv), `verify_channel.py`(stdout 재생→alive/reject/broken/silent/inputmismatch), `arun.sh`(회차 자동화+pull+analyze).
- 읽기: repo 검색 안 됨 → `git clone` 후 task_id로 runs.jsonl grep (가장 확실), 또는 raw URL(push 후 1~2분 CDN 지연).

-----

*이 문서가 길어지면 잘못된 것 — 정의·근거가 새어든 것이니 정본으로 도로 밀어낼 것.*