# aaa — HANDOFF (작업용)

## 2026-06-09 H4 Docker h4_5 완료 — 유효 Docker 회차 2회차

- 최신 커밋: bot push (h4_5).
- **유효 Docker 회차 누적: h4_3(첫 10칸) + h4_5(10칸) = 20칸, H1b=0.**
- h4_5: exit=125 0건. exit0가짜 9 / inputmismatch 1(A2, argparse). H1b=0.
- h4_3·h4_4 무효 경위: Claude Code subprocess로 봇 재시작(PID 28908) → Docker pipe 권한 미상속. → FINDINGS §18.
- **운영 원칙 추가**: Docker 사용 시 봇 재시작 방법 — ①코드 업데이트 후: Discord `/업데이트`(`os.execv`로 프로세스 교체 → Docker 권한 유지). ②봇이 완전히 죽었을 때: 사용자가 직접 PS 터미널에서 `restart_bot2.ps1`. Claude Code `Start-Process` 재시작 금지(Docker 권한 미상속).

> 이 문서 = 살아있는 현재 상태만. **얇게 유지(1~2화면).** 정의·명세·근거는 베끼지 않고 가리킨다.
> 
> - 왜·무엇·구현 명세·가설 정의 → **정본 `work_unified.md`**
> - 회차별 날 사실(rows·코드 대조) → **repo `FINDINGS.md`**
> - 여기엔: ①현재 위치 ②다음 한 수 ③작업 체크리스트 만.
>   기준일 2026-06-09.

-----

## 1. 현재 위치

- **H1 (a/b/c) 종료.** H1b = 부재(Gemini 누적 표면 0, 진짜 부재 다중 확인). vtx_13~30 유효 회차 **150칸 연속 H1b 0** + **h4_3 Docker 10칸 H1b 0 추가** → 총 160칸. → FINDINGS §1~18.
- **Q7 (왜 dict 수렴) 종료, 단 미세수정.** 주류는 dict/list 경계라 멤버 계약 충돌 구조적 미발생. → FINDINGS §15.
- **Q8 (실패=실행채널 문제?) 종료.** vtx_26~30 50칸 회귀, broken 0, H1b 0. → FINDINGS §16.
- **H4 Docker 유효 회차 2회 완료(h4_3·h4_5).** 20칸 H1b=0. 관측 천장(stdin 미연결) 여전히 유효. → FINDINGS §18·§19.
- 보류: H2(모델 통일로 비교군 소멸). 미착수: H3. → 정본 리스크 레지스터.

## 2. 다음 한 수 (하나만 고르고 그것만)

직전 완료(2026-06-09): ①~⑨(vtx 시리즈, Q8 종료) ✅ ⑩H4 Docker 구현 ✅ ⑪h4_3 최초 유효 Docker 회차(H1b=0) ✅ ⑫h4_3(2차)·h4_4 무효(봇 재시작 권한 문제) ✅ ⑬봇 재시작 운영 원칙 확립 ✅ ⑭h4_5 유효 회차(H1b=0) ✅ ⑮FINDINGS §18·§19 기록 ✅.

★ §13 수정 핵심(client.py·limiter.py·run.py·batch.py): 400/401/403/404=재시도금지(`PermanentHTTPError`), 429=`RateLimitError`로 분리·재시도, Retry-After 우선+없으면 지수백오프+jitter(cap60), model별 global cooldown(`limiter.set_cooldown`)로 연쇄429 차단, 최종실패 로그에 본문·모델·attempt·sleep. 그리고 ★ 쿼터/권한 최종실패는 `RPDExceeded`처럼 회차를 멈춤 — 가짜 exit=-1 칸으로 데이터 오염하던 것 차단(§3). limiter 자가검증 8케이스 통과. 단 실호출 HTTP 분기는 미실행(키·네트워크 부재, 코드리뷰만).

후보:

