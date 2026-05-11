"""
run_baseline.py  –  Phase 1 entry point
========================================
Run the 2-D HD-GWO baseline on one instance or a whole BR set.

Usage examples
--------------
# Single instance
python run_baseline.py ..\data\CLP-Datasets-Main\BR\BR0\1.json

# First 10 instances in BR0 (batch validation)
python run_baseline.py --set BR0 --count 10

# Full set with custom parameters
python run_baseline.py --set BR1 --pop 20 --iter 50 --max-time 30
"""

import sys
import os
import json
import math
import argparse
import time

from instance_reader import load_instance
from baseline_2d     import hd_gwo_2d


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def lower_bound_2d(items, container):
    total = sum(i['L'] * i['H'] for i in items)
    cap   = container['L'] * container['H']
    return math.ceil(total / cap) if cap > 0 else 1


def run_one(instance_path, pop_size, max_iter, max_time):
    """Run the baseline on a single JSON instance. Returns result dict."""
    container, items = load_instance(instance_path)
    n  = len(items)
    lb = lower_bound_2d(items, container)

    print(f"\nInstance  : {instance_path}", file=sys.stderr, flush=True)
    print(f"2D dims   : L={container['L']}  H={container['H']}", file=sys.stderr, flush=True)
    print(f"Items     : {n}   lower bound: {lb} bin(s)", file=sys.stderr, flush=True)

    t0   = time.time()
    best = hd_gwo_2d(
        items, container,
        pop_size=pop_size,
        max_iter=max_iter,
        max_time=max_time,
    )
    elapsed = time.time() - t0

    gap = ((best.n_bins - lb) / lb * 100) if lb > 0 else 0.0

    return {
        "instance":        instance_path,
        "n_items":         n,
        "lower_bound":     lb,
        "bins_used":       best.n_bins,
        "gap_pct":         round(gap, 2),         # % above lower bound
        "dissipation":     round(best.dissipation, 6),
        "composite_score": round(best.composite,   6),
        "runtime_s":       round(elapsed, 2),
        "container_2d": {
            "L": container['L'],
            "H": container['H'],
        },
        # Bin assignment: bin_id -> [item indices]
        "bin_assignment": {
            str(b): sorted(lst)
            for b, lst in best.bin_assignment.items()
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1 – HD-GWO 2-D Bin Packing Baseline"
    )

    # Mode A: single instance
    parser.add_argument("instance_path", nargs="?",
                        help="Path to a single BR JSON instance")

    # Mode B: batch over a BR set
    parser.add_argument("--set",    type=str, default=None,
                        help="BR set name, e.g. BR0  (runs all JSONs in that folder)")
    parser.add_argument("--count",  type=int, default=None,
                        help="Limit to first N instances of the set (default: all)")
    parser.add_argument("--data-root", type=str,
                        default=os.path.join("..", "data", "CLP-Datasets-Main", "BR"),
                        help="Path to the BR root folder")

    # Algorithm parameters
    parser.add_argument("--pop",      type=int,   default=20,
                        help="Population size (default 20)")
    parser.add_argument("--iter",     type=int,   default=50,
                        help="Max GWO iterations (default 50)")
    parser.add_argument("--max-time", type=int,   default=60,
                        help="Wall-clock time limit per instance in seconds (default 60)")

    # Output
    parser.add_argument("--out", type=str, default=None,
                        help="Save results JSON to this file")

    args = parser.parse_args()

    results = []

    # ── Mode A: single instance ───────────────────────────────────────────────
    if args.instance_path:
        result = run_one(args.instance_path, args.pop, args.iter, args.max_time)
        results.append(result)

    # ── Mode B: batch over a set ──────────────────────────────────────────────
    elif args.set:
        set_path = os.path.join(args.data_root, args.set)
        if not os.path.isdir(set_path):
            print(f"ERROR: Set folder not found: {set_path}", file=sys.stderr)
            sys.exit(1)

        files = sorted(
            [f for f in os.listdir(set_path) if f.endswith(".json")],
            key=lambda f: int(os.path.splitext(f)[0])
        )

        if args.count:
            files = files[:args.count]

        print(f"\nBatch: {args.set}  ({len(files)} instances)\n",
              file=sys.stderr, flush=True)

        for idx, fname in enumerate(files):
            fpath  = os.path.join(set_path, fname)
            result = run_one(fpath, args.pop, args.iter, args.max_time)
            results.append(result)

            print(f"  [{idx+1}/{len(files)}]  {fname}  →  "
                  f"bins={result['bins_used']}  LB={result['lower_bound']}  "
                  f"gap={result['gap_pct']}%  "
                  f"time={result['runtime_s']}s",
                  flush=True)

        # Summary statistics
        avg_bins  = sum(r['bins_used']    for r in results) / len(results)
        avg_gap   = sum(r['gap_pct']      for r in results) / len(results)
        avg_diss  = sum(r['dissipation']  for r in results) / len(results)
        avg_time  = sum(r['runtime_s']    for r in results) / len(results)
        optimal   = sum(1 for r in results if r['bins_used'] == r['lower_bound'])

        print(f"\n── Summary: {args.set} ({'first ' + str(args.count) if args.count else 'all'} instances) ──")
        print(f"   Avg bins      : {avg_bins:.2f}")
        print(f"   Avg gap       : {avg_gap:.2f}%  above lower bound")
        print(f"   Avg diss      : {avg_diss:.4f}")
        print(f"   Avg time/inst : {avg_time:.1f}s")
        print(f"   Optimal (LB)  : {optimal}/{len(results)}")

    else:
        parser.print_help()
        sys.exit(0)

    # ── Output ────────────────────────────────────────────────────────────────
    output = {
        "phase":    1,
        "pop_size": args.pop,
        "max_iter": args.iter,
        "max_time": args.max_time,
        "results":  results,
    }

    if args.out:
        with open(args.out, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to {args.out}")
    else:
        # Single instance: pretty-print result
        if len(results) == 1:
            r = results[0]
            print(f"\n{'─'*50}")
            print(f"  Bins used   : {r['bins_used']}")
            print(f"  Lower bound : {r['lower_bound']}")
            print(f"  Gap         : {r['gap_pct']}%")
            print(f"  Dissipation : {r['dissipation']}")
            print(f"  Runtime     : {r['runtime_s']}s")
            print(f"{'─'*50}")
            print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()