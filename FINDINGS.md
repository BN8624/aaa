# FINDINGS — aaa 살아있는 발견 (raw로 Claude가 읽음)

> 날 사실만. 해석·가설은 aaa_progress.md. 기준 2026-06-06(PT).

## §1 정의

- H1b = 파일 간 계약 파괴(import/시그니처/멤버(AttributeError)/unhashable/NameError).
- H1c = 런타임 값예외(계약 멀쩡). timeout = 20s 초과.
- 관측가능 3상태: 관측됨 / 관측불가(메뉴앞EOF·argparse·코더빈손) / 불명(exit0가짜).

## §2 핵심 (두 세션 재현)

- H1b 6~9%, D·E 집중, AttributeError 최다, 비결정적. py_compile은 다 통과.
- 관측 천장: 대부분 “H1b 없음”이 아니라 “볼 기회조차 없음”. 핵심 지표 = H1b / 관측가능.

## §3 H2 (stdin 주입 길1)

- runner에 stdin_input. client.py 5xx 재시도(is_retryable) f272b02로 복구.

## §4 H4 = 길B (scripter 대본)

- scripter v2: 코드+acceptance 읽고 stdin 대본 생성. expected 안 봄, runner stdin에만.
- h4b_1: H1b 0/10, 대본 짧아 B·C EOFError로 굶음.
- h4b_3: 절반 5xx로 죽음(client fix 전·무효), 메뉴앞EOF 0.

## §5 probe_1780746513 (client fix 후 첫 깨끗한 회차, 10실행)

- 집계: exit0가짜 7 / argparse 2(A1·A2) / H1c 1(D2) / H1b 0 / 메뉴앞EOF 0 / 코더빈손 0.
- 코더빈손 0 = client 5xx fix 검증됨(10/10 코드 생성·실행).
- ★ exit0가짜가 두 부류로 갈린다(과거 r0604 stderr로 확증):
  - 메뉴형(B·C, while True + input()): stdin 굶으면 EOFError 또는 exit0가짜로 수렴.
  - 데모형(D·E, run_demo()/run_simulation() 등 input 없음): stdin 무관하게 정상 exit0.
- ★ 길B는 D·E 데모형에 구조적으로 무력: coder가 D·E를 input 없는 자족 스크립트로 생성
  → stdin 주입이 닿을 데 없음. D·E의 exit0가짜는 “불명”이 아니라 사실상 “관측됨”에 가까움
  (멤버 계약 가로질러 실행 완료; H1b 터질 거면 stderr에 떴을 것).
- D2 증거: ValueError(user_88 not found) — main→point_service→repository 3파일 체인 실제 도달.
- 메뉴앞EOF=0의 실제 원인: 데모형은 애초에 EOF 안 냄, 메뉴형은 대본이 exit까지 끌고 감. 둘 다 exit0가짜로 수렴.
- ★ stdin 로깅 호명됨: exit0가짜가 “굶음”인지 “완주”인지 stderr만으론 영구 구분 불가
  → run.py(주입 시) + state.py(dump 시) 별도 깨끗한 변경으로.

## §6 vtx1 (Gemini 3.5 Flash 첫 회차, 2026-06-06)

- 전환 후 첫 깨끗한 회차. 10칸 전부 코드 생성(코더빈손 0).
- ★ 메뉴앞EOF 4→0: Gemma는 input()맨몸→EOF즉사였으나, Gemini는 input을 try/except (EOFError)로 감싸 “Goodbye!” 후 정상 break. → 죽지 않지만 메뉴 루프 0바퀴, 파일상호작용 미실행 = exit0가짜(불명).
- 즉 관측천장의 정체가 “메뉴앞EOF(죽음)“→”exit0가짜(우아한 무동작)“로 이동. 관측가능률은 여전히 낮음(B·C 4칸 불명).
- H1b 표면상 0. 단 E1은 H1c(create_user가 role 도메인 {admin,user,guest}인데 main이 ‘editor’/‘viewer’ 주입→ValueError)이고, 그 뒤 user.get() vs dataclass 반환 불일치(H1b)가 잠복(도달 전 사망).
- ★ 함의: H4(stdin 대본)이 Gemini에서 처음 쓸모 가능. B1은 데모형이 아닌 진짜 메뉴형이라, 대본 주입 시 EOF로 안 죽고 메뉴를 실제로 돌 가능성 → D·E 아닌 B·C에서도 계약 실행 관측 기회.
- 주의: tag ‘vtx1’은 analyze 정규식(*숫자*) 불일치로 rows.csv 빈값. 다음부터 ‘vtx_2’ 형식.

