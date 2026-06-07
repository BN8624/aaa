# verify_channel.py — Q6 관측 전용 검증기 (파이프라인과 분리, batch/run/runner 안 건드림)
#
# 목적(progress §5): 깸이 "정상 거부 vs 진짜 깸" 중 무엇인지, 그리고 그게
#   어느 채널(stderr 예외 / stdout 반환값·메시지 / 침묵)에 나타나는지 관측.
#   → H1b 사냥기가 아니라 "반환값/stdout에서 깸을 잡아냈나"를 보는 도구.
#
# 입력: runs.jsonl (task_id 또는 tag prefix). 코드는 generated_files를 임시폴더에
#   풀어 stdin(로깅된 주입 대본)을 재생하며 실제 실행 → stdout/stderr/exit 실측.
#   ※ 파이프라인 흐름과 분리. 깸을 줄이는 개입 아님(관측만).
#
# 3상태 판정(observable):
#   broken : 진짜 깸. exit!=0(timeout 제외) 이거나 stderr에 미처리 예외 트레이스.
#   reject : 정상 동작했고 stdout에 도메인 거부 신호({'success':False}/Unauthorized/
#            Insufficient/denied 등). 코드가 의도한 거부 분기 → 깸 아님.
#   alive  : 정상 동작, 거부 신호 없음(성공 경로 주행).
#   silent : 출력이 사실상 없음(메뉴앞 즉시 종료 등) → 관측천장 ①/② 잔재.
#
# 채널 표기와 별개로, 정적 H1b 후보(import/멤버 계약 깨짐)도 병기해 교차확인.

import json, re, sys, tempfile, subprocess, os, shutil, collections

REJECT_PAT = re.compile(
    r"(['\"]success['\"]\s*:\s*False|['\"]status['\"]\s*:\s*['\"](error|denied)['\"]"
    r"|Unauthorized|Insufficient|not enough|denied|privileges|not recognized"
    r"|not found|Payment failed|Login failed|invalid|cannot be|must be)", re.I)
TRACE_PAT = re.compile(r"Traceback \(most recent call last\)", re.M)
H1B_PAT = re.compile(
    r"(AttributeError|has no attribute|not subscriptable|unhashable type"
    r"|NameError|is not defined|unexpected keyword argument"
    r"|missing \d+ required positional|takes \d+ positional)", re.I)


def load(path):
    rows = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    pass
    return rows


def is_fake(r):
    se = str(r.get('stderr') or '')
    if 'VERTEX_API_KEY' in se:
        return True
    if r.get('exit_code') == -1 and not (r.get('generated_files') or {}):
        return True
    return False


def files(r):
    gf = r.get('generated_files') or {}
    if isinstance(gf, dict):
        return {k: str(v) for k, v in gf.items()}
    out = {}
    if isinstance(gf, list):
        for x in gf:
            if isinstance(x, dict):
                out[x.get('name', '?')] = str(x.get('content') or x.get('code') or '')
    return out


def pick_entry(fs):
    for cand in ('main.py', 'app.py', 'run.py', '__main__.py'):
        if cand in fs:
            return cand
    # fallback: file containing __main__ guard
    for n, c in fs.items():
        if '__main__' in c:
            return n
    return next(iter(fs), None)


def run_cell(r, timeout=20):
    fs = files(r)
    if not fs:
        return None
    entry = pick_entry(fs)
    stdin_input = r.get('stdin')
    if stdin_input is not None and not isinstance(stdin_input, str):
        stdin_input = str(stdin_input)
    wd = tempfile.mkdtemp(prefix='vc_')
    try:
        for name, content in fs.items():
            # only write plain .py-ish names; skip pathological names
            safe = os.path.join(wd, os.path.basename(name))
            with open(safe, 'w') as f:
                f.write(content)
        kw = dict(cwd=wd, capture_output=True, text=True, timeout=timeout)
        if stdin_input is None:
            kw['stdin'] = subprocess.DEVNULL
        else:
            kw['input'] = stdin_input
        p = subprocess.run([sys.executable, os.path.basename(entry)], **kw)
        return {'exit': p.returncode, 'stdout': p.stdout or '', 'stderr': p.stderr or '',
                'timeout': False, 'entry': entry}
    except subprocess.TimeoutExpired as e:
        return {'exit': None, 'stdout': e.stdout or '', 'stderr': e.stderr or '',
                'timeout': True, 'entry': entry}
    finally:
        shutil.rmtree(wd, ignore_errors=True)


INPUTMISMATCH_PAT = re.compile(
    r"usage:|error: the following arguments are required"
    r"|Invalid number of arguments|Expected \d+ .*?(values|arguments)"
    r"|the following arguments|too few arguments", re.I)


def _argv_based(code_all):
    # code reads command-line args (argparse / sys.argv[1:]) rather than stdin input()
    return bool(re.search(r"argparse|sys\.argv\[1", code_all)) and \
        not re.search(r"\binput\s*\(", code_all)


def classify(res, code_all):
    if res is None:
        return 'nofiles', '-'
    out, err = res['stdout'], res['stderr']
    # channel: where does anything show up
    if res['timeout']:
        return 'broken', 'timeout'
    # input-channel mismatch: code expects argv, runner injected stdin → not a real break.
    if res['exit'] not in (0, None) and (
            INPUTMISMATCH_PAT.search(err) or
            (_argv_based(code_all) and ('argument' in err.lower() or 'usage' in err.lower()))):
        return 'inputmismatch', 'argv-vs-stdin'
    if TRACE_PAT.search(err) or (res['exit'] not in (0, None) and err.strip()):
        ch = 'stderr-exc'
        return 'broken', ch
    if res['exit'] not in (0, None):
        return 'broken', 'exit%s' % res['exit']
    # exit 0 from here
    body = (out + '\n' + err).strip()
    if len(body) < 3:
        return 'silent', 'none'
    if REJECT_PAT.search(out):
        return 'reject', 'stdout-return'
    return 'alive', 'stdout-ok'


def main():
    if len(sys.argv) < 3:
        print("usage: verify_channel.py <runs.jsonl> <tag-or-taskid> [--exit0-only]")
        sys.exit(2)
    path, sel = sys.argv[1], sys.argv[2]
    exit0_only = '--exit0-only' in sys.argv[3:]
    rows = load(path)
    # dedup real rows by task_id (later line wins)
    byid = {}
    for r in rows:
        tid = str(r['task_id'])
        if tid == sel or tid.startswith(sel + '_') or sel == 'ALL':
            if not is_fake(r):
                byid[tid] = r
    if not byid:
        print("no matching real rows for:", sel)
        sys.exit(1)
    obs = collections.Counter()
    ch = collections.Counter()
    rows_out = []
    for tid in sorted(byid):
        r = byid[tid]
        if exit0_only and r.get('exit_code') != 0:
            continue
        res = run_cell(r)
        code_all = "\n".join(files(r).values())
        state, channel = classify(res, code_all)
        h1b = 'H1b?' if H1B_PAT.search(
            (res['stderr'] if res else '') + code_all) else ''
        obs[state] += 1
        ch[channel] += 1
        rows_out.append((tid, state, channel, h1b,
                         (res['exit'] if res else None)))
    w = max((len(t) for t, *_ in rows_out), default=8)
    print(f"{'task_id':{w}}  state    channel        logged_exit  flag")
    for tid, st, c, h, ex in rows_out:
        print(f"{tid:{w}}  {st:7}  {c:13}  {str(ex):>5}        {h}")
    print("\nobservable:", dict(obs))
    print("channel   :", dict(ch))


if __name__ == '__main__':
    main()
