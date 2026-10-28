"""Score the agent against reference SQL: python -m evals.run_evals [--limit N] [--only N ...]
Results are compared as multisets of rounded values, ignoring column names and order
; extra result columns are allowed."""
import argparse
import json
import time as clock
from datetime import datetime, time
from pathlib import Path

from analyst import db, run_question


def normalize(df):
    def cell(v):
        if isinstance(v, datetime) and v.time() == time.min:
            v = v.date()  # date_trunc returns a midnight timestamp unless cast to date
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return str(v)
    return sorted(tuple(cell(v) for v in row) for row in df.itertuples(index=False))


def matches(got, expected) -> bool:
    """True if every reference column appears in the result (extra columns are fine)
    and the rows agree on those columns."""
    if len(got) != len(expected):
        return False
    if expected.empty:
        return len(got.columns) >= len(expected.columns)
    used: list[int] = []
    for j in range(expected.shape[1]):
        want = normalize(expected.iloc[:, [j]])
        for k in range(got.shape[1]):
            if k not in used and normalize(got.iloc[:, [k]]) == want:
                used.append(k)
                break
        else:
            return False
    return normalize(got.iloc[:, used]) == normalize(expected)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", type=int, nargs="+", help="1-based case numbers to run")
    ap.add_argument("--sleep", type=float, default=0, help="seconds between cases")
    args = ap.parse_args()
    all_cases = json.loads((Path(__file__).parent / "cases.json").read_text())
    picked = args.only or range(1, len(all_cases) + 1)
    cases = [(i, all_cases[i - 1]) for i in picked][: args.limit]
    passed = 0
    for i, case in cases:
        t0 = clock.time()
        try:
            out = run_question(case["q"], case.get("history"))
            if case["sql"] is None:  # should be refused
                ok = out.get("df") is None
            else:
                refs = case["sql"] if isinstance(case["sql"], list) else [case["sql"]]  # any may match
                ok = out.get("df") is not None and any(matches(out["df"], db.run_query(r)) for r in refs)
            note = "" if ok else f"\n    got SQL: {out.get('sql')}\n    answer: {out.get('answer', '')[:150]}"
        except Exception as e:
            ok, note = False, f"\n    error: {e}"
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {i:2d}. {case['q']} ({clock.time() - t0:.0f}s){note}", flush=True)
        clock.sleep(args.sleep)
    print(f"\n{passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
