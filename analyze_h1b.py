#!/usr/bin/env python3
"""runs.jsonl 분석틀 (관측 전용). python3 analyze_h1b.py [tag] [--push] [--no-replay]

정적 분류(cat) + verify_channel 재실행 분류(runstate)를 한 표에 합친다.
- cat       : runs.jsonl에 로깅된 stderr/exit 텍스트만 보는 정적 라벨(기존).
- runstate  : generated_files를 재실행해 얻는 alive/reject/broken/silent/inputmismatch.
              exit0가짜/exit0정상/timeout 같은 '추측' 라벨을 실측으로 해소(Q8).
재실행은 verify_channel.run_cell/classify를 그대로 호출(도구 통합, 로직 1곳).
--no-replay 면 재실행 생략(기존 정적 동작).
"""
import json, re, sys, os, subprocess, csv
from collections import defaultdict, Counter

# Windows cp949 콘솔에서 한글/기호 print 크래시 방지(진입점에서 1회).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Q8 통합: 재실행 관측기. import 실패해도 정적 분석은 돌게 가드.
try:
    import verify_channel as vc
    _HAS_VC = True
except Exception as _e:
    _HAS_VC = False
    _VC_ERR = _e

TID = re.compile(r"(\w+?)_([0-9]+)_([A-E][12])")   # 세션태그 무관(r0605b·h4b 등 모두). 회차=\d+, 칸=[A-E][12]

def h1b_type(se):
    if "ImportError" in se or "cannot import name" in se or "ModuleNotFoundError" in se:
        return "import불일치"
    if "TypeError" in se and ("unexpected keyword argument" in se
                              or "positional argument" in se
                              or ("takes" in se and "argument" in se)):
        return "시그니처불일치"
    if "TypeError" in se and "unhashable" in se: return "계약(unhashable)"
    if "AttributeError" in se: return "계약(AttributeError)"
    if "NameError" in se: return "계약(NameError)"
    return None

def generated_main(rec):
    gf = rec.get("generated_files") or {}
    if isinstance(gf, dict):
        return str(gf.get("main.py") or "")
    if isinstance(gf, list):
        for item in gf:
            if isinstance(item, dict) and item.get("name") == "main.py":
                return str(item.get("content") or item.get("code") or "")
    return ""

def stdin_text(rec):
    stdin = rec.get("stdin")
    if stdin is None: return ""
    return stdin if isinstance(stdin, str) else str(stdin)

def has_input_loop(code):
    return bool(re.search(r"\binput\s*\(|while\s+(True|1)\s*:", code))

def stdin_has_exit(stdin):
    return any(line.strip().lower() in {"exit","quit"} for line in stdin.splitlines())

def classify(rec):
    se = rec.get("stderr") or ""; so = rec.get("stdout") or ""
    ec = rec.get("exit_code"); g = len(rec.get("generated_files") or [])
    if g == 0: return ("코더빈손","")
    t = h1b_type(se)
    if t: return ("H1b", t)
    if "Invalid JSON input" in se:
        return ("STDIN_FORMAT_MISMATCH","Invalid JSON input")
    if "TimeoutExpired" in se and has_input_loop(generated_main(rec)) and not stdin_has_exit(stdin_text(rec)):
        return ("STDIN_EXIT_MISMATCH","input loop without exit/quit")
    if "EOFError" in se:
        return ("메뉴앞EOF","") if so.strip()=="" else ("메뉴중EOF","")
    if "usage:" in se or "the following arguments are required" in se \
       or (ec==2 and "argument" in se): return ("argparse","")
    if ec==0:
        return ("exit0가짜","") if so.strip()=="" else ("exit0정상","")
    # H1c: import/시그니처는 통과(파일간 호출 성공), 실행 중 값/상태로 죽음.
    #      H1b(계약 파괴)와 구분되는 별도 범주. 멀티파일에서만 의미.
    if "TimeoutExpired" in se: return ("timeout","")
    if se.strip() and any(e in se for e in
        ["ValueError","KeyError","IndexError","ZeroDivisionError",
         "RuntimeError","AssertionError","FileNotFoundError"]):
        return ("H1c런타임값", se.strip().splitlines()[-1][:45])
    if se.strip(): return ("기타예외","")
    return ("미분류","")

AMBIGUOUS = {"기타예외","미분류","코더빈손"}

