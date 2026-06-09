# aaa — HANDOFF (작업용)

> 이 문서 = 살아있는 현재 상태만. **얇게 유지(1~2화면).** 정의·명세·근거는 베끼지 않고 가리킨다.
> 
> - 왜·무엇·구현 명세·가설 정의 → **정본 `work_unified.md`**
> - 회차별 날 사실(rows·코드 대조) → **repo `FINDINGS.md`**
> - 여기엔: ①현재 위치 ②다음 한 수 ③작업 체크리스트 만.
>   기준일 2026-06-09.

-----

## 1. 현재 위치

- **H1 (a/b/c) 종료.** H1b = 부재(Gemini 누적 표면 0, 진짜 부재 다중 확인). 이제 vtx_13~25 유효 회차 **100칸 연속 H1b 0**(vtx_18·19·21 폐기). → 정본 리스크 레지스터 / FINDINGS §1~15.
- **Q7 (왜 dict 수렴) 종료, 단 미세수정.** 주류는 dict/list 경계라 멤버 계약 충돌 구조적 미발생. vtx_25_D2처럼 class `Node`가 파일 경계를 넘어도 공유 생성자/동일 클래스 import로 계약이 맞으면 H1b 없이 완주.
- **Q8 (실패=실행채널 문제?) 진행 중 — 현재 주 질문.** **도구 갖춰짐**: analyzer가 매 회차 verify_channel 재실행 분류(alive/reject/broken/silent/inputmismatch)+채널 자동 부착, broken vs 채널불일치 자동 분리. → FINDINGS §11.
  - ★ **부분 반례가 재현됐지만 좁아짐(§12·§14·§15)**: vtx_20·22 broken은 채널이 아니라 AST 데이터계약 불일치였으나, vtx_23~25에서는 C AST 스키마 불일치가 직접 재현 안 됨. 새 비채널 broken은 vtx_23_D2의 문법/데이터계약(`x` 변수 거부). E2 JSON은 `STDIN_FORMAT_MISMATCH`, vtx_25_D2 class 경계 신호는 `STATIC_H1B_FALSE_POSITIVE`로 자동 분리됨.
- 보류: H2(모델 통일로 비교군 소멸), H4(도커 미구현). 미착수: H3. → 정본 리스크 레지스터.

## 2. 다음 한 수 (하나만 고르고 그것만)

직전 완료(2026-06-09): ①analyzer+verify_channel 통합 ✅ ②FINDINGS §11(vtx_14~17 닫음) ✅ ③Windows cp949 버그 수정 ✅ ④FINDINGS §12(vtx_20 닫음) ✅ ⑤회차완료 디스코드 웹훅 알림 구현/환경 우선순위 수정 ✅ ⑥vtx_21 429 사건 → client 에러분류·429복구 재설계(FINDINGS §13) ✅ ⑦vtx_22 완주(FINDINGS §14) ✅ ⑧vtx_23~25 완주(FINDINGS §15) ✅ ⑨분류 갭 보강(`DATA_CONTRACT_GRAMMAR`/`STDIN_FORMAT_MISMATCH`/`STATIC_H1B_FALSE_POSITIVE`) ✅.

★ §13 수정 핵심(client.py·limiter.py·run.py·batch.py): 400/401/403/404=재시도금지(`PermanentHTTPError`), 429=`RateLimitError`로 분리·재시도, Retry-After 우선+없으면 지수백오프+jitter(cap60), model별 global cooldown(`limiter.set_cooldown`)로 연쇄429 차단, 최종실패 로그에 본문·모델·attempt·sleep. 그리고 ★ 쿼터/권한 최종실패는 `RPDExceeded`처럼 회차를 멈춤 — 가짜 exit=-1 칸으로 데이터 오염하던 것 차단(§3). limiter 자가검증 8케이스 통과. 단 실호출 HTTP 분기는 미실행(키·네트워크 부재, 코드리뷰만).

후보:

1. **Q8 새 회차 — vtx_26~28** ★ 추천. 분류 갭을 메웠으니 다시 누적. 이제 관측 포인트는 (a) vtx_20/22류 AST 스키마 불일치 재현 여부, (b) vtx_23_D2류 문법/데이터계약 추가 발생 여부, (c) JSON stdin은 inputmismatch로 자동 분리되는지 회귀 확인.
1. **★ 인증경로/쿼터 확정(§13 미결, 근본 원인 후보)** — client.py가 `aiplatform.googleapis.com`에 `?key=`로 호출 중. 정식 Vertex는 OAuth/서비스계정 요구 → 이 키 경로가 유료 1티어 project quota를 안 타고 별도 버킷에 묶였을 가능성. GCP 콘솔 Quotas에서 generativelanguage vs aiplatform 어디에 사용량 찍히는지 + 1티어 결제프로젝트와 키 발급프로젝트 일치 여부 확인. 필요시 client.py를 OAuth+`projects/<id>/locations/<region>/...` 정식 경로로 전환(인증 수정은 §3 ‘깸 줄이는 수정’ 경계 밖 — 인프라).
1. **남은 분류 갭** — `H1B_IMPORT`/`H1B_SIGNATURE` 분리, `TIMEOUT_REAL` vs STDIN_EXIT, `RUNTIME_EXCEPTION` 통일. 데이터가 호명할 때만.

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

- `github.com/BN8624/aaa` (main). tip은 웹 Edit로 자주 바뀜 → 폰 `git fetch && git reset --hard origin/main`로 맞출 것. 직전 작업: analyzer/verify 분류 갭 보강, vtx_23~25 재분석, FINDINGS §15, handoff 갱신(2026-06-09).
- 회차완료 알림: `DISCORD_WEBHOOK_URL` 환경변수 설정 시 봇이 회차 끝에 요약 1회 POST(미설정 시 자동 skip). 키처럼 취급 — 커밋 금지. → 정본 §10.
- 모델: 전 역할 gemini-3.5-flash, Vertex REST, 키 VERTEX_API_KEY. → 정본 3장.
- 핵심 도구: `analyze_h1b.py`(관측 — 정적 cat + **verify_channel 재실행 runstate 통합**, rows.csv/summary.json/report.txt에 alive/reject/broken/silent/inputmismatch+채널+cat×runstate 교차표; `--no-replay`로 정적만), `verify_channel.py`(재실행 분류 본체, 단독도 가능), `arun.sh`(회차 자동화+pull+analyze, analyze가 재실행 포함). ★Windows는 UTF-8 강제됨(cp949 크래시 수정 완료).
- 읽기: repo 검색 안 됨 → `git clone` 후 task_id로 runs.jsonl grep (가장 확실), 또는 raw URL(push 후 1~2분 CDN 지연).

-----

*이 문서가 길어지면 잘못된 것 — 정의·근거가 새어든 것이니 정본으로 도로 밀어낼 것.*
