#!/usr/bin/env python3
"""
§4 (길A) 분석: r0605_1~r0605_5 50줄을 읽어 칸별·회차별 H1b 분포를 낸다.
- 규칙: stderr 전문을 읽고 분류(머리글자 금지). H1_RUN 교훈 반영.
- 입력: runs.jsonl (0단계 8필드). tag로 회차 구분.
사용법: python3 analyze_h1b.py runs.jsonl
"""
import json, sys, re
from collections import defaultdict

TAGS = [f"r0605_{i}" for i in range(1, 6)]
CELLS = ["A1","A2","B1","B2","C1","C2","D1","D2","E1","E2"]

def classify(rec):
    exit_code = rec.get("exit_code", rec.get("exit"))
    stderr = (rec.get("stderr") or "")
    stdout = (rec.get("stdout") or "")
    generated = rec.get("generated_files", rec.get("generated", []))
    g = len(generated) if isinstance(generated, list) else generated

    if g == 0:
        return ("코더빈손", "generated=[] (500/인프라)")
    if "ImportError" in stderr or "cannot import name" in stderr or \
       ("ModuleNotFoundError" in stderr and g >= 2):
        return ("H1b", "import불일치")
    if "TypeError" in stderr and ("unexpected keyword argument" in stderr or
                                  "positional argument" in stderr or
                                  "argument" in stderr):
        return ("H1b", "시그니처불일치")
    if "AttributeError" in stderr and "object has no attribute" in stderr:
        return ("H1b", "기타계약(AttributeError)")
    if "NameError" in stderr:
        return ("H1b", "기타계약(NameError)")
    if "EOFError" in stderr:
        if stdout.strip() == "":
            return ("메뉴앞EOF", "첫 input EOFError(stdout빔)")
        else:
            return ("메뉴중EOF", "메뉴 일부 통과 후 EOFError(stdout있음)")
    if "usage:" in stderr or "error: the following arguments are required" in stderr \
       or (exit_code == 2 and "argument" in stderr):
        return ("argparse", "stdin무력(명령행인자)")
    if exit_code == 0:
        if stdout.strip() == "":
            return ("exit0가짜", "stdout빔(가짜 의심)")
        else:
            return ("exit0정상", "stdout있음(동작 추정)")
    if stderr.strip():
        first = stderr.strip().splitlines()[-1][:60]
        return ("기타예외", first)
    return ("미분류", f"exit={exit_code} g={g}")

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "runs.jsonl"
    grid = defaultdict(dict)
    raw = defaultdict(dict)
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            tag = rec.get("tag", "")
            if tag not in TAGS:
                continue
            task = rec.get("task_id", rec.get("task", ""))
            m = re.search(r"\b([A-E][12])\b", str(task))
            cell = m.group(1) if m else task
            if cell not in CELLS:
                continue
            cat, sub = classify(rec)
            grid[tag][cell] = (cat, sub)
            raw[cell][tag] = (cat, sub)

    print("="*78)
    print("회차별 × 칸별 결과 (대분류)")
    print("="*78)
    header = "칸 |" + "|".join(f"{t.split('_')[1]:>10}" for t in TAGS)
    print(header)
    print("-"*len(header))
    for cell in CELLS:
        row = f"{cell:>2} |"
        for t in TAGS:
            cat = grid[t].get(cell, ("-",""))[0]
            row += f"{cat:>10}|"
        print(row)

    print()
    print("="*78)
    print("칸별 H1b 분포 — 5회 중 몇 회 H1b로 죽나 + 유형 + 안 죽은 회차 결말")
    print("="*78)
    for cell in CELLS:
        h1b = [(t, raw[cell][t][1]) for t in TAGS
               if raw[cell].get(t, ("",""))[0] == "H1b"]
        non = [(t.split('_')[1], raw[cell][t][0]) for t in TAGS
               if raw[cell].get(t, ("",""))[0] not in ("H1b","결측")]
        n_h1b = len(h1b)
        types = sorted(set(s for _, s in h1b))
        print(f"\n[{cell}]  H1b {n_h1b}/5")
        print(f"    유형: {', '.join(types) if types else '(H1b 없음)'}")
        if non:
            print(f"    H1b 아닌 회차: " + ", ".join(f"{r}:{c}" for r, c in non))

    print()
    print("="*78)
    print("전체 유형 집계 (50칸)")
    print("="*78)
    tally = defaultdict(int)
    subtally = defaultdict(int)
    for t in TAGS:
        for cell in CELLS:
            cat, sub = grid[t].get(cell, ("결측",""))
            tally[cat] += 1
            if cat == "H1b":
                subtally[sub] += 1
    for cat, n in sorted(tally.items(), key=lambda x: -x[1]):
        print(f"  {cat:>14}: {n}")
    if subtally:
        print("  └ H1b 세부:")
        for sub, n in sorted(subtally.items(), key=lambda x: -x[1]):
            print(f"      {sub:>22}: {n}")

if __name__ == "__main__":
    main()
