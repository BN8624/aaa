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
