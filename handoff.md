# aaa — HANDOFF (작업용)

## 2026-06-09 현 상태 — h4_16 돌릴 준비 완료 (B 적용 + 봇 수정 끝)

- 최신 커밋: `fd8d3df`. 봇 현재 생존·Discord 연결됨(예약 작업 경유, Docker 권한 보장).
- **유효 Docker 누적 70칸 H1b=0**(h4_11까지). vtx 150 + Docker 70 = **220칸 H1b=0.**
- **h4_12~15 = 무효/폐기(§28)**: 일시적 429로 중단. h4_12 부분(5칸)·13~15 전량 무효. 429는 회복됨(프로브 확정). 누적 증가 없음.
- **저quota 대응 B → 재검증으로 정정(§28)**: 4초 페이싱 재프로브도 7번째 429(6건/30.5s) → **버스트 아니라 분당 ~6 고정 저캡** 확정. B의 rpm=8/min_interval=4는 캡 위라 부족 → **`Limiter(rpm=5, min_interval=12.0)`로 정정**(≈5/min). `client max_retries=8`. **h4_16 전 `python probe_quota.py 10 12`로 12초 지속 통과 먼저 확인.** 통과 못 하면(창>60s) 정식 Vertex 인증(SA+OAuth, C안)이 유일. → **`/도커실행` 1개씩**, /연속도커 금지.
- **봇 2중 사망버그 수정(§29)**: 작업 `StopOnIdleEnd=false`(PC 유휴해제 시 ~30초 사망) + `MultipleInstances=Parallel`(/재시작봇이 자기만 죽이던 IgnoreNew). Task Scheduler 설정이라 repo 밖이었으나 → **`register_bot_task.ps1`로 백업 완료**(작업 삭제/기계 재구성 시 한 줄 복구, §29).
- **관측 본류(§26·§27)**: `DUMMY_ARGV=["1"]`로 C lexer→parser→evaluator 채널 개방(C1·C2·A2·D2 alive 회복). **E1 데이터계약 H1c 첫 관측**(§12·§14 패밀리 E 도메인 출현) — 아직 단일 사례, C 채널 다회차 재현이 h4_16+의 핵심 관측 목표.

> 이 문서 = 살아있는 현재 상태만. **얇게 유지(1~2화면).** 정의·명세·근거는 베끼지 않고 가리킨다.
>
> - 왜·무엇·구현 명세·가설 정의 → **정본 `work_unified.md`**
> - 회차별 날 사실(rows·코드 대조) → **repo `FINDINGS.md`**
> - 여기엔: ①현재 위치 ②다음 한 수 ③작업 체크리스트 만.
>   기준일 2026-06-09.

-----

## 1. 현재 위치

- **H1 (a/b/c) 종료.** H1b = 부재. vtx_13~30 150칸 + Docker 70칸(h4_3·h4_5·h4_6·h4_7·h4_8·h4_10·h4_11) → **누적 220칸 H1b=0.** → FINDINGS §1~§27.
- **Q7 (왜 dict 수렴) 종료.** → FINDINGS §15.
- **Q8 (실패=실행채널?) 종료.** → FINDINGS §16.
- **H4 Docker 유효 7회차 완료.** 70칸 H1b=0. → FINDINGS §18~§27.
- **관측 천장 해소**: `DUMMY_ARGV=["1"]`로 argparse·표현식파서(C·D) 둘 다 진입. C 파서 체인 채널 개방 확인(§26·§27).
- **Vertex 저quota 대응 완료(B)** + **봇 사망버그 수정(§28·§29)**. 인프라 안정화됨.
- 보류: H2(비교군 소멸). 미착수: H3. → 정본 리스크 레지스터.

## 2. 다음 한 수 (하나만 고르고 그것만)

직전 완료(2026-06-09): ①~㉔ ✅ ㉕h4_12~15 무효(429)·진단해소(§28) ✅ ㉖봇 2중 사망버그 수정(§29) ✅ ㉗저quota 재검증 = 분당 ~6 고정캡 확정, B는 부족 판정(§28) ✅ ㉘C안 코드 구현 = 이중 인증(§30) ✅.

**바로 다음(게이트): 정식 Vertex 인증(C안) 자격 갖추기.** express는 분당 ~6 + 느린 회복이라 배치 회차 불가 확정(§28). 코드는 준비됨(§30) — 환경변수 3종 갖추면 자동 전환. h4_16은 그 뒤.

