#!/usr/bin/env python3
"""runs.jsonl 분석틀 (관측 전용). python3 analyze_h1b.py [tag] [--push]"""
import json, re, sys, os, subprocess, csv
from collections import defaultdict, Counter

TID = re.compile(r"(r\d+[a-z]?)_([0-9]+)_([A-E][12])")

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

def classify(rec):
    se = rec.get("stderr") or ""; so = rec.get("stdout") or ""
    ec = rec.get("exit_code"); g = len(rec.get("generated_files") or [])
    if g == 0: return ("코더빈손","")
    t = h1b_type(se)
    if t: return ("H1b", t)
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

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    tagfilter = args[0] if args else None
    label = tagfilter if tagfilter else "all"
    outdir = os.path.join("analysis_out", label)
    os.makedirs(outdir, exist_ok=True)

    rows=[]
    for line in open("runs.jsonl"):
        line=line.strip()
        if not line: continue
        try: rec=json.loads(line)
        except: continue
        tid=str(rec.get("task_id",""))
        if tagfilter and tagfilter not in tid: continue
        m=TID.search(tid)
        if not m: continue
        cat,sub=classify(rec)
        se=(rec.get("stderr") or "")
        rows.append({"task_id":tid,"round":m.group(2),"cell":m.group(3),
            "cat":cat,"sub":sub,"exit":rec.get("exit_code"),
            "g":len(rec.get("generated_files") or []),
            "stderr_full":se,"created_at":rec.get("created_at","")})

    cells=sorted({r["cell"] for r in rows})
    rounds=sorted({r["round"] for r in rows}, key=int)

    with open(os.path.join(outdir,"rows.csv"),"w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["task_id","round","cell","cat","sub","exit","g","stderr_full","created_at"])
        for r in sorted(rows,key=lambda x:(x["cell"],x["round"])):
            w.writerow([r["task_id"],r["round"],r["cell"],r["cat"],r["sub"],
                        r["exit"],r["g"],r["stderr_full"],r["created_at"]])

    with open(os.path.join(outdir,"review.txt"),"w") as f:
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
    with open(os.path.join(outdir,"summary.json"),"w") as f:
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
    open(os.path.join(outdir,"report.txt"),"w").write("\n".join(L)+"\n")

    print(f"[완료] {outdir}/ 4파일")
    print(f"  실행 {len(rows)} | H1b {summary['exec']['h1b']} | 애매 {sum(1 for r in rows if r['cat'] in AMBIGUOUS)}줄")

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
