#!/usr/bin/env python3
"""
run_preprocessed.py
Entry point for running the optimizer on preprocessed training instances.

Usage:
    python run_preprocessed.py <index> --stream --max-time 90
    
Loads the instance at <index> from data/train/instances.json and runs
the 3D HD-GWO optimizer with streaming output.
"""

import sys
import json
import math
import time
import argparse
from pathlib import Path

from hd_gwo import HDGWO


def main():
    parser = argparse.ArgumentParser(description="3-D Bin Packing on Preprocessed Data")
    parser.add_argument("instance_index", type=int, help="Zero-based index in training dataset")
    parser.add_argument("--stream", action="store_true",
                        help="Emit JSON progress lines to stdout")
    parser.add_argument("--max-time", type=int, default=90,
                        help="Wall-clock time limit in seconds (default 90)")
    args = parser.parse_args()

    # Load preprocessed training dataset
    train_json_path = Path(__file__).resolve().parents[1] / "data" / "train" / "instances.json"
    if not train_json_path.exists():
        print(json.dumps({"type": "error", "error": f"Training dataset not found: {train_json_path}"}), flush=True)
        sys.exit(1)

    try:
        with open(train_json_path, 'r', encoding='utf-8') as f:
            train_data = json.load(f)
    except Exception as e:
        print(json.dumps({"type": "error", "error": f"Failed to load training dataset: {e}"}), flush=True)
        sys.exit(1)

    instances = train_data.get('instances', [])
    if args.instance_index < 0 or args.instance_index >= len(instances):
        print(json.dumps({"type": "error", "error": f"Instance index {args.instance_index} out of range"}), flush=True)
        sys.exit(1)

    instance = instances[args.instance_index]
    container = instance.get('container', {})
    items_raw = instance.get('items', [])

    # Convert preprocessed format to optimizer format
    container_opt = {
        'L': float(container.get('L', 0)),
        'H': float(container.get('H', 0)),
        'D': float(container.get('W', 0)),  # W -> D for 3D
    }

    items_opt = []
    for item in items_raw:
        items_opt.append({
            'L': float(item.get('L', 0)),
            'H': float(item.get('H', 0)),
            'D': float(item.get('W', 0)),  # W -> D for 3D
            'can_rotate': True,
            'stop': 1,
        })

    n = len(items_opt)
    cap = container_opt['L'] * container_opt['H'] * container_opt['D']
    total = sum(i['L'] * i['H'] * i['D'] for i in items_opt)
    lb = math.ceil(total / cap) if cap > 0 else 1

    print(f"Instance  : {instance.get('id', '<unknown>')}", file=sys.stderr, flush=True)
    print(f"Container : L={container_opt['L']} H={container_opt['H']} D={container_opt['D']}",
          file=sys.stderr, flush=True)
    print(f"Items     : {n}  (lower bound: {lb} bin(s))", file=sys.stderr, flush=True)

    pop_size = min(20, max(5, n // 8))
    max_iter = min(50, max(20, n // 4))
    max_process = min(15, max(5, n // 10))

    print(f"Params    : pop={pop_size} iter={max_iter} proc={max_process}",
          file=sys.stderr, flush=True)

    def emit(event_type, data):
        msg = {"type": event_type, **data}
        print(json.dumps(msg), flush=True)

    if args.stream:
        emit("instance_info", {
            "container": container_opt,
            "n_items": n,
            "lower_bound": lb,
        })

    t0 = time.time()
    optimizer = HDGWO(
        items=items_opt,
        container=container_opt,
        pop_size=pop_size,
        max_iter=max_iter,
        T0=500.0,
        delta_T=25.0,
        freeze=10.0,
        max_process=max_process,
        max_time=args.max_time,
        stream_cb=emit if args.stream else None,
    )

    best = optimizer.run()
    elapsed = time.time() - t0

    gap = ((best.n_bins - lb) / lb * 100) if lb > 0 else 0.0

    result = {
        "bins_used": best.n_bins,
        "lower_bound": lb,
        "gap_pct": round(gap, 2),
        "dissipation": round(best.dissipation, 6),
        "composite_score": round(best.composite, 6),
        "volume_util_pct": round((total / (best.n_bins * cap)) * 100, 2) if cap > 0 else 0.0,
        "runtime_s": round(elapsed, 2),
        "container": container_opt,
        "n_items": n,
        "items": best.bin_assignment,
    }

    if args.stream:
        emit("instance_complete", result)
    else:
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