## §7 vtx_2~10 (Gemini 3.5 Flash 누적 9회차, 2026-06-06)

- 데이터 무결성: runs.jsonl에 vtx_ 170행 중 80행이 VERTEX_API_KEY 미설정 가짜(files=[], exit=-1, stderr “VERTEX_API_KEY 환경변수가 없다”). 키 없이 한 번 돌고 export 후 재실행한 흔적(약 17분 간격). 가짜 걷으면 9회차x10칸=90 진짜 실행, 빠진 칸·중복 없음. vtx_2는 키실패 0. analysis_out/에 vtx_ 디렉토리 없음 = arun.sh 안 거치고 batch.py 직접 실행됨(rows.csv 미생성). 집계는 runs.jsonl 직접 계산.
- 표면 H1b = 0/90. 분류: exit0 76 / H1c 7 / argparse 6 / timeout 1.
- D·E exit0 34칸 전부 logged-stdin 재생 시 계약 가로질러 완주(삼켜진/도달전 H1b 없음).
- vtx1 E1의 잠복 H1b(dict vs dataclass) 재현 안 됨: 9회차 E1 전부 @dataclass 미사용, dict 수렴으로 멤버 계약 충돌 자체가 발생 안 함. “더 깊이 숨긴다”(vtx1 가설)는 이번 누적으로 반증에 가까움.
- 새 발견 — 오류의 채널 이동: exit0 79칸 중 24칸이 오류를 stderr 예외가 아니라 stdout 반환값으로 삼킴. 예: {‘success’:False,‘error’:…} / Unauthorized / Insufficient stock / Payment failed. 코드 신호: broad except Exception 47/90, except->print 62/90. 강한 모델은 계약위반·값오류를 raise가 아니라 return으로 처리. H1b/H1c가 사라진 게 아니라 예외->반환값, stderr->stdout으로 이동했을 가능성.
- 관측 천장 3차 이동: (1)메뉴앞EOF(죽음) -> (2)exit0가짜(우아한 무동작, vtx1) -> (3)예외->반환값(오류 삼킴, vtx_2~10). 이제 반환값/stdout 의미검증 없이는 깸 관측 불가.
- 인과 교란 명시: 모델(Gemma->Gemini)과 파이프라인(H4 대본·stdin로깅) 동시 변경. Gemma 대조회차 미수행 -> “H1b 감소가 모델 탓”이라 단정 못 함.

## §8 Q5 — 삼킨 24칸 분류 (코드 변경 0, runs.jsonl 재생, 2026-06-07)

- 방법: vtx_2~10 가짜 80행 제외 → 진짜 90칸, exit0 79칸. 삼킴 신호로 ≈21칸 좁힘(§7의 24와 동일 현상). generated_files 직독 + import 정합 대조로 H1b/H1c 분류.
- 결과: 삼킨 오류 중 H1b = 0건. 자동분류 H1b 후보 2건은 다중행 import 괄호 오인 거짓양성(직독 시 계약 정합).
- 나머지 전부 H1c/의도된 정상 도메인 거부(Unauthorized·Insufficient·not recognized). stdin이 실제 메뉴 주행이라 코드는 돌고 정당히 거부함.
- 분포: C·D·E 편중, A·B 거의 없음.
- 해석(Q5 답): 삼킴 = 숨은 H1b 아님. dict 수렴으로 H1b 애초 미발생(vtx1 E1 비재현과 일치). 표면 H1b 0은 채널 은폐보다 진짜 부재. §7 “예외→반환값” 가설은 H1c엔 맞지만 H1b 사례 0.
- Q6 함의: 검증기로도 건질 숨은 H1b 없음 → “정상 거부 vs 진짜 깸” 구분 관측 도구로 재설정.

## §9 Q6 — verify_channel.py 첫 실측 (2026-06-07)

