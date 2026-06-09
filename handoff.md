# aaa — HANDOFF (작업용)

## 2026-06-09 h4_11 완료 — argv=["1"] 검증 성공 / E 도메인 데이터계약 H1c 첫 관측

- 최신 커밋: `daf5284 run h4_11`. FINDINGS §27 기록.
- **유효 Docker 누적: h4_3(첫10)+h4_5+h4_6+h4_7+h4_8+h4_10+h4_11 = 70칸, H1b=0.**
- **§26 argv=["1"] 검증 성공(§27)**: A2 argparse·C1·C2 표현식파서·D2 모두 alive로 회복. `"test input"` DATA_CONTRACT_GRAMMAR 부작용 0건. C lexer→parser→evaluator 체인 완주 확인 — 관측 채널 개방.
- **★ E1 데이터계약 H1c 첫 관측(§27)**: summarize_components dict 키 ↔ main의 'representative' 키 기대 불일치 → KeyError. §12·§14 AST 패밀리가 C 넘어 E 그래프 도메인서 첫 출현. H1b 아님(H1c).
- h4_9: Docker Access Denied 재발 → 전량 무효. 예약 작업으로 근본 해결(§23).
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

직전 완료(2026-06-09): ①~㉒ ✅ ㉓argv=["1"] 검증 성공 — h4_11 유효, C·D 채널 개방·E1 데이터계약 H1c 첫 관측(§27) ✅.

★ §13 수정 핵심(client.py·limiter.py·run.py·batch.py): 400/401/403/404=재시도금지, 429=재시도+백오프, 최종실패 시 배치 중단. h4_10 E2에서 정상 동작 확인.

관측 천장 도구(argv+DUMMY_STDIN) 안정화됨. 남은 소소한 갭: DUMMY_STDIN이 긴 메뉴(7옵션+)엔 짧아 B2류 메뉴앞EOF 잔존(§27). 깸 아님 — 늘릴지는 데이터가 호명할 때만.

후보(하나만):
1. **h4_12+ 누적 ★ 추천** — `/도커실행`/`/연속도커`. C 채널 열렸으니 §12·§14 AST 스키마 H1c·E1식 데이터계약 H1c가 더 잡히는지 관측(현재 단일 사례). H1b 누적도 계속.
2. **H3/known_failures 실험 설계** — Docker 관측층 안정화됐으니 자연스러운 다음 축.
3. **Vertex 인증경로/쿼터 정식화(§13 미결)** — 1티어 실제 적용 여부.

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