1. **H4 추가 회차(h4_6~) 누적** ★ 추천. 현재 20칸(h4_3+h4_5). 최소 3~5회차 더 쌓아야 비결정적 패턴 강화. `/도커실행 h4_6` 등. 봇 재시작 필요 시 `/업데이트`(Docker 권한 유지) 또는 사용자 직접 PS에서 restart_bot2.ps1.
   - **보류: argparse/sys.argv inputmismatch** — runner가 `python main.py` 인수 없이 실행 → argparse 프로그램 항상 exit=1 inputmismatch. vtx(host)도 동일 한계. 빈도 관측 후 수정 판단.
1. **★ 인증경로/쿼터 확정(§13 미결, 근본 원인 후보)** — client.py가 `aiplatform.googleapis.com`에 `?key=`로 호출 중. 정식 Vertex는 OAuth/서비스계정 요구 → 이 키 경로가 유료 1티어 project quota를 안 타고 별도 버킷에 묶였을 가능성. GCP 콘솔 Quotas 확인.
1. **H3/known_failures 실험 설계** — 되돌림 루프를 켜야 하므로 Docker 관측층 뒤가 자연스럽다.

## 3. 작업 체크리스트 (까먹지 말 것 — 정의는 정본/아래 참조)

회차 돌리기 전:

- [ ] **키 확인**: `echo $VERTEX_API_KEY` (미설정 시 files=[]·exit=-1 가짜 행 오염)
- [ ] **새 tag**: `<세션>_<회차>` 형식, `_숫자_` 유지(analyze 정규식 요구). 부분/실패 tag 재사용 금지 → 새 번호.
- [ ] **한글 파일(batch.py TASKS) 편집은 GitHub 웹 Edit** — 폰 sed 금지(인코딩 깨짐, vtx_11·12 무효 전례). 편집 후 폰에서 `git fetch && git reset --hard origin/main`.

돌리기:

- `/실행 <tag>` 또는 `/연속실행 vtx_28 vtx_29 vtx_30` (Discord). `python3 -u batch.py`만 쓰면 rows.csv 안 생김.
- **0실행 빈손 push 주의**: batch 미실행인데 빈 analysis push되는 사고(vtx_18). 결과 확인 = runs.jsonl에 해당 tag 행 ≥1.

절대 제약 (→ 정본, 자연발생량 관측 중이라 엄수):

- planner/coder 프롬프트로 모델 행동 제약 금지.
- expected_type(A~E 라벨) planner에 넘기기 금지.
- 깸을 *줄이는* 수정 금지(계측기는 데이터가 호명할 때만).
- 한 번에 한 곳/한 변수만. 단일 회차로 판정 금지(비결정적, 누적 필요).

## 4. repo 상태 · 읽는 법

- `github.com/BN8624/aaa` (main). tip은 웹 Edit로 자주 바뀜 → 폰은 Discord `/업데이트`로 pull+봇재시작 가능. 직전 작업: vtx_26~30, `/연속실행`, webhook UA, FINDINGS §16, handoff 갱신(2026-06-09).
- 회차완료 알림: `DISCORD_WEBHOOK_URL` 환경변수 설정 시 봇이 회차 끝에 요약 1회 POST(미설정 시 자동 skip). 키처럼 취급 — 커밋 금지. → 정본 §10.
- 모델: 전 역할 gemini-3.5-flash, Vertex REST, 키 VERTEX_API_KEY. → 정본 3장.
- 핵심 도구: `analyze_h1b.py`(관측 — 정적 cat + **verify_channel 재실행 runstate 통합**, rows.csv/summary.json/report.txt에 alive/reject/broken/silent/inputmismatch+채널+cat×runstate 교차표; `--no-replay`로 정적만), `verify_channel.py`(재실행 분류 본체, 단독도 가능), `arun.sh`(회차 자동화+pull+analyze, analyze가 재실행 포함). ★Windows는 UTF-8 강제됨(cp949 크래시 수정 완료).
- 읽기: repo 검색 안 됨 → `git clone` 후 task_id로 runs.jsonl grep (가장 확실), 또는 raw URL(push 후 1~2분 CDN 지연).

-----

*이 문서가 길어지면 잘못된 것 — 정의·근거가 새어든 것이니 정본으로 도로 밀어낼 것.*