- 도구: 파이프라인 분리 관측기. generated_files 임시폴더 재생 + 로깅된 stdin 주입 → stdout/stderr/exit 실측, 4상태(alive/reject/broken/silent) + 채널(stderr-exc/stdout-return/silent) 판정.
- vtx_2~10 exit0 79칸 전수: broken 0, reject 25(전부 stdout-return), alive 54(stdout-ok), silent 0.
- 의미: §8의 “삼킨 ≈21~24 = 전부 정상 도메인 거부”를 추론→실측으로 확정. 깸 채널(broken) 비어 있음. progress §5 새 지표 첫 값.
- 함의: 검증기는 H1b 사냥기 아님이 실증됨(잡을 broken 없음). “정상 거부 vs 진짜 깸” 구분 관측 도구로 위치 확정.

## §10 vtx_11~13 + 타입계약 도메인 실험 (2026-06-07)

- 동기: §8·§9에서 “표면 H1b 0이 채널은폐냐 진짜부재냐” 미결. 가르기 위해 과제 도메인을 dict로 충분한 영역(권한·재고·포인트)에서 타입계약이 자연스러운 영역(좌표·벡터·행렬·입자·상태기계)으로 교체. ★결합도 A~E·라벨·구조 유지, 자료구조는 미지정(유도 아님, 관측).
- 운영 주의: vtx_11·vtx_12는 batch.py TASKS 교체가 실제 반영 안 된 채 돎(폰 sed 한글 인코딩 실패 + push 누락) → 둘 다 옛 과제 회차. 무효는 아니고 H1b 0 누적엔 보탬이나 도메인 실험 아님. vtx_13에서 GitHub 웹 직접 교체로 반영 확인(E1=“3D 변환”) 후 유효.
- 부수 사고: FINDINGS.md 실수 삭제(commit b39d490) → 직전 79e3cb5에서 복구. §1~9 손실 0.
- ★ 핵심 결과(vtx_13, 진짜 타입계약 도메인): H1b 0/10. 벡터·4x4행렬·물리·상태기계에서도 모델이 전부 list/dict로 표현, dataclass·class·namedtuple 0개. 멤버접근(.x/.matrix) 대신 키/인덱스 접근(mat[i][j], snap[“matrix”]) → 멤버 계약 충돌이 구조적으로 미발생. E1(3D변환) 코드 직독으로 메커니즘 확인.
- 결론: 표면 H1b 0은 “과제가 안 불러서”가 아니라 **모델이 어떤 도메인이든 원시 자료구조(dict/list)로 수렴하는 본성**. vtx1 “dict 수렴” 가설이 통제된 도메인 변경으로 재확인. → progress Q5/§3 “진짜 부재” 쪽 강화.
- 새 관측 — 입력채널 선택: 타입계약 도메인에서 모델이 stdin 메뉴 대신 argv CLI(argparse/sys.argv)를 더 자주 고름(vtx_13 A1·A2·B1). runner의 stdin 대본과 불일치해 exit≠0로 죽지만 이는 깸이 아니라 측정기-코드 입력채널 불일치.
- 도구: verify_channel.py에 ‘inputmismatch’(argv-vs-stdin) 상태 추가 — argv CLI에 stdin 주입돼 죽은 칸을 broken에서 분리. vtx_13: broken 0/alive 6/reject 1/inputmismatch 3. vtx_2~10 회귀 영향 없음(alive 54/reject 25 불변).

## §11 vtx_14~17 + analyzer 통합 (40칸, 2026-06-07~08)

