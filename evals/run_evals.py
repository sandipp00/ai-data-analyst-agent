"""Score the agent against reference SQL: python -m evals.run_evals [--limit N]
Results are compared as multisets of rounded values, ignoring column names and order
(unless the reference has ORDER BY ... LIMIT, where the set still matches)."""
import argparse
import json
import time
from pathlib import Path

from analyst import db, run_question


def normalize(df):
    def cell(v):
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return str(v)
    return sorted(tuple(cell(v) for v in row) for row in df.itertuples(index=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--sleep", type=float, default=0, help="seconds between cases")
    args = ap.parse_args()
    cases = json.loads((Path(__file__).parent / "cases.json").read_text())[: args.limit]
    passed = 0
    for i, case in enumerate(cases, 1):
        t0 = time.time()
        try:
            out = run_question(case["q"])
            if case["sql"] is None:  # should be refused
                ok = out.get("df") is None
            else:
                ok = out.get("df") is not None and normalize(out["df"]) == normalize(db.run_query(case["sql"]))
            note = "" if ok else f"\n    got SQL: {out.get('sql')}\n    answer: {out.get('answer', '')[:150]}"
        except Exception as e:
            ok, note = False, f"\n    error: {e}"
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {i:2d}. {case['q']} ({time.time() - t0:.0f}s){note}", flush=True)
        time.sleep(args.sleep)
    print(f"\n{passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
