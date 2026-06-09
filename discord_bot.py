#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AAA Discord 운영 Bot (Windows 사무실 PC용)

목적: 아이폰 Discord -> 사무실 Windows PC -> AAA 운영 리모컨

설계 원칙
  - 기존 AAA 코드(run.py, runner.py, state.py, arun.sh 등)는 절대 수정하지 않는다.
  - 이 봇은 얇은 wrapper다. 화이트리스트된 명령만 실행한다.
  - 임의 shell 실행 금지. 모든 subprocess는 shell=False + 리스트 인자.
  - 긴 작업은 백그라운드(subprocess.Popen)로 돌리고 즉시 응답한다.
  - 상태는 discord_state.json에 기록한다.

1차 구현 슬래시 커맨드
  /상태  /로그  /실행  /분석  /검증
  (/깃풀 /정지 /sleep /wake 는 2차)

/실행 의미: arun.sh 와 동일한 전체 파이프라인을 Python subprocess로 재현.
  1. git pull --rebase --autostash
  2. python batch.py <tag>
  3. python analyze_h1b.py <tag>
  4. git add -A
  5. git commit -m "run <tag>"
  6. git push  (실패 시 pull --rebase --autostash 후 1회 재시도)
  arun.sh 파일 자체는 호출하지 않는다(Windows엔 bash 부재). arun.sh는 수정하지 않는다.