- 동기: vtx_14~17(40칸, 타입계약 도메인 연장)이 §10 이후 runs.jsonl엔 쌓였으나 미반영. 닫고 기록. 동시에 분석 도구를 통합(아래)해 재실행 분류로 한 번에 본다.
- ★ 도구 통합(Q8 다음 한 수): analyze_h1b.py가 매 행을 verify_channel로 재실행해 정적 cat 옆에 실측 runstate(alive/reject/broken/silent/inputmismatch)+channel을 붙임. rows.csv 4열 추가, summary.json에 replay 블록(runstate·channel·cat×runstate 교차표), report.txt에 “추측 라벨이 무엇으로 풀렸나” 교차표. verify_channel 로직 그대로 호출(분류 1곳 유지). arun.sh analyze 단계가 이제 재실행 포함(–no-replay로 정적만). 회귀 없음: vtx_2~10 exit0 = alive54/reject25(=§9), vtx_13 = alive6/reject1/inputmismatch3(=§10) 재현.
- ★ 핵심 결과(40칸): 정적 H1b 0/40 — §10의 “dict 수렴 → H1b 진짜 부재” 더 누적(이제 vtx_13~17 50칸 연속 H1b 0). dataclass/class 멤버계약 충돌 여전히 0.
- 40칸 runstate 합계: alive 29 / reject 6 / inputmismatch 2 / broken 3. 회차별 — vtx_14 alive7·inputmismatch2·broken1, vtx_15 alive8·reject2, vtx_16 alive7·reject1·broken2, vtx_17 alive7·reject3.
- ★ broken 3칸 전수 검토 = 전부 입력채널 불일치, 진짜 깸 0(run_h1b 플래그 0). 정체:
  - vtx_14_C1: input()+while, stdin 대본 일찍 고갈 → EOFError(메뉴 주행 중 입력 부족).
  - vtx_16_C1: argv+input+while, argv 기대인데 stdin 주입 → 무한루프 20s timeout.
  - vtx_16_E2: stdin JSON 한 줄 기대인데 대본 멀티라인 → “Invalid JSON input”(코드의 정당한 거부에 가까움).
    → §10 inputmismatch 관측의 연장. broken 라벨이 곧 깸 아님을 통합 분류기가 교차표(cat×runstate)로 노출. Q8 “실패=실행채널 문제?” 쪽 증거 누적.
- 운영 발견(Windows): 통합 검증 중 verify_channel.load()가 Windows 기본 cp949로 runs.jsonl 읽다 한글에서 크래시 → 봇 /검증 그간 전면 불능이던 것 발견·수정(UTF-8 명시). 재실행 subprocess IO도 UTF-8 강제(PYTHONUTF8 주입) — 모델 코드 한글 출력이 cp949로 깨져 ‘가짜 broken’ 나던 것 차단. 수정 전 봇 vtx_17 broken×1 → 수정 후 alive7/reject3로 Linux와 일치(4중 검증: Win/Linux × 단독/통합 동일). 분류기 OS 무관 안정 확인.
- 결론: vtx_14~17 닫음. H1b 0 유지(누적 강화), 비-alive는 전부 채널 불일치/정당 거부지 깸 아님. 통합 분류기로 broken을 채널 불일치와 분리 관측하는 체계 확립.

## §12 vtx_20 — broken의 성격이 stdin채널 → 데이터계약으로 첫 이동 (2026-06-08)

- 맥락: cp949 print 크래시 수정(batch/analyze/discord_bot 진입점 stdout UTF-8 강제) 후 봇에서 정상 완주한 첫 회차. vtx_19는 batch.py:75 em-dash print가 cp949에서 죽어 0칸 빈손(폐기, §3 tag 재사용 금지).
- 결과: 정적 H1b 0/10 → vtx_13~20 누적 60칸 연속 H1b 0(dict 수렴 본성 계속). 재실행 alive 9 / broken 1.
- ★ broken 1칸(C1, 산술식 평가기) = 지금까지와 다른 종류. 정적 cat ‘기타예외’(애매)였는데 통합 분류기가 broken/stderr-exc로 해소. run_h1b 플래그 없음 → H1b 아님.
  - 정체: parser가 만든 AST 스키마(`{'type':'Program','body':[{'type':'BinaryExpression',...}]}`, ESTree류)를 evaluator가 다른 스키마(`{'type':'unary/binary','op','operand'}`)로 기대 → `ValueError: Unknown AST node structure`로 런타임 사망. import·시그니처는 통과, 주고받는 dict의 내부 구조(데이터 계약)가 불일치.
  - §11까지 broken은 전부 stdin 채널(EOF/timeout/JSON포맷). vtx_20 broken은 채널이 아니라 **파일 간 자료구조 형식 불일치** — 정본 §5 “시그니처만으론 부족, 데이터 계약(input/output_schema)까지”가 예고한 실패의 첫 실측. 분류상 H1c(런타임 값/상태) 쪽.