# 재실행 결과가 '정적 cat을 뒤집었나' 판단용: 정적은 죽었다/빈손이라 본 칸을
# 재실행은 살아있다(alive/reject)고 보거나 그 반대인 경우를 교차표로 노출.
def replay_state(rec):
    """verify_channel로 1행 재실행 → (runstate, runchannel, h1b_flag, replay_exit).
    재실행 불가/모듈 없음/가짜행이면 ('-', '-', '', None)."""
    if not _HAS_VC:
        return ("-","","",None)
    try:
        if vc.is_fake(rec):
            return ("fake","","",None)
        res = vc.run_cell(rec)
        code_all = "\n".join(vc.files(rec).values())
        state, channel = vc.classify(res, code_all)
        h1b = "H1b?" if vc.H1B_PAT.search(((res.get("stderr") if res else "") or "") + code_all) else ""
        return (state, channel, h1b, (res.get("exit") if res else None))
    except Exception as e:
        return ("replayerr", str(e)[:30], "", None)

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    tagfilter = args[0] if args else None
    label = tagfilter if tagfilter else "all"
    outdir = os.path.join("analysis_out", label)
    os.makedirs(outdir, exist_ok=True)
    do_replay = ("--no-replay" not in flags) and _HAS_VC
    if "--no-replay" not in flags and not _HAS_VC:
        print(f"[경고] verify_channel import 실패 → 재실행 생략(정적만): {_VC_ERR}")

    rows=[]
    for line in open("runs.jsonl", encoding="utf-8"):
        line=line.strip()
        if not line: continue
        try: rec=json.loads(line)
        except: continue
        tid=str(rec.get("task_id",""))
        if tagfilter and not tid.startswith(tagfilter + "_"): continue
        m=TID.search(tid)
        if not m: continue
        cat,sub=classify(rec)
        se=(rec.get("stderr") or "")
        if do_replay:
            runstate,runchannel,run_h1b,replay_exit = replay_state(rec)
        else:
            runstate,runchannel,run_h1b,replay_exit = ("-","","",None)
        rows.append({"task_id":tid,"round":m.group(2),"cell":m.group(3),
            "cat":cat,"sub":sub,"exit":rec.get("exit_code"),
            "runstate":runstate,"runchannel":runchannel,
            "run_h1b":run_h1b,"replay_exit":replay_exit,
            "g":len(rec.get("generated_files") or []),
            "stderr_full":se,"created_at":rec.get("created_at","")})

    cells=sorted({r["cell"] for r in rows})
    rounds=sorted({r["round"] for r in rows}, key=int)

    with open(os.path.join(outdir,"rows.csv"),"w",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(["task_id","round","cell","cat","sub","exit",
                    "runstate","runchannel","run_h1b","replay_exit",
                    "g","stderr_full","created_at"])
        for r in sorted(rows,key=lambda x:(x["cell"],x["round"])):
            w.writerow([r["task_id"],r["round"],r["cell"],r["cat"],r["sub"],
                        r["exit"],r["runstate"],r["runchannel"],r["run_h1b"],
                        r["replay_exit"],r["g"],r["stderr_full"],r["created_at"]])

    with open(os.path.join(outdir,"review.txt"),"w",encoding="utf-8") as f:
        amb=[r for r in rows if r["cat"] in AMBIGUOUS]
        f.write(f"# 분류 애매/확인필요 {len(amb)}줄 (전문). 분류기 점검은 여기부터.\n\n")
        for r in amb:
            f.write(f"=== {r['task_id']} [{r['cat']}] exit={r['exit']} g={r['g']}\n")
            f.write((r["stderr_full"].strip() or "(stderr 없음)")+"\n\n")

    cell_round=defaultdict(lambda: defaultdict(list))
    for r in rows: cell_round[r["cell"]][r["round"]].append(r["cat"])
    summary={"label":label,"n_rows":len(rows),"cells":cells,"rounds":rounds}
    exec_tally=Counter(r["cat"] for r in rows)
    exec_h1b_types=Counter(r["sub"] for r in rows if r["cat"]=="H1b")
    summary["exec"]={"tally":dict(exec_tally),
        "h1b":sum(1 for r in rows if r["cat"]=="H1b"),
        "h1b_types":dict(exec_h1b_types)}
    # Q8 통합: 재실행 분류 집계 + 정적 cat × 재실행 runstate 교차표.
    replayed=[r for r in rows if r["runstate"] not in ("-",)]
    runstate_tally=Counter(r["runstate"] for r in replayed)
    runchannel_tally=Counter(r["runchannel"] for r in replayed if r["runchannel"])
    crosstab=defaultdict(Counter)
    for r in replayed:
        crosstab[r["cat"]][r["runstate"]]+=1
    summary["replay"]={
        "n_replayed":len(replayed),
        "runstate":dict(runstate_tally),
        "runchannel":dict(runchannel_tally),
        "run_h1b_flags":sum(1 for r in replayed if r["run_h1b"]),
        "cat_x_runstate":{k:dict(v) for k,v in crosstab.items()}}
    split=[]; rh=rt=0
    for c in cells:
        for rd in rounds:
            cats=cell_round[c].get(rd,[])
            if not cats: continue
            rt+=1
            if "H1b" in cats: rh+=1
            if "H1b" in cats and any(x!="H1b" for x in cats): split.append(f"{c} r{rd}")
    summary["round"]={"h1b_cells":rh,"total_cells":rt}
    summary["nondeterministic_splits"]=split
    summary["per_cell"]={}
    for c in cells:
        lst=[r for r in rows if r["cell"]==c]
        summary["per_cell"][c]={"n_exec":len(lst),
            "h1b":sum(1 for r in lst if r["cat"]=="H1b"),
            "h1b_types":dict(Counter(r["sub"] for r in lst if r["cat"]=="H1b")),
            "cats":dict(Counter(r["cat"] for r in lst))}
    with open(os.path.join(outdir,"summary.json"),"w",encoding="utf-8") as f:
        json.dump(summary,f,ensure_ascii=False,indent=2)

    L=[f"분석: {label} | {len(rows)}실행 | 칸 {len(cells)} 회차 {rounds}",
       "="*50,"칸별 H1b 분포 (분모=실행수)","="*50]
    for c in cells:
        s=summary["per_cell"][c]
        L.append(f"\n[{c}] H1b {s['h1b']}/{s['n_exec']}")
        if s["h1b_types"]:
            L.append("  유형: "+", ".join(f"{k}×{v}" for k,v in s["h1b_types"].items()))
        det=[]
        for rd in rounds:
            cats=cell_round[c].get(rd,[])
            if not cats: continue
            nh=sum(1 for x in cats if x=="H1b")
            t=f"r{rd}:{nh}/{len(cats)}"
            if "H1b" in cats and any(x!="H1b" for x in cats): t+="*"
            det.append(t)
        L.append("  회차(H1b/실행): "+" ".join(det))
    L+=["\n"+"="*50,"★ 비결정성 (* 동일칸·회차 갈림)","="*50,
        "  "+(", ".join(split) if split else "(없음)"),
        "\n"+"="*50,f"실행단위 집계 ({len(rows)}실행)","="*50]
    for k,v in sorted(exec_tally.items(),key=lambda x:-x[1]):
        L.append(f"  {k:>12}: {v}")
    if exec_h1b_types:
        L.append("  └ H1b 유형:")
        for k,v in sorted(exec_h1b_types.items(),key=lambda x:-x[1]):
            L.append(f"      {k:>18}: {v}")
    L+=["\n"+"="*50,"회차단위(칸×회차 H1b 노출)","="*50,f"  {rh}/{rt}"]
    if replayed:
        L+=["\n"+"="*50,f"★ 재실행 관측 (verify_channel 통합, {len(replayed)}/{len(rows)}행)","="*50]
        for k,v in sorted(runstate_tally.items(),key=lambda x:-x[1]):
            L.append(f"  {k:>13}: {v}")
        if runchannel_tally:
            L.append("  └ 채널:")
            for k,v in sorted(runchannel_tally.items(),key=lambda x:-x[1]):
                L.append(f"      {k:>16}: {v}")
        if any(r["run_h1b"] for r in replayed):
            L.append(f"  └ 재실행 H1b? 플래그: {sum(1 for r in replayed if r['run_h1b'])}")
        L+=["\n"+"-"*50,"정적 cat × 재실행 runstate (추측 라벨이 무엇으로 풀렸나)","-"*50]
        for cat in sorted(crosstab, key=lambda c:-sum(crosstab[c].values())):
            inner=", ".join(f"{s}×{n}" for s,n in sorted(crosstab[cat].items(),key=lambda x:-x[1]))
            L.append(f"  {cat:>12} → {inner}")
    elif "--no-replay" in flags:
        L.append("\n(재실행 생략: --no-replay)")
    open(os.path.join(outdir,"report.txt"),"w",encoding="utf-8").write("\n".join(L)+"\n")

    print(f"[완료] {outdir}/ 4파일")
    rs = (" | 재실행 " + ", ".join(f"{k}×{v}" for k,v in runstate_tally.most_common())) if replayed else ""
    print(f"  실행 {len(rows)} | H1b {summary['exec']['h1b']} | 애매 {sum(1 for r in rows if r['cat'] in AMBIGUOUS)}줄{rs}")

    if "--push" in flags:
        try:
            subprocess.run(["git","add","analyze_h1b.py",outdir],check=True)
            subprocess.run(["git","commit","-m",f"analysis: {label}"],check=True)
            subprocess.run(["git","push"],check=True)
            print("[푸시] 완료")
        except subprocess.CalledProcessError as e:
            print(f"[푸시 실패] {e}")

if __name__=="__main__":
    main()
