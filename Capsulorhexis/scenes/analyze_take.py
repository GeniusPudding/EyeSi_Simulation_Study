"""Post-mortem for one recorded pull ("black box" reader).

Two recordings are written every session and this reads both:

  diag_last.csv          one row per STEP, always on, tiny. Mechanics (speed, stretch,
                         clamps, rewinds, glued spots) AND the tear (crack length, c, tip
                         radius, and WHY the tear did or did not advance that step).
  stress_log_<take>.jsonl  one entry per published FRAME, only with CAP_STRESS_LOG=1. The
                         full per-triangle sigma1/sigma2/direction field plus the crack path.

Usage:
    py -3.12 analyze_take.py                    # newest of each, in this folder
    py -3.12 analyze_take.py diag_last.csv
    py -3.12 analyze_take.py stress_log_1.jsonl

The question this is built to answer is "I pulled and nothing tore -- what stopped it?",
which the why-histogram answers directly: it is how the two safety gates that were refusing
91.6% of all tearing opportunities were found, after the viewport showed nothing at all.
"""
import csv
import glob
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def _bar(frac, width=28):
    n = int(round(frac * width))
    return "#" * n + "." * (width - n)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f"{path}: empty")
        return
    print(f"\n=== {os.path.basename(path)} - {len(rows)} steps, "
          f"t {rows[0]['t']} .. {rows[-1]['t']} s ===")

    def col(name, cast=float, default=0.0):
        out = []
        for r in rows:
            try:
                out.append(cast(r.get(name, default)))
            except (TypeError, ValueError):
                out.append(default)
        return out

    crack = col("crack", int, 0)
    if any(crack):
        cs = col("c")
        print(f"crack: {crack[0]} -> {max(crack)} vertices   peak c = {max(cs):.2f}")
        grew = sum(1 for a, b in zip(crack, crack[1:]) if b > a)
        print(f"steps that actually advanced the crack: {grew} of {len(rows)} "
              f"({grew / len(rows) * 100:.1f}%)")
    else:
        print("crack: never grew (tearing off, or nothing ever met the criterion)")

    why = Counter(r.get("why", "").strip("'\"") for r in rows if r.get("why"))
    if why:
        print("\nwhy the tear did or did not advance:")
        for k, v in why.most_common():
            print(f"  {v:6d}  {v / len(rows) * 100:5.1f}%  {_bar(v / len(rows))}  {k}")

    glued = col("glued", int, 0)
    if any(glued):
        print(f"\nadhesion: {glued[0]} -> {glued[-1]} spots "
              f"({glued[0] - min(glued)} released)")
    # health flags worth knowing about after the fact
    for name, label in (("rewinds", "blow-up rewinds"), ("vclamped", "velocity clamps"),
                        ("dclamped", "displacement clamps")):
        v = col(name, int, 0)
        if v and max(v):
            print(f"{label}: peak {max(v)}")
    ms = col("maxstretch")
    mc = col("maxcoord")
    if ms:
        print(f"worst edge stretch {max(ms):.2f}   max |coord| {max(mc):.2f}")


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            rows.append(d)
    if not rows:
        print(f"{path}: no frames")
        return
    print(f"\n=== {os.path.basename(path)} - {len(rows)} frames, "
          f"t {rows[0].get('t')} .. {rows[-1].get('t')} s ===")
    why = Counter(d.get("tear", {}).get("why", "?") for d in rows)
    print("why (per published frame):")
    for k, v in why.most_common():
        print(f"  {v:6d}  {v / len(rows) * 100:5.1f}%  {_bar(v / len(rows))}  {k}")
    print(f"\n{'t':>7}{'crack':>7}{'c':>9}{'tip r':>7}{'peak s1':>9}")
    for d in rows[::max(1, len(rows) // 12)]:
        te = d.get("tear", {})
        print(f"{d.get('t', 0):7.2f}{te.get('len', 0):7d}{te.get('c', 0):9.2f}"
              f"{te.get('tipr', 0):7.2f}{d.get('sp98', 0):9.1f}")
    last = rows[-1].get("crack") or []
    print(f"\nfinal crack path: {len(last)} vertices "
          f"({'chain of mesh edges' if len(last) > 1 else 'not started'})")


def main():
    args = sys.argv[1:]
    if not args:
        args = [p for p in [os.path.join(HERE, "diag_last.csv")] if os.path.exists(p)]
        logs = sorted(glob.glob(os.path.join(HERE, "stress_log_*.jsonl")),
                      key=os.path.getmtime)
        if logs:
            args.append(logs[-1])
    if not args:
        print("no recordings found. Run the scene once; diag_last.csv is always written, "
              "and stress_log_<take>.jsonl needs CAP_STRESS_LOG=1 (run_cap.ps1 -Heatmap).")
        return
    for path in args:
        if not os.path.exists(path):
            print(f"{path}: not found")
        elif path.endswith(".csv"):
            read_csv(path)
        else:
            read_jsonl(path)


if __name__ == "__main__":
    main()