- ★ 해석(가설, 단일 사례 — 누적 필요): dict 수렴이 H1b(멤버계약 충돌)는 구조적으로 막지만, 그 대가로 깸이 H1c(dict 키 구조 불일치)로 옮겨갈 수 있다. H1b를 피한 비용이 데이터계약 쪽에 나타나는 모양새. Q8 “실패=실행채널 문제?”의 부분 반례 — 이 깸은 실행채널이 아니라 모델 간 설계(스키마) 불일치.
- 미결/다음: 데이터계약 broken이 재현되는지(vtx_21+ 누적), C 도메인(파서/평가기류)에서 더 잦은지 관측. §3대로 단일 회차로 단정 금지.
## §13 vtx_21 429 사건 + client 에러분류·429복구 재설계 (2026-06-08)

- 사건: vtx_21 회차에서 A·B·C 6칸이 `429 RESOURCE_EXHAUSTED`(Vertex)로 exit=-1, files d0/g0. analyze가 `재실행 fake×6`으로 정확히 잡음. 유효 데이터는 D·E 4칸뿐이라 회차로 못 침 → 폐기(§3, vtx_18·19와 동급 처리). tag vtx_21 소진, 다음은 vtx_22.
- ★ 원인은 RPM 부족 아님(유료 1티어 1K RPM): 순간 429를 맞았을 때 client.py가 ①Retry-After 무시 ②모델 cooldown 부재로 같은 모델 다음 칸들이 줄줄이 같은 429에 처박힘 ③분류가 뭉개져 영구거부(403)와 일시거부(429)를 못 가름. 즉 에러분류·복구정책 문제.
- ★ 인증경로 의심(미해소): client.py가 Vertex 호스트(`aiplatform.googleapis.com`)에 `?key=`(Gemini API 인증)를 섞어 호출. Google 공식 문서상 정식 Vertex는 OAuth/서비스계정 + `projects/<id>/locations/<region>/...` 경로를 요구. 이 키 경로가 1티어 project quota를 안 타고 별도(무료/기본) 버킷에 묶였을 가능성. 콘솔 Quotas에서 generativelanguage vs aiplatform 어디에 사용량이 찍히는지 확인 필요. 이번 수정은 429를 견디게만 하지 이 근본 질문은 못 푼다.
- 수정(client.py + limiter.py + run.py + batch.py):
  - 분류 3분기 — 400/401/403/404=`PermanentHTTPError`(재시도 금지). 단 403+RESOURCE_EXHAUSTED는 쿼터로 취급. 429/RESOURCE_EXHAUSTED=쿼터(재시도, 최종실패 시 `RateLimitError`로 분리). 500/503/INTERNAL/UNAVAILABLE/URLError/Timeout=일시오류(재시도).
  - Retry-After 우선: 헤더의 정수 초를 그대로 따름(상한 cap). 없으면 `2**attempt + jitter(0~1초)`, cap 60. jitter는 여러 칸 동시 재돌진(thundering herd) 분산.
  - model별 global cooldown: 429 맞은 모델은 `limiter.set_cooldown`으로 park, 다음 acquire가 RPD/RPM 검사 전에 그만큼 잠. 모델별 격리(무관 모델 즉시 통과). ← vtx_21 연쇄 429의 직접 차단.
  - 최종실패 로그: 본문(안 자름)+모델명+attempt+잔시간+kind를 stderr에. 이전엔 본문이 잘려(`(e.g. ch`) 어느 한도인지 안 보였음.
  - ★ 오염 차단(설계 판단): 기존엔 쿼터 최종실패가 가짜 exit=-1 칸이 되고 회차 계속 → vtx_21 오염의 정체. 이제 `RateLimitError`·`PermanentHTTPError`는 `RPDExceeded`처럼 회차를 멈춤(사실 기록 후 정지). 인프라 거부를 모델의 코드 산출 실패로 위장하지 않음.