**C안 콘솔 절차(폰 브라우저 가능, console.cloud.google.com):**
1. 우상단 프로젝트 선택 → 기존 프로젝트 쓰거나 **새 프로젝트** 생성. **결제 계정 연결**(없으면 Billing에서 추가).
2. 검색창 "Vertex AI API" → **사용(Enable)**.
3. 검색창 "서비스 계정" → **서비스 계정 만들기**(이름 아무거나) → 역할 **`Vertex AI User`** 부여 → 완료.
4. 만든 SA 클릭 → **키 → 키 추가 → 새 키 → JSON** → 다운로드. 이 파일을 기계 `C:\Users\USER\aaa\vertex-sa.json`로.
5. 환경변수(`.env` 또는 시스템): `GOOGLE_APPLICATION_CREDENTIALS=C:\Users\USER\aaa\vertex-sa.json`, `VERTEX_PROJECT=<프로젝트ID>`, `VERTEX_LOCATION=us-central1`.
6. 기계에서 `pip install -r requirements-vertex.txt`(google-auth).
7. 검증: `python client.py`(1콜 통과) → `python probe_quota.py 30`(연사 30콜 통과 기대, express 6캡 탈출 확인).
8. 통과하면 **`/도커실행 h4_16`** — 이제 완주율 논쟁 없이 정식 quota로 누적.

그 뒤 후보(하나만):
1. **h4_16+ 누적 ★ 추천** — §12·§14 AST·E1식 데이터계약 H1c **재현 관측이 목표**(현재 단일 사례). H1b 누적도 계속. **이 다회차 데이터가 H4 vs H3 전환 판단의 근거.**
2. **H3/known_failures 실험 설계** — 관측→개입 국면 전환. h4_16+로 C 채널 다회차 보고 H4 포화 확인 뒤가 깨끗.

(SA 자격을 못 갖추는 동안만 임시로) express 폴백으로 limp: 이미 `rpm=5/min_interval=12`로 조여둠 — 단발 호출은 되나 회차는 느리고 깨지기 쉬움.

## 3. 작업 체크리스트 (까먹지 말 것)

회차 돌리기 전:

- [ ] **키 확인**: `echo $VERTEX_API_KEY` (미설정 시 files=[]·exit=-1 가짜 행 오염)
- [ ] **새 tag**: `<세션>_<회차>` 형식, `_숫자_` 유지(analyze 정규식 요구). 부분/실패 tag 재사용 금지 → 새 번호.
- [ ] **봇 재시작 필요 시**: `/업데이트`(pull+재시작) 또는 `/재시작봇`(재시작만). 둘 다 예약 작업 경유 → Docker 권한 보장.
- [ ] **봇 완전사망(무응답) 시**: `/재시작봇`·`/업데이트`는 봇이 처리하는 명령이라 **못 씀**(닭-달걀). → Windows에서 직접 `schtasks /run /tn AAABotRestart`. (§29 — StopOnIdleEnd가 봇을 ~30초 만에 죽이던 건 수정 완료.)
- [ ] **작업 자체가 사라졌거나 설정이 틀어졌을 때**: 관리자 PowerShell에서 `powershell -ExecutionPolicy Bypass -File .\register_bot_task.ps1 -Run` — 올바른 설정(§29: StopOnIdleEnd/RunOnlyIfIdle/RestartOnIdle=false, MultipleInstances=Parallel, LogonType Interactive)으로 재등록+기동.
- [ ] **한글 파일(batch.py TASKS) 편집은 GitHub 웹 Edit** — 폰 sed 금지(인코딩 깨짐).

돌리기:

- `/도커실행 <tag>` (Discord). **저quota라 한 개씩** — `/연속도커` 남발 시 순간 429로 회차 중단 위험(§28).
- **0실행 빈손 push 주의**: 결과 확인 = runs.jsonl에 해당 tag 행 ≥1.

절대 제약 (→ 정본, 자연발생량 관측 중이라 엄수):

- planner/coder 프롬프트로 모델 행동 제약 금지.
- expected_type(A~E 라벨) planner에 넘기기 금지.
- 깸을 *줄이는* 수정 금지(계측기는 데이터가 호명할 때만).
- 한 번에 한 곳/한 변수만. 단일 회차로 판정 금지(비결정적, 누적 필요).

## 4. repo 상태 · 읽는 법

- `github.com/BN8624/aaa` (main). `/업데이트`로 pull+봇재시작 가능(예약 작업 경유, Docker 권한 보장).
- 회차완료 알림: `DISCORD_WEBHOOK_URL` 환경변수 → 봇이 회차 끝에 요약 POST.
- 모델: 전 역할 gemini-3.5-flash, Vertex REST, 키 VERTEX_API_KEY. → 정본 3장.
- 핵심 도구: `analyze_h1b.py`, `verify_channel.py`, `arun.sh`. ★Windows UTF-8 강제.
- 읽기: `git clone` 후 task_id로 runs.jsonl grep.

-----

*이 문서가 길어지면 잘못된 것 — 정의·근거가 새어든 것이니 정본으로 도로 밀어낼 것.*
