# aaa — HANDOFF (작업용)

## 2026-06-09 h4_12~15 — 일시적 429(회복됨), §13 정지 실전 발화 / 재개 가능

- 최신 커밋: `9bd76c6 run h4_15`. FINDINGS §28 기록.
- **★ 차단(§28)**: h4_11 직후 h4_12 중반(C2)에서 429 RESOURCE_EXHAUSTED → §13대로 배치 중단. h4_13~15 각 A1에서 즉시 429 → 전량 무효. **h4_12는 부분/폐기**(5칸 H1b=0 사실만, 회차 불침).
- **유효 Docker 누적: 70칸 유지(h4_11까지), 증가 없음.** H1b=0.
- **§13 쿼터 정지 실호출 첫 발화 확인**: 429 fake가 `코더빈손`/fake로 분류, run_h1b 0 — H1b 오염 0. 인프라 거부를 모델 실패로 위장 안 함이 실전 작동.
- **★ 429 진단 해소(§28, probe_endpoints.py)**: **일시적 429였음 확정 — 영구 벽 아님.** 프로브: generativelanguage(AI Studio)=403 blocked, aiplatform(Vertex, 현재 코드)=200 정상. → 엔드포인트 교체·무료버킷 가설 폐기, 코드 경로 맞음. AI Studio quota(RPM1k 등)는 미적용 숫자(403). 실제 한도=Vertex quota(미확인). **aiplatform 200 = 이미 회복.**
  - **Vertex 실측 한도 매우 낮음(probe_quota.py)**: 16토큰 콜 연사 → 7번째 429(성공 6 / 14.8s). 429 본문에 metric·limit 없음(generic) → 콘솔 없이 숫자 못 얻음, 경험값 ~6 버스트가 전부. 정체 = `?key=`→aiplatform 저quota express 접근(빌링으로 안 올라감). "무료버킷"→"저quota" 정정.
  - **조치(B 적용, 커밋됨)**: limiter에 `min_interval`(콜 간 간격) 추가, production = `Limiter(rpm=8, min_interval=4.0)`; client `max_retries` 5→8. 버스트 차단 + 잔여 429를 backoff로 흡수 → 회차 안 죽고 완주. limiter 자가검증 [9][10] 추가, 10/10 통과. 인프라만, 모델 동작 불변.
  - **운영**: `/도커실행 h4_16` 한 개씩(여전히 /연속도커 남발 금지). 근본책(C, 보류) = 정식 Vertex 인증(SA+OAuth+projects/locations 경로)로 실제 quota 획득.
- **§26 argv=["1"] 검증 성공(§27)**: A2·C1·C2·D2 alive 회복, DATA_CONTRACT_GRAMMAR 부작용 0. C lexer→parser→evaluator 채널 개방.
- **E1 데이터계약 H1c 첫 관측(§27)**: summarize_components dict 키 ↔ main 'representative' 기대 불일치 → KeyError. §12·§14 패밀리 E 도메인 첫 출현. H1b 아님. **아직 단일 사례**(C 채널 열린 뒤 재현 관측은 쿼터로 중단됨).
- **B1·B2 메뉴앞EOF 반복(§28)**: DUMMY_STDIN(12행) 긴 메뉴에 소진. 깸 아님이나 반복 패턴 → 확장 호명됨.
- h4_9: Docker Access Denied 재발 → 예약 작업으로 근본 해결(§23).
- **봇 재시작 운영 원칙 갱신(§23)**:
  - `/업데이트` — pull + 예약 작업 재시작(Docker 권한 보장). 표준.
  - `/재시작봇` — pull 없이 재시작만(권한 복구 전용).
  - `restart_bot2.ps1` 직접 실행 — 비상용만.
- **관측 천장 해소(§24)**: runner.py `argv` 파라미터 추가, `DUMMY_ARGV=["test input"]`, DUMMY_STDIN 확장, `gen_stdin=False`.
  - 효과: argparse inputmismatch 0건(h4_5에서 1건 → h4_10에서 0건). A2 정상 진입 확인.
  - 부작용: 표현식 파서(C1·C2·D2)가 `"test input"`을 expression으로 파싱 실패. **→ §26에서 `DUMMY_ARGV=["1"]`로 해결**(미커밋, h4_11로 검증 예정).

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
- **H4 Docker 유효 6회차 완료.** 60칸 H1b=0. → FINDINGS §18~§25.
- **관측 천장 해소**: argv 주입으로 argparse 진입 확인. 표현식 파서 부작용은 `DUMMY_ARGV=["1"]`로 해결(§26, h4_11 검증 대기).
- 보류: H2(비교군 소멸). 미착수: H3. → 정본 리스크 레지스터.

## 2. 다음 한 수 (하나만 고르고 그것만)

직전 완료(2026-06-09): ①~㉓ ✅ ㉔h4_12~15 쿼터 소진 — §13 정지 실전 발화, h4_12 부분/폐기·13~15 무효(§28) ✅.

★ §13 수정 핵심(client.py·limiter.py·run.py·batch.py): 400/401/403/404=재시도금지, 429=재시도+백오프, 최종실패 시 배치 중단. **h4_12 C2에서 실전 발화 확인** — 429 fake/코더빈손 분류, H1b 오염 0.

쿼터 차단 해소됨(§28 프로브 — 일시적이었고 회복). 바로 재개 가능.

후보(하나만):
1. **h4_16+ 누적 ★ 추천** — 새 tag로 `/도커실행 h4_16` 또는 `/연속도커 h4_16 h4_17`(2개씩 끊어 순간 429 회피). C 채널 열린 뒤 §12·§14 AST·E1식 데이터계약 H1c 재현 관측이 목표(현재 단일 사례). H1b 누적도 계속. **이 다회차 데이터가 H4 vs H3 전환 판단의 근거.**
2. **H3/known_failures 실험 설계** — 관측→개입 국면 전환. h4_16+로 C 채널 다회차 보고 H4 포화 확인 뒤가 깨끗.
3. (재발 시만) Vertex 콘솔 quota 확인·limiter 실값 갱신.

## 3. 작업 체크리스트 (까먹지 말 것)

회차 돌리기 전:

- [ ] **키 확인**: `echo $VERTEX_API_KEY` (미설정 시 files=[]·exit=-1 가짜 행 오염)
- [ ] **새 tag**: `<세션>_<회차>` 형식, `_숫자_` 유지(analyze 정규식 요구). 부분/실패 tag 재사용 금지 → 새 번호.
- [ ] **봇 재시작 필요 시**: `/업데이트`(pull+재시작) 또는 `/재시작봇`(재시작만). 둘 다 예약 작업 경유 → Docker 권한 보장.
- [ ] **한글 파일(batch.py TASKS) 편집은 GitHub 웹 Edit** — 폰 sed 금지(인코딩 깨짐).

돌리기:

- `/도커실행 <tag>` 또는 `/연속도커 h4_11 h4_12` (Discord).
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