"""

import os
import re
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Windows cp949 콘솔에서 한글/기호 print 크래시 방지(봇 진입점에서 1회).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import discord
from discord import app_commands
from dotenv import load_dotenv

try:
    import psutil
except ImportError:
    psutil = None  # is_process_alive에서 fallback 처리

# ----------------------------------------------------------------------------
# 설정
# ----------------------------------------------------------------------------

KST = timezone(timedelta(hours=9))
CHANNEL_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
MAX_TAIL_LINES = 200
DEFAULT_TAIL_LINES = 80
DISCORD_MSG_LIMIT = 1900  # 2000자 제한 - code fence 여유분

# /명령 (임의 명령 실행) 안전장치
CMD_TIMEOUT_SEC = 60          # 60초 넘으면 강제 종료
# 파괴적/위험 명령 차단 (단어 경계로 검사)
CMD_BLOCKED_TOKENS = [
    "del", "erase", "format", "rmdir", "rd",
    "rm", "rm -rf", "rd /s", "rmdir /s",
    "fdisk", "diskpart", "shutdown", "mklink",
    "reg ", "regedit", "schtasks", "takeown", "icacls",
]
# 절대경로(드라이브 문자) / 상위 폴더 탈출 차단
CMD_BLOCKED_RE = re.compile(r"(\.\.[\\/]|\b[a-zA-Z]:[\\/])")

# 경로(모두 pathlib, OS 무관). AAA_ROOT 기준.
_CONFIG = {}


def load_config():
    """`.env` 로드 후 설정 dict 반환."""
    # 작업 스케줄러/시스템 환경에 오래된 값이 남아 있어도 repo .env가 우선이다.
    load_dotenv(override=True)
    root = Path(os.environ.get("AAA_ROOT", ".")).resolve()
    cfg = {
        "token": os.environ.get("DISCORD_TOKEN", "").strip(),
        "root": root,
        "guild_id": _int_or_none(os.environ.get("AAA_ALLOWED_GUILD_ID")),
        "channel_id": _int_or_none(os.environ.get("AAA_ALLOWED_CHANNEL_ID")),
        "admin_user_id": _int_or_none(os.environ.get("AAA_ADMIN_USER_ID")),
        "state_file": root / "discord_state.json",
        "log_dir": root / "logs" / "discord",
        "runs_jsonl": root / "runs.jsonl",
    }
    cfg["log_dir"].mkdir(parents=True, exist_ok=True)
    _CONFIG.update(cfg)
    return cfg


def _int_or_none(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------
# 입력 검증
# ----------------------------------------------------------------------------

def validate_channel_name(name: str) -> bool:
    """안전한 채널/태그명만 허용. 셸 인젝션/경로 탈출 차단."""
    return bool(name) and bool(CHANNEL_RE.match(name))


def check_command_allowed(command: str):
    """
    /명령 으로 들어온 셸 명령 문자열 검사.
    허용되면 None, 거부되면 사유 문자열 반환.
    완벽한 샌드박스는 아니다. 파괴적 명령/폴더 탈출만 최대한 막는다.
    """
    if not command or not command.strip():
        return "빈 명령이다."
    low = command.lower()
    # 절대경로 / 상위폴더 탈출
    if CMD_BLOCKED_RE.search(command):
        return "절대경로(C:\\ 등)나 상위폴더(..) 접근은 막혀 있다. AAA 폴더 안에서만 동작한다."
    # 위험 토큰 (공백/시작 경계로 검사)
    tokens = re.split(r"[\s&|;<>()]+", low)
    for blk in CMD_BLOCKED_TOKENS:
        blk = blk.strip()
        if blk in tokens or low.startswith(blk + " ") or low == blk:
            return f"차단된 명령이다: `{blk}`"
    return None


# ----------------------------------------------------------------------------
# 상태 파일
# ----------------------------------------------------------------------------

def load_state():
    sf = _CONFIG["state_file"]
    if not sf.exists():
        return None
    try:
        return json.loads(sf.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_state(state: dict):
    sf = _CONFIG["state_file"]
    try:
        sf.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[warn] save_state 실패: {e}", file=sys.stderr)


def is_process_alive(pid) -> bool:
    """PID 생존 확인. psutil 우선, 없으면 표준 라이브러리 fallback."""
    if not pid:
        return False
    if psutil is not None:
        try:
            p = psutil.Process(int(pid))
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            return False
    # fallback (Windows에서는 불안정할 수 있음)
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


# ----------------------------------------------------------------------------
# 로그
# ----------------------------------------------------------------------------

def make_log_file(task: str, channel: str = None) -> Path:
    ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    name = f"{task}_{channel}_{ts}.log" if channel else f"{task}_{ts}.log"
    return _CONFIG["log_dir"] / name


def tail_file(path: Path, lines: int = DEFAULT_TAIL_LINES) -> str:
    if not path or not Path(path).exists():
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.readlines()
    except OSError:
        return ""
    tail = content[-lines:]
    text = "".join(tail)
    # Discord 길이 제한: 너무 길면 앞부분을 잘라낸다.
    if len(text) > DISCORD_MSG_LIMIT:
        text = "...(앞부분 생략)...\n" + text[-DISCORD_MSG_LIMIT:]
    return text


# ----------------------------------------------------------------------------
# 백그라운드 작업 실행
# ----------------------------------------------------------------------------

def _now_iso():
    return datetime.now(KST).isoformat(timespec="seconds")


def start_background_task(task: str, channel: str = None, mode: str = "pipeline"):
    """
    백그라운드 작업 시작. 즉시 (state, log_path) 반환.
    mode:
      "pipeline" : /실행 - arun.sh 6단계 재현 (runner 스크립트를 subprocess로 기동)
      "analyze"  : /분석 - analyze_h1b.py
      "verify"   : /검증 - verify_channel.py runs.jsonl <tag>
    """
    root = _CONFIG["root"]
    log_path = make_log_file(task, channel)

    if mode == "pipeline":
        # arun.sh 6단계를 재현하는 러너를 별도 프로세스로 띄운다.
        # 이 파일(discord_bot.py) 자신을 러너 모드로 재실행 -> bash 불필요.
        cmd = [sys.executable, str(Path(__file__).resolve()), "--pipeline", channel]
    elif mode == "analyze":
        cmd = [sys.executable, "analyze_h1b.py", channel]
    elif mode == "verify":
        cmd = [sys.executable, "verify_channel.py", str(_CONFIG["runs_jsonl"]), channel]
    else:
        raise ValueError(f"unknown mode: {mode}")

    log_fh = open(log_path, "w", encoding="utf-8")
    log_fh.write(f"command: {cmd}\n")
    log_fh.write(f"cwd: {root}\n")
    log_fh.write(f"started_at: {_now_iso()}\n")
    log_fh.flush()

    # Windows/Unix 공통. shell=False, 리스트 인자.
    proc = subprocess.Popen(
        cmd,
        cwd=str(root),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )

    state = {
        "running": True,
        "task": task,
        "channel": channel,
        "pid": proc.pid,
        "started_at": _now_iso(),
        "finished_at": None,
        "log_file": str(log_path),
        "last_command": f"/{task} {channel}".strip(),
        "last_exit_code": None,
    }
    save_state(state)
    return state, log_path


# ----------------------------------------------------------------------------
# 파이프라인 러너 (별도 프로세스로 실행됨 -- arun.sh 6단계 재현)
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# 회차 완료 알림 (정본 §10: 판단 전달용 웹훅, 본문 20줄 이내, 의존성 0=urllib)
#   - URL은 환경변수 DISCORD_WEBHOOK_URL (키처럼 취급, 커밋 금지).
#   - 미설정이면 조용히 건너뜀(파이프라인 안 깨짐).
#   - 본문은 로그가 아니라 "지금 가서 볼 가치 있나" 판단에 필요한 최소 정보.
# ----------------------------------------------------------------------------

def _build_run_summary(tag: str) -> str:
    """analysis_out/<tag>/summary.json 을 읽어 폰 판단용 20줄 이내 요약 생성."""
    import json as _json
    sj = _CONFIG["root"] / "analysis_out" / tag / "summary.json"
    try:
        j = _json.loads(sj.read_text(encoding="utf-8"))
    except Exception:
        # 분석 산출 없음(예: batch 빈손) — 회차 자체가 비었음을 알린다.
        return (f"⚠️ [{tag}] 분석 결과 없음 — batch가 0칸이거나 분석 실패.\n"
                f"재시도 가치: 높음(빈손 원인 확인 필요). 추천: SSH에서 로그 확인.")
    n = j.get("n_rows", 0)
    h1b = j.get("exec", {}).get("h1b", 0)
    rep = j.get("replay", {})
    rs = rep.get("runstate", {})
    broken = rs.get("broken", 0)
    inmis = rs.get("inputmismatch", 0)
    alive = rs.get("alive", 0)
    reject = rs.get("reject", 0)
    # retry_value / recommended_action: 규칙으로 가르고, 애매하면 사람 판단(§10·14장).
    if n == 0:
        retry, action = "높음", "빈손 — SSH 확인"
    elif broken > 0:
        retry, action = "높음(broken 발생)", "broken 칸 전수검토(채널불일치 vs 데이터계약 vs H1b)"
    elif h1b > 0:
        retry, action = "높음(H1b 노출)", "H1b 칸 코드 직독 — 가설 핵심"
    else:
        retry, action = "낮음(alive/reject뿐, 깸 없음)", "기록만 — 다음 회차로"
    lines = [
        f"✅ [{tag}] 회차 완료 · {n}실행",
        f"H1b: {h1b}  |  재실행: alive {alive} / reject {reject} / broken {broken} / inputmismatch {inmis}",
        f"재시도 가치: {retry}",
        f"추천: {action}",
        f"로그: analysis_out/{tag}/rows.csv (전문은 SSH)",
    ]
    return "\n".join(lines)


def _notify_webhook(tag: str):
    """회차 완료 시 디스코드 웹훅으로 요약 1회 POST. URL 없으면 건너뜀."""
    import json as _json
    import urllib.request as _ur
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        print("[알림] DISCORD_WEBHOOK_URL 미설정 — 웹훅 건너뜀", flush=True)
        return
    body = _build_run_summary(tag)
    payload = _json.dumps({"content": f"```\n{body}\n```"}).encode("utf-8")
    req = _ur.Request(url, data=payload,
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _ur.urlopen(req, timeout=15) as resp:
            print(f"[알림] 웹훅 전송 완료 (HTTP {resp.status})", flush=True)
    except _ur.HTTPError as e:
        # Discord는 실패 원인을 JSON 본문에 담아준다. URL/토큰은 절대 찍지 않는다.
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        print(f"[알림] 웹훅 전송 실패(무시): HTTP {e.code} {detail}", flush=True)
    except Exception as e:
        # 알림 실패가 회차 결과를 덮지 않게 — 로그만 남기고 통과.
        print(f"[알림] 웹훅 전송 실패(무시): {type(e).__name__}: {e}", flush=True)


def _run_step(args, label):
    print(f"\n----- {label} -----", flush=True)
    print(f"$ {' '.join(args)}", flush=True)
    r = subprocess.run(args, cwd=str(_CONFIG["root"]),
                       stdout=sys.stdout, stderr=subprocess.STDOUT,
                       env=os.environ.copy())
    print(f"[exit {r.returncode}] {label}", flush=True)
    return r.returncode


def run_pipeline(tag: str) -> int:
    """
    arun.sh 와 동일한 의미의 전체 파이프라인.
      1. git pull --rebase --autostash
      2. python batch.py <tag>
      3. python analyze_h1b.py <tag>
      4. git add -A
      5. git commit -m "run <tag>"
      6. git push  (실패 시 pull --rebase --autostash 후 1회 재시도)
    이 함수는 start_background_task가 띄운 별도 프로세스 안에서 돈다.
    stdout/stderr는 호출 측에서 로그 파일로 리다이렉트된다.
    """
    py = sys.executable
    print(f"===== 실행 파이프라인 {tag}  {datetime.now(timezone.utc).isoformat()} =====", flush=True)

    # 1. git pull --rebase --autostash
    _run_step(["git", "pull", "--rebase", "--autostash"], "git pull")
    # 2. batch.py
    _run_step([py, "batch.py", tag], "batch")
    # 3. analyze_h1b.py
    _run_step([py, "analyze_h1b.py", tag], "analyze")
    # 4. git add -A
    _run_step(["git", "add", "-A"], "git add")
    # 5. git commit
    _run_step(["git", "commit", "-m", f"run {tag}"], "git commit")
    # 6. git push (실패 시 pull 재시도 후 재push)
    push_rc = _run_step(["git", "push"], "git push")
    if push_rc != 0:
        print("[info] push 실패 -> pull 재시도 후 재push", flush=True)
        _run_step(["git", "pull", "--rebase", "--autostash"], "git pull (retry)")
        push_rc = _run_step(["git", "push"], "git push (retry)")

    print(f"\n>>> DONE {tag} (읽을 것: analysis_out/{tag}/rows.csv)", flush=True)
    # 정본 §10: 회차 끝나면 폰으로 판단 정보 통지(웹훅 미설정 시 자동 skip).
    _notify_webhook(tag)
    return 0


def _finalize_pipeline_state(exit_code: int):
    """파이프라인 러너 종료 직전 state 갱신."""
    st = load_state()
    if st and st.get("task") == "run":
        st["running"] = False
        st["pid"] = None
        st["finished_at"] = _now_iso()
        st["last_exit_code"] = exit_code
        save_state(st)


# ----------------------------------------------------------------------------
# Discord 봇
# ----------------------------------------------------------------------------

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def _guild_obj():
    gid = _CONFIG.get("guild_id")
    return discord.Object(id=gid) if gid else None


def _channel_allowed(interaction: discord.Interaction) -> bool:
    cid = _CONFIG.get("channel_id")
    if cid is None:
        return True
    return interaction.channel_id == cid


def _refresh_running_flag(st):
    """state는 running=true인데 프로세스가 죽었으면 stale 처리."""
    if st and st.get("running") and not is_process_alive(st.get("pid")):
        return True  # stale
    return False


def _busy_state():
    """현재 실행 중인 작업이 있으면 그 state 반환, 없으면 None."""
    st = load_state()
    if st and st.get("running") and is_process_alive(st.get("pid")):
        return st
    return None


@client.event
async def on_ready():
    g = _guild_obj()
    if g:
        tree.copy_global_to(guild=g)
        await tree.sync(guild=g)
    else:
        await tree.sync()
    print(f"[ready] {client.user} 로그인 완료. AAA_ROOT={_CONFIG['root']}")


# ---- /상태 ----
@tree.command(name="상태", description="현재 AAA 실행 상태를 보여준다")
async def 상태(interaction: discord.Interaction):
    if not _channel_allowed(interaction):
        return await interaction.response.send_message("이 채널에서는 사용할 수 없다.", ephemeral=True)
    st = load_state()
    if not st:
        return await interaction.response.send_message("no active state (상태 기록 없음)")

    stale = _refresh_running_flag(st)
    alive = is_process_alive(st.get("pid"))
    lines = [
        "AAA Status",
        "",
        f"running: {st.get('running')}" + ("  (stale: 프로세스 죽음)" if stale else ""),
        f"task: {st.get('task')}",
        f"channel: {st.get('channel')}",
        f"pid: {st.get('pid')}  (alive: {alive})",
        f"started_at: {st.get('started_at')}",
        f"finished_at: {st.get('finished_at')}",
        f"last_exit_code: {st.get('last_exit_code')}",
        f"log_file: {st.get('log_file')}",
    ]
    await interaction.response.send_message("```\n" + "\n".join(lines) + "\n```")


# ---- /로그 ----
@tree.command(name="로그", description="최근 로그를 보여준다 (기본 80줄, 최대 200줄)")
@app_commands.describe(줄수="표시할 줄 수 (최대 200)")
async def 로그(interaction: discord.Interaction, 줄수: int = DEFAULT_TAIL_LINES):
    if not _channel_allowed(interaction):
        return await interaction.response.send_message("이 채널에서는 사용할 수 없다.", ephemeral=True)
    n = max(1, min(int(줄수), MAX_TAIL_LINES))
    st = load_state()
    if not st or not st.get("log_file"):
        return await interaction.response.send_message("표시할 로그가 없다.")
    log_path = Path(st["log_file"])
    if not log_path.exists():
        return await interaction.response.send_message(f"로그 파일이 없다: {log_path}")
    text = tail_file(log_path, n)
    if not text.strip():
        text = "(빈 로그)"
    await interaction.response.send_message(f"`{log_path.name}` (최근 {n}줄)\n```\n{text}\n```")


# ---- /실행 ----
@tree.command(name="실행", description="AAA 전체 파이프라인 실행 (arun.sh와 동일: pull→batch→analyze→commit→push)")
@app_commands.describe(채널="실행할 채널/태그 (예: vtx_18)")
async def 실행(interaction: discord.Interaction, 채널: str):
    if not _channel_allowed(interaction):
        return await interaction.response.send_message("이 채널에서는 사용할 수 없다.", ephemeral=True)
    if not validate_channel_name(채널):
        return await interaction.response.send_message(
            f"잘못된 채널명: `{채널}`\n허용: 영문/숫자/_/- 만 가능", ephemeral=True)
    busy = _busy_state()
    if busy:
        return await interaction.response.send_message(
            f"이미 실행 중이다: {busy.get('task')} {busy.get('channel')} (pid {busy.get('pid')})\n"
            f"`/상태`로 확인하라.", ephemeral=True)

    await interaction.response.defer()
    state, log_path = start_background_task("run", 채널, mode="pipeline")
    msg = (
        "Started AAA run (arun.sh 동일 파이프라인)\n\n"
        f"channel: {채널}\n"
        f"pid: {state['pid']}\n"
        f"log: {log_path.name}\n\n"
        "단계: git pull → batch → analyze → add → commit → push\n"
        "진행은 `/상태`, `/로그`로 확인하라."
    )
    await interaction.followup.send(f"```\n{msg}\n```")


# ---- /분석 ----
@tree.command(name="분석", description="분석 스크립트 실행 (analyze_h1b.py)")
@app_commands.describe(채널="분석할 채널/태그 (예: vtx_18)")
async def 분석(interaction: discord.Interaction, 채널: str):
    if not _channel_allowed(interaction):
        return await interaction.response.send_message("이 채널에서는 사용할 수 없다.", ephemeral=True)
    if not validate_channel_name(채널):
        return await interaction.response.send_message(
            f"잘못된 채널명: `{채널}`\n허용: 영문/숫자/_/- 만 가능", ephemeral=True)
    busy = _busy_state()
    if busy:
        return await interaction.response.send_message(
            f"이미 실행 중이다: {busy.get('task')} {busy.get('channel')} (pid {busy.get('pid')})",
            ephemeral=True)

    await interaction.response.defer()
    state, log_path = start_background_task("analyze", 채널, mode="analyze")
    msg = (
        "Started analyze\n\n"
        f"channel: {채널}\n"
        f"pid: {state['pid']}\n"
        f"log: {log_path.name}\n\n"
        "결과는 `/로그`로 확인하라."
    )
    await interaction.followup.send(f"```\n{msg}\n```")


# ---- /검증 ----
@tree.command(name="검증", description="검증 스크립트 실행 (verify_channel.py)")
@app_commands.describe(채널="검증할 채널/태그 (예: vtx_18)")
async def 검증(interaction: discord.Interaction, 채널: str):
    if not _channel_allowed(interaction):
        return await interaction.response.send_message("이 채널에서는 사용할 수 없다.", ephemeral=True)
    if not validate_channel_name(채널):
        return await interaction.response.send_message(
            f"잘못된 채널명: `{채널}`\n허용: 영문/숫자/_/- 만 가능", ephemeral=True)
    busy = _busy_state()
    if busy:
        return await interaction.response.send_message(
            f"이미 실행 중이다: {busy.get('task')} {busy.get('channel')} (pid {busy.get('pid')})",
            ephemeral=True)

    await interaction.response.defer()
    # verify_channel.py 는 인자 2개 필수: <runs.jsonl> <tag>. runs.jsonl 은 봇이 자동 주입.
    state, log_path = start_background_task("verify", 채널, mode="verify")
    msg = (
        "Started verify\n\n"
        f"channel: {채널}\n"
        f"pid: {state['pid']}\n"
        f"log: {log_path.name}\n\n"
        "결과는 `/로그`로 확인하라."
    )
    await interaction.followup.send(f"```\n{msg}\n```")


# ---- /명령 (관리자 전용 임의 명령 실행) ----
@tree.command(name="명령", description="[관리자 전용] AAA 폴더에서 명령 실행 (SSH 유사)")
@app_commands.describe(명령어="실행할 명령 (예: git status, dir, git push)")
async def 명령(interaction: discord.Interaction, 명령어: str):
    # 채널 제한
    if not _channel_allowed(interaction):
        return await interaction.response.send_message("이 채널에서는 사용할 수 없다.", ephemeral=True)
    # 관리자 본인만
    admin = _CONFIG.get("admin_user_id")
    if admin is None:
        return await interaction.response.send_message(
            "`/명령`은 AAA_ADMIN_USER_ID 가 .env 에 설정돼야 사용할 수 있다.", ephemeral=True)
    if interaction.user.id != admin:
        return await interaction.response.send_message("권한 없음. 관리자만 사용할 수 있다.", ephemeral=True)
    # 명령어 검사
    reason = check_command_allowed(명령어)
    if reason:
        return await interaction.response.send_message(f"거부: {reason}", ephemeral=True)

    await interaction.response.defer()
    root = _CONFIG["root"]
    log_path = make_log_file("cmd")
    started = _now_iso()
    try:
        # AAA 폴더에서만 실행(cwd 고정). shell=True 로 일반 셸 명령 형태 지원.
        # 위험 토큰/경로탈출은 check_command_allowed 에서 이미 차단.
        proc = subprocess.run(
            명령어,
            cwd=str(root),
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CMD_TIMEOUT_SEC,
            env=os.environ.copy(),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        out = f"(타임아웃: {CMD_TIMEOUT_SEC}초 초과로 강제 종료)"
        rc = -1
    except Exception as e:
        out = f"(실행 오류: {type(e).__name__}: {e})"
        rc = -1

    # 로그 기록
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"command: {명령어}\ncwd: {root}\nstarted_at: {started}\n")
            f.write(f"user_id: {interaction.user.id}\nexit_code: {rc}\n--- output ---\n{out}\n")
    except OSError:
        pass

    if not out.strip():
        out = "(출력 없음)"
    if len(out) > DISCORD_MSG_LIMIT:
        out = "...(앞부분 생략)...\n" + out[-DISCORD_MSG_LIMIT:]
    await interaction.followup.send(f"`$ {명령어}`  (exit {rc})\n```\n{out}\n```")


# ----------------------------------------------------------------------------
# 진입점
# ----------------------------------------------------------------------------

def main():
    load_config()

    # 파이프라인 러너 모드: start_background_task가 이 모드로 자신을 재실행한다.
    if len(sys.argv) >= 3 and sys.argv[1] == "--pipeline":
        tag = sys.argv[2]
        if not validate_channel_name(tag):
            print(f"[error] invalid tag: {tag}", file=sys.stderr)
            _finalize_pipeline_state(2)
            raise SystemExit(2)
        rc = 0
        try:
            rc = run_pipeline(tag)
        finally:
            _finalize_pipeline_state(rc)
        raise SystemExit(rc)

    # 봇 모드
    if not _CONFIG["token"]:
        print("[error] DISCORD_TOKEN 이 .env 에 없다.", file=sys.stderr)
        raise SystemExit(1)
    client.run(_CONFIG["token"])


if __name__ == "__main__":
    main()
