"""
run_baseline.py  –  Phase 1 entry point
========================================
Run the 2-D HD-GWO baseline on preprocessed training instances.
"""

import sys
import json
import math
import argparse
import time
from pathlib import Path

from processed_instance_reader import load_train_dataset
from baseline_2d import hd_gwo_2d


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def lower_bound_2d(items, container):
    total = sum(i['L'] * i['H'] for i in items)
    cap = container['L'] * container['H']
    return math.ceil(total / cap) if cap > 0 else 1


def validate_data_path(data_path: Path) -> Path:
    resolved = data_path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Training JSON not found: {resolved}")

    if 'held_out' in resolved.parts:
        raise PermissionError(
            f"Unauthorized Access: baseline may not load data from held-out directory ({resolved})"
        )

    held_out_root = resolved.parents[2] / 'held_out' if len(resolved.parents) >= 3 else None
    if held_out_root and held_out_root in resolved.parents:
        raise PermissionError(
            f"Unauthorized Access: baseline may not load data from held-out directory ({resolved})"
        )

    return resolved


def run_one(instance: dict, pop_size: int, max_iter: int, max_time: int):
    """Run the baseline on a single preprocessed instance."""
    container = instance['container']
    items = instance['items']
    n = len(items)
    lb = lower_bound_2d(items, container)

    print(f"\nInstance  : {instance.get('id', '<unknown>')}", file=sys.stderr, flush=True)
    print(f"2D dims   : L={container['L']}  H={container['H']}", file=sys.stderr, flush=True)
    print(f"Items     : {n}   lower bound: {lb} bin(s)", file=sys.stderr, flush=True)

    t0 = time.time()
    best = hd_gwo_2d(
        items, container,
        pop_size=pop_size,
        max_iter=max_iter,
        max_time=max_time,
    )
    elapsed = time.time() - t0

    gap = ((best.n_bins - lb) / lb * 100) if lb > 0 else 0.0

    return {
        "instance": instance.get('id', '<unknown>'),
        "n_items": n,
        "lower_bound": lb,
        "bins_used": best.n_bins,
        "gap_pct": round(gap, 2),
        "dissipation": round(best.dissipation, 6),
        "composite_score": round(best.composite, 6),
        "runtime_s": round(elapsed, 2),
        "container_2d": {
            "L": container['L'],
            "H": container['H'],
        },
        "bin_assignment": {
            str(b): sorted(lst)
            for b, lst in best.bin_assignment.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Phase 1 – HD-GWO 2-D Bin Packing Baseline"
    )

    parser.add_argument(
        "--data_path",
        type=str,
        default=str(Path("data") / "train" / "instances.json"),
        help="Path to the preprocessed training JSON file",
    )
    parser.add_argument(
        "--instance_index",
        type=int,
        default=None,
        help="Optional zero-based index of a single instance to run",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Limit to first N instances of the training dataset",
    )
    parser.add_argument("--pop", type=int, default=20,
                        help="Population size (default 20)")
    parser.add_argument("--iter", type=int, default=50,
                        help="Max GWO iterations (default 50)")
    parser.add_argument("--max-time", type=int, default=60,
                        help="Wall-clock time limit per instance in seconds (default 60)")
    parser.add_argument("--out", type=str, default=None,
                        help="Save results JSON to this file")

    args = parser.parse_args()

    data_path = validate_data_path(Path(args.data_path))
    instances = load_train_dataset(str(data_path))

    if args.instance_index is not None:
        if args.instance_index < 0 or args.instance_index >= len(instances):
            raise IndexError(
                f"Instance index {args.instance_index} out of range (0..{len(instances)-1})"
            )
        instances = [instances[args.instance_index]]

    if args.count is not None:
        instances = instances[:args.count]

    print(f"Running baseline on {len(instances)} preprocessed training instances...", file=sys.stderr)

    results = []
    for instance in instances:
        result = run_one(instance, args.pop, args.iter, args.max_time)
        results.append(result)

    output = {
        "phase": 1,
        "pop_size": args.pop,
        "max_iter": args.iter,
        "max_time": args.max_time,
        "data_path": str(data_path),
        "instances": len(instances),
        "results": results,
    }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to {args.out}")
    else:
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
