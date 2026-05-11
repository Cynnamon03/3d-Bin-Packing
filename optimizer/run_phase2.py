# run_phase2.py  -  Phase 2 entry point
#
# Usage:
#   Single instance:
#     python run_phase2.py ..\data\CLP-Datasets-Main\BR\BR0\1.json
#
#   First 10 instances in BR0:
#     python run_phase2.py --set BR0 --count 10 --max-time 30
#
#   Save results:
#     python run_phase2.py --set BR0 --count 10 --out phase2_results.json
#
#   Compare Phase 1 vs Phase 2:
#     python run_phase2.py ..\data\CLP-Datasets-Main\BR\BR0\1.json --compare

import sys
import os
import json
import math
import argparse
import time

from instance_reader import load_instance
from geometry_3d     import assign_weights, compute_weight_capacity
from wolf_3d         import hd_gwo_3d

try:
    from baseline_2d import hd_gwo_2d
    HAS_PHASE1 = True
except ImportError:
    HAS_PHASE1 = False


def lower_bound_3d(items, container):
    total = sum(i['L'] * i['H'] * i['D'] for i in items)
    cap   = container['L'] * container['H'] * container['D']
    return math.ceil(total / cap) if cap > 0 else 1


def run_one(instance_path, pop_size, max_iter, max_time, compare=False):
    container, items = load_instance(instance_path)
    n  = len(items)
    lb = lower_bound_3d(items, container)

    assign_weights(items, seed=42)
    wt_cap = compute_weight_capacity(items, container)

    print(f"\nInstance : {instance_path}", file=sys.stderr, flush=True)
    print(f"3D dims  : L={container['L']}  H={container['H']}"
          f"  D={container['D']}",
          file=sys.stderr, flush=True)
    print(f"Items    : {n}   LB={lb}   wt_cap={wt_cap}",
          file=sys.stderr, flush=True)

    t0   = time.time()
    best = hd_gwo_3d(
        items, container,
        pop_size=pop_size,
        max_iter=max_iter,
        max_time=max_time,
    )
    elapsed = time.time() - t0
    gap     = ((best.n_bins - lb) / lb * 100) if lb > 0 else 0.0

    result = {
        "phase":           2,
        "instance":        instance_path,
        "n_items":         n,
        "lower_bound":     lb,
        "bins_used":       best.n_bins,
        "overflow_items":  best.overflow,
        "gap_pct":         round(gap, 2),
        "dissipation":     round(best.dissipation, 6),
        "composite_score": round(best.composite,   6),
        "runtime_s":       round(elapsed, 2),
        "weight_capacity": wt_cap,
        "container_3d":    container,
        "placements": {
            str(idx): {
                "bin_id": best.genes[idx],
                "x": v[0], "y": v[1], "z": v[2],
                "l": v[3], "h": v[4], "d": v[5],
            }
            for idx, v in best.placements.items()
        },
    }

    if compare and HAS_PHASE1:
        print("\n  [comparison] Phase 1 (2D)...", file=sys.stderr, flush=True)
        t1    = time.time()
        best1 = hd_gwo_2d(items, container,
                           pop_size=pop_size, max_iter=max_iter,
                           max_time=max_time)
        result["phase1_bins"]    = best1.n_bins
        result["phase1_runtime"] = round(time.time() - t1, 2)
        result["phase1_diss"]    = round(best1.dissipation, 6)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Phase 2 - HD-GWO 3D Bin Packing with Geometric Feasibility"
    )
    parser.add_argument("instance_path", nargs="?",
                        help="Path to a single BR JSON instance")
    parser.add_argument("--set",      type=str, default=None)
    parser.add_argument("--count",    type=int, default=None)
    parser.add_argument("--data-root", type=str,
                        default=os.path.join("..", "data",
                                             "CLP-Datasets-Main", "BR"))
    parser.add_argument("--pop",      type=int, default=20)
    parser.add_argument("--iter",     type=int, default=50)
    parser.add_argument("--max-time", type=int, default=60)
    parser.add_argument("--out",      type=str, default=None)
    parser.add_argument("--compare",  action="store_true")
    args    = parser.parse_args()
    results = []

    if args.instance_path:
        results.append(run_one(args.instance_path, args.pop,
                               args.iter, args.max_time, args.compare))

    elif args.set:
        set_path = os.path.join(args.data_root, args.set)
        if not os.path.isdir(set_path):
            print(f"ERROR: {set_path} not found", file=sys.stderr)
            sys.exit(1)

        files = sorted(
            [f for f in os.listdir(set_path) if f.endswith(".json")],
            key=lambda f: int(os.path.splitext(f)[0])
        )
        if args.count:
            files = files[:args.count]

        print(f"\nPhase 2 Batch: {args.set}  ({len(files)} instances)\n",
              file=sys.stderr, flush=True)

        for idx, fname in enumerate(files):
            fpath  = os.path.join(set_path, fname)
            result = run_one(fpath, args.pop, args.iter,
                             args.max_time, args.compare)
            results.append(result)
            print(f"  [{idx+1}/{len(files)}]  {fname}  ->"
                  f"  bins={result['bins_used']}"
                  f"  overflow={result['overflow_items']}"
                  f"  LB={result['lower_bound']}"
                  f"  gap={result['gap_pct']}%"
                  f"  time={result['runtime_s']}s",
                  flush=True)

        n_res    = len(results)
        avg_bins = sum(r['bins_used']      for r in results) / n_res
        avg_gap  = sum(r['gap_pct']        for r in results) / n_res
        avg_diss = sum(r['dissipation']    for r in results) / n_res
        avg_time = sum(r['runtime_s']      for r in results) / n_res
        avg_ov   = sum(r['overflow_items'] for r in results) / n_res
        optimal  = sum(1 for r in results
                       if r['bins_used'] == r['lower_bound']
                       and r['overflow_items'] == 0)

        print(f"\n-- Phase 2 Summary: {args.set} --")
        print(f"   Avg bins         : {avg_bins:.2f}")
        print(f"   Avg gap          : {avg_gap:.2f}%")
        print(f"   Avg dissipation  : {avg_diss:.4f}")
        print(f"   Avg overflow/inst: {avg_ov:.2f}")
        print(f"   Avg time/inst    : {avg_time:.1f}s")
        print(f"   Optimal (no ov)  : {optimal}/{n_res}")

    else:
        parser.print_help()
        sys.exit(0)

    output = {
        "phase":    2,
        "pop_size": args.pop,
        "max_iter": args.iter,
        "max_time": args.max_time,
        "results":  results,
    }

    if args.out:
        with open(args.out, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved -> {args.out}")
    elif len(results) == 1:
        r = results[0]
        print(f"\n{'-'*50}")
        print(f"  Phase 2 - 3D Geometric Feasibility")
        print(f"{'-'*50}")
        print(f"  Bins used       : {r['bins_used']}")
        print(f"  Lower bound     : {r['lower_bound']}")
        print(f"  Gap             : {r['gap_pct']}%")
        print(f"  Overflow items  : {r['overflow_items']}")
        print(f"  Dissipation     : {r['dissipation']}")
        print(f"  Weight capacity : {r['weight_capacity']}")
        print(f"  Runtime         : {r['runtime_s']}s")
        if args.compare and "phase1_bins" in r:
            print(f"  Phase 1 (2D)    : {r['phase1_bins']} bins"
                  f"  in {r['phase1_runtime']}s")
        print(f"{'-'*50}")


if __name__ == "__main__":
    main()