# AAA Discord 운영 Bot (Windows)

아이폰 Discord에서 사무실 Windows PC의 AAA 파이프라인을 운영하는 얇은 wrapper 봇이다.

## 무엇을 하나

| 커맨드 | 동작 |
|---|---|
| `/상태` | 현재 실행 상태 표시 (PID 생존 확인 포함, stale 감지) |
| `/로그 [줄수:80]` | 최근 로그 표시 (최대 200줄) |
| `/실행 채널:<tag>` | **arun.sh와 동일한 전체 파이프라인** 실행 |
| `/분석 채널:<tag>` | `analyze_h1b.py <tag>` 실행 |
| `/검증 채널:<tag>` | `verify_channel.py runs.jsonl <tag>` 실행 |

`/실행`은 다음 6단계를 순서대로 수행한다 (arun.sh를 호출하지 않고 Python으로 재현):

1. `git pull --rebase --autostash`
2. `python batch.py <tag>`
3. `python analyze_h1b.py <tag>`
4. `git add -A`
5. `git commit -m "run <tag>"`
6. `git push` (실패 시 pull 재시도 후 1회 재push)

> `/깃풀`, `/정지`, `/sleep`, `/wake`는 2차 범위다.

---

## 설치 (Windows)

### 1. 파일 배치

다음 파일을 AAA 저장소 루트(`arun.sh`, `batch.py` 등이 있는 곳)에 둔다.

```text
discord_bot.py
requirements-discord.txt
.env.example
discord_state.json.example
logs/discord/.gitkeep
```

### 2. 의존성 설치

기존 AAA가 돌던 파이썬 환경에 그대로 설치하거나, 전용 venv를 만든다.

```bat
python -m pip install -r requirements-discord.txt
```

### 3. 환경 변수 설정

```bat
copy .env.example .env
```

`.env`를 열어 `DISCORD_TOKEN`을 채운다. 보안을 위해 `AAA_ALLOWED_GUILD_ID`,
`AAA_ALLOWED_CHANNEL_ID`도 채우는 것을 권장한다.

### 4. Discord Bot Token 발급

1. https://discord.com/developers/applications 접속
2. New Application 생성 → 좌측 **Bot** 탭
3. **Reset Token** → 토큰 복사 → `.env`의 `DISCORD_TOKEN`에 붙여넣기
4. 같은 화면에서 봇을 서버에 초대 (OAuth2 → URL Generator → scopes에 `bot`, `applications.commands` 체크 → 생성된 URL로 초대)
5. 슬래시 커맨드만 쓰므로 별도 권한 인텐트는 불필요

> 채널/길드 ID는 Discord 앱에서 개발자 모드를 켠 뒤(설정→고급→개발자 모드)
> 서버/채널 우클릭 → "ID 복사"로 얻는다.

### 5. 실행

```bat
python discord_bot.py
```

봇이 뜨면 콘솔에 `[ready] ... 로그인 완료`가 출력된다.

### 6. 자동 시작 (PC 부팅 시)

봇이 항상 떠 있어야 운영 리모컨이 된다. 두 가지 방법:

**작업 스케줄러 (권장)**
1. 작업 스케줄러 → 작업 만들기
2. 트리거: "로그온할 때"
3. 동작: 프로그램 시작 → `python`, 인수 `discord_bot.py`, 시작 위치 = AAA 루트 경로

**시작프로그램 .bat**

`start_bot.bat`을 만들어 시작프로그램 폴더(`shell:startup`)에 둔다.

```bat
@echo off
cd /d C:\path\to\aaa
python discord_bot.py
```

---

## `.gitignore`에 추가할 항목

기존 `.gitignore`에 `.env`, `*.log`, `*.pid`는 이미 있다. 다음 한 줄만 추가한다.

```text
discord_state.json
```

`logs/discord/` 디렉토리 구조는 `.gitkeep`으로 유지한다 (`*.log`가 무시되므로 force-add 필요).

```bat
git add -f logs/discord/.gitkeep
```

---

## 환경 변수 참고

| 변수 | 필수 | 설명 |
|---|---|---|
| `DISCORD_TOKEN` | O | Discord Bot Token |
| `AAA_ROOT` | | AAA 저장소 루트 (기본: 봇 실행 위치) |
| `AAA_ALLOWED_GUILD_ID` | 권장 | 이 서버에서만 동작 |
| `AAA_ALLOWED_CHANNEL_ID` | 권장 | 이 채널에서만 동작 |
| `AAA_ADMIN_USER_ID` | | 2차 기능용 |

> `batch.py`는 `VERTEX_API_KEY` 환경 변수를 요구한다. 봇을 띄우는 셸/작업 스케줄러
> 환경에 이 변수가 설정돼 있어야 `/실행`이 정상 동작한다.

---

## 안전 설계

- 모든 외부 실행은 `shell=False` + 리스트 인자 → 셸 인젝션 차단
- 채널명은 `^[a-zA-Z0-9_-]+$`만 허용 (`; rm -rf`, `../`, 공백, `$(...)` 거부)
- 동시 실행 1개 제한 (실행 중이면 새 작업 거부)
- 임의 shell 커맨드 미구현
- 기존 AAA 코드(`run.py`, `runner.py`, `state.py`, `arun.sh`)는 수정하지 않음

---

## 테스트 결과 요약

- `python -m py_compile discord_bot.py` 통과
- 채널명 검증 단위 테스트 통과
  - 거부: `vtx_18; rm -rf /`, `../../x`, `a b`, `$(whoami)`, `` (빈값)
  - 허용: `vtx_18`, `h1b`, `test-01`, `abc_123`

### 실제 Discord 수동 테스트 순서

```text
/상태
/로그
/실행 채널:vtx_18
/상태
/로그
/분석 채널:vtx_18
/검증 채널:vtx_18
```

---

## 남은 TODO (2차)

- `/깃풀` (`git pull --rebase --autostash`, `/실행` 중 거부)
- `/정지` (terminate → 일정 시간 후 kill, state 갱신)
- 봇 재시작 시 진행 중이던 PID 복구는 불가 → 현재는 `/상태`가 stale로 표시
- `/sleep`, `/wake` (WOL은 ipTIME 앱으로, 초기 범위 외)
