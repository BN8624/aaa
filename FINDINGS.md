# FINDINGS — aaa 살아있는 발견 (raw로 Claude가 읽음)

> 날 사실만. 해석·가설은 aaa_progress.md. 기준 2026-06-06(PT).

## §1 정의
- H1b = 파일 간 계약 파괴(import/시그니처/멤버(AttributeError)/unhashable/NameError).
- H1c = 런타임 값예외(계약 멀쩡). timeout = 20s 초과.
- 관측가능 3상태: 관측됨 / 관측불가(메뉴앞EOF·argparse·코더빈손) / 불명(exit0가짜).

## §2 핵심 (두 세션 재현)
- H1b 6~9%, D·E 집중, AttributeError 최다, 비결정적. py_compile은 다 통과.
- 관측 천장: 대부분 "H1b 없음"이 아니라 "볼 기회조차 없음". 핵심 지표 = H1b / 관측가능.

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
  → stdin 주입이 닿을 데 없음. D·E의 exit0가짜는 "불명"이 아니라 사실상 "관측됨"에 가까움
  (멤버 계약 가로질러 실행 완료; H1b 터질 거면 stderr에 떴을 것).
- D2 증거: ValueError(user_88 not found) — main→point_service→repository 3파일 체인 실제 도달.
- 메뉴앞EOF=0의 실제 원인: 데모형은 애초에 EOF 안 냄, 메뉴형은 대본이 exit까지 끌고 감. 둘 다 exit0가짜로 수렴.
- ★ stdin 로깅 호명됨: exit0가짜가 "굶음"인지 "완주"인지 stderr만으론 영구 구분 불가
  → run.py(주입 시) + state.py(dump 시) 별도 깨끗한 변경으로.

## §6 vtx1 (Gemini 3.5 Flash 첫 회차, 2026-06-06)
- 전환 후 첫 깨끗한 회차. 10칸 전부 코드 생성(코더빈손 0).
- ★ 메뉴앞EOF 4→0: Gemma는 input()맨몸→EOF즉사였으나, Gemini는 input을 try/except (EOFError)로 감싸 "Goodbye!" 후 정상 break. → 죽지 않지만 메뉴 루프 0바퀴, 파일상호작용 미실행 = exit0가짜(불명).
- 즉 관측천장의 정체가 "메뉴앞EOF(죽음)"→"exit0가짜(우아한 무동작)"로 이동. 관측가능률은 여전히 낮음(B·C 4칸 불명).
- H1b 표면상 0. 단 E1은 H1c(create_user가 role 도메인 {admin,user,guest}인데 main이 'editor'/'viewer' 주입→ValueError)이고, 그 뒤 user.get() vs dataclass 반환 불일치(H1b)가 잠복(도달 전 사망).
- ★ 함의: H4(stdin 대본)이 Gemini에서 처음 쓸모 가능. B1은 데모형이 아닌 진짜 메뉴형이라, 대본 주입 시 EOF로 안 죽고 메뉴를 실제로 돌 가능성 → D·E 아닌 B·C에서도 계약 실행 관측 기회.
- 주의: tag 'vtx1'은 analyze 정규식(_숫자_) 불일치로 rows.csv 빈값. 다음부터 'vtx_2' 형식.