- 검증: limiter 자가검증 8케이스로 확장(Retry-After 우선·cap·쿨다운 대기·모델별 격리 추가) 전부 통과. RPM 로직 불변(15개 즉시·16번째 60초 대기 회귀 없음). 실호출 HTTP 분기는 키·네트워크 부재로 코드리뷰로만 검증(미실행).
- 목표 달성: RPM 안 낮춤. 순간 429는 재시도+쿨다운으로 흡수돼 run 전체가 안 죽음. 지속 429는 가짜 데이터 없이 전체 진단과 함께 깨끗이 멈춤.
- 미결/다음: (1) 인증경로/쿼터 확인(콘솔) — 1티어가 실제 적용되는지. (2) vtx_22로 429 복구가 실호출에서 도는지 + §12 데이터계약 broken 재현 관측. (3) 핸드오프 §2에 본 수정 반영.

## §14 vtx_22 — 429 복구 확인 + 데이터계약 broken 재현 (2026-06-09)

- 사건: vtx_22가 10/10칸 전부 생성·실행·분석 완료. vtx_21의 429 오염은 재현 안 됨. `analysis_out/vtx_22` 생성 완료, rows 기준 A1~E2 빠진 칸 없음.
- 결과: 정적 H1b 0/10. vtx_13~22 유효 타입계약 도메인 누적은 이제 **70칸 연속 H1b 0**(vtx_21 폐기). dict/list 수렴으로 멤버계약 충돌이 구조적으로 안 나는 흐름 유지.
- 재실행 runstate: alive 7 / reject 1 / silent 1 / broken 1. 채널: stdout-ok 7 / stdout-return 1 / none 1 / stderr-exc 1. run_h1b 플래그 0.
- ★ broken 1칸(C1, 산술식 평가기) = §12 데이터계약 broken 재현. parser는 AST 타입을 `BinaryOp`/`Number`/`UnaryOp`(PascalCase)로 만들고, evaluator는 `binary_op`/`number`/`unary_op`(snake_case)을 기대 → `Error: Unknown AST node type: BinaryOp`.
  - import·시그니처는 통과. 실패 지점은 파일 간 dict 내부 스키마의 문자열 계약 불일치.
  - §12 vtx_20 C1의 `Unknown AST node structure`와 같은 계열. 이제 단일 사례가 아니라 **C 도메인에서 2회 관측**.
- 해석(가설 강화, 아직 단정 금지): Q8 “실패=실행채널 문제?”는 더 좁혀짐. §11의 broken은 채널 문제였지만, §12·§14의 broken은 채널이 아니라 데이터계약(H1c 쪽)이다. dict 수렴은 H1b를 막는 대신, 파서/평가기류 C 도메인에서 AST 스키마 불일치로 새 깸을 만든다는 쪽으로 증거가 쌓인다.
- 429 쪽 해석: vtx_22에서 429 fake가 없어서 §13 수정이 최소한 실호출 회차를 방해하지 않음은 확인. 다만 실제 429를 다시 맞아 재시도·cooldown·회차중단이 작동한 사례는 아직 없음. 인증경로/쿼터 의심은 여전히 미결.

## §15 vtx_23~25 — 3회차 누적, H1b 100칸 0 + 데이터계약/입력포맷 분리 (2026-06-09)

- 사건: vtx_23·24·25 모두 10/10칸 생성·실행·분석 완료. 429/RESOURCE_EXHAUSTED 오염 없음. `analysis_out/vtx_23~25` 모두 존재.
- 결과: 세 회차 정적 H1b 0/30. vtx_13~25 유효 타입계약 도메인 누적은 이제 **100칸 연속 H1b 0**(vtx_18·19·21 폐기). 표면 H1b 부재 결론은 더 강화.
- 분류기 갭 보강 후 재실행 합계(30칸): alive 21 / reject 2 / silent 2 / inputmismatch 4 / broken 1. `run_h1b_flags` 0, `static_h1b_false_positive` 1(vtx_25_D2).
  - vtx_23: alive 6 / reject 1 / silent 1 / broken 1 / inputmismatch 1.
  - vtx_24: alive 8 / reject 1 / inputmismatch 1.
  - vtx_25: alive 7 / inputmismatch 2 / silent 1.