## §7 vtx_2~10 (Gemini 3.5 Flash 누적 9회차, 2026-06-06)
- 데이터 무결성: runs.jsonl에 vtx_ 170행 중 80행이 VERTEX_API_KEY 미설정 가짜(files=[], exit=-1, stderr "VERTEX_API_KEY 환경변수가 없다"). 키 없이 한 번 돌고 export 후 재실행한 흔적(약 17분 간격). 가짜 걷으면 9회차x10칸=90 진짜 실행, 빠진 칸·중복 없음. vtx_2는 키실패 0. analysis_out/에 vtx_ 디렉토리 없음 = arun.sh 안 거치고 batch.py 직접 실행됨(rows.csv 미생성). 집계는 runs.jsonl 직접 계산.
- 표면 H1b = 0/90. 분류: exit0 76 / H1c 7 / argparse 6 / timeout 1.
- D·E exit0 34칸 전부 logged-stdin 재생 시 계약 가로질러 완주(삼켜진/도달전 H1b 없음).
- vtx1 E1의 잠복 H1b(dict vs dataclass) 재현 안 됨: 9회차 E1 전부 @dataclass 미사용, dict 수렴으로 멤버 계약 충돌 자체가 발생 안 함. "더 깊이 숨긴다"(vtx1 가설)는 이번 누적으로 반증에 가까움.
- 새 발견 — 오류의 채널 이동: exit0 79칸 중 24칸이 오류를 stderr 예외가 아니라 stdout 반환값으로 삼킴. 예: {'success':False,'error':...} / Unauthorized / Insufficient stock / Payment failed. 코드 신호: broad except Exception 47/90, except->print 62/90. 강한 모델은 계약위반·값오류를 raise가 아니라 return으로 처리. H1b/H1c가 사라진 게 아니라 예외->반환값, stderr->stdout으로 이동했을 가능성.
- 관측 천장 3차 이동: (1)메뉴앞EOF(죽음) -> (2)exit0가짜(우아한 무동작, vtx1) -> (3)예외->반환값(오류 삼킴, vtx_2~10). 이제 반환값/stdout 의미검증 없이는 깸 관측 불가.
- 인과 교란 명시: 모델(Gemma->Gemini)과 파이프라인(H4 대본·stdin로깅) 동시 변경. Gemma 대조회차 미수행 -> "H1b 감소가 모델 탓"이라 단정 못 함.

## §8 Q5 — 삼킨 24칸 분류 (코드 변경 0, runs.jsonl 재생, 2026-06-07)
- 방법: vtx_2~10 가짜 80행 제외 → 진짜 90칸, exit0 79칸. 삼킴 신호로 ≈21칸 좁힘(§7의 24와 동일 현상). generated_files 직독 + import 정합 대조로 H1b/H1c 분류.
- 결과: 삼킨 오류 중 H1b = 0건. 자동분류 H1b 후보 2건은 다중행 import 괄호 오인 거짓양성(직독 시 계약 정합).
- 나머지 전부 H1c/의도된 정상 도메인 거부(Unauthorized·Insufficient·not recognized). stdin이 실제 메뉴 주행이라 코드는 돌고 정당히 거부함.
- 분포: C·D·E 편중, A·B 거의 없음.
- 해석(Q5 답): 삼킴 = 숨은 H1b 아님. dict 수렴으로 H1b 애초 미발생(vtx1 E1 비재현과 일치). 표면 H1b 0은 채널 은폐보다 진짜 부재. §7 "예외→반환값" 가설은 H1c엔 맞지만 H1b 사례 0.
- Q6 함의: 검증기로도 건질 숨은 H1b 없음 → "정상 거부 vs 진짜 깸" 구분 관측 도구로 재설정.

## §9 Q6 — verify_channel.py 첫 실측 (2026-06-07)
- 도구: 파이프라인 분리 관측기. generated_files 임시폴더 재생 + 로깅된 stdin 주입 → stdout/stderr/exit 실측, 4상태(alive/reject/broken/silent) + 채널(stderr-exc/stdout-return/silent) 판정.
- vtx_2~10 exit0 79칸 전수: broken 0, reject 25(전부 stdout-return), alive 54(stdout-ok), silent 0.
- 의미: §8의 "삼킨 ≈21~24 = 전부 정상 도메인 거부"를 추론→실측으로 확정. 깸 채널(broken) 비어 있음. progress §5 새 지표 첫 값.
- 함의: 검증기는 H1b 사냥기 아님이 실증됨(잡을 broken 없음). "정상 거부 vs 진짜 깸" 구분 관측 도구로 위치 확정.