- 라벨 분리 결과:
  - vtx_23_D2: `Unexpected character: x`. main 기본식은 `3 + 5 * 2 + x`인데 parser tokenizer는 숫자·연산자만 허용하고 식별자 `x`를 거부. 채널 문제가 아니라 **문법/데이터계약 불일치**. 다만 파일 간 AST 스키마 불일치(§12·§14 C1류)는 아님.
  - vtx_23_E2 / vtx_24_E2 / vtx_25_E2: 모두 stdin 대본 멀티라인을 JSON으로 읽다가 `Extra data: line 2 column 1`. 이는 dependency graph 프로그램이 JSON stdin을 기대한 데 반해 공통 대본을 주입한 **STDIN_FORMAT_MISMATCH** 쪽. 모델 내부 깸으로 세면 안 됨.
- ★ vtx_20·22의 C AST 스키마 불일치는 vtx_23~25에서 직접 재현 안 됨. C1/C2는 세 회차 모두 alive/silent. 따라서 “C 파서/평가기류에서 반복” 가설은 아직 강한 결론 금지. 대신 더 넓은 “데이터계약/문법계약 H1c가 드문드문 발생”으로 완화.
- ★ 새 관측: vtx_25_D2가 `nodes.Node` 클래스를 별도 파일에서 만들고 parser/folder/serializer/main이 속성(`.type/.value/.left/.right`)으로 공유했지만 실행은 silent/exit0. 즉 “항상 dict/list만”은 약간 깨짐. 그러나 공유 생성자·동일 클래스 import로 계약이 맞아 H1b는 발생하지 않음. Q7 결론은 “객체가 나와도 경계 계약이 일관되면 H1b가 안 난다”로 미세 수정 필요.
- 도구 수정 완료: analyzer/verify에 `DATA_CONTRACT_GRAMMAR`, `STDIN_FORMAT_MISMATCH`, `STATIC_H1B_FALSE_POSITIVE` 라벨 분리. 기존 broken 4칸 중 JSON 3칸은 inputmismatch로 이동했고, vtx_25_D2는 H1b?가 아니라 static false positive로 분리됨. Q8 표에서 모델 내부 깸은 vtx_23_D2 1칸만 남음.

## §16 vtx_26~30 — Q8 회귀 확인, broken 0으로 닫기 (2026-06-09)

- 사건: vtx_26 단일 회귀 후 vtx_27~30까지 연속 실행. 모두 10/10칸 생성·실행·분석·push 완료. 429/RESOURCE_EXHAUSTED 오염 없음. 웹훅은 vtx_27 이후 정상 요약 수신, `/연속실행` 운영도 정상.
- 결과: vtx_26~30 정적 H1b 0/50. vtx_13~30 유효 타입계약 도메인 누적은 이제 **150칸 연속 H1b 0**(vtx_18·19·21 폐기). H1b 부재는 더 볼수록 강화될 뿐 새 신호 없음.
- 재실행 합계(50칸): alive 44 / reject 3 / inputmismatch 3 / broken 0 / silent 0. `run_h1b_flags` 0, `static_h1b_false_positive` 0.
  - vtx_26: alive 10.
  - vtx_27: alive 9 / reject 1.
  - vtx_28: alive 9 / reject 1.
  - vtx_29: alive 9 / inputmismatch 1(`STDIN_FORMAT_MISMATCH`, E2 JSON stdin).
  - vtx_30: alive 7 / reject 1 / inputmismatch 2(B2 argv-vs-stdin, E2 JSON stdin).
- ★ 새 라벨 회귀 확인: `STDIN_FORMAT_MISMATCH`와 `argv-vs-stdin`이 broken을 오염하지 않고 inputmismatch로 분리됨. vtx_23_D2류 `DATA_CONTRACT_GRAMMAR` 추가 발생 없음. vtx_20·22류 AST 스키마 불일치도 재발 없음.
- 결론(Q8): “실패=실행채널 문제?”는 **대부분 그렇다**로 닫을 수 있다. 관측된 비-alive의 대부분은 정상 reject 또는 입력채널/포맷 불일치이며, 모델 내부 데이터계약 broken은 드물게만 관측(vtx_20 C1, vtx_22 C1, vtx_23 D2). H1b로 넘어가는 사례는 없음.
- 다음 스텝: Q8 추가 회차의 한계효용 낮음. 정본 리스크 레지스터를 갱신하고, 새 축으로 넘어간다. 후보는 (1) H4 도커 실측 구현으로 실제 런타임 판정 계층 만들기, (2) Vertex 인증경로/쿼터 정식화, (3) H3/known_failures 실험 설계.
