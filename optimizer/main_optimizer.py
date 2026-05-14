"""
main_optimizer.py
Command-line entry point.

Normal mode (no --stream):
    python main_optimizer.py <path.json>
    → prints one JSON result blob to stdout when done.

Streaming mode (--stream):
    python main_optimizer.py <path.json> --stream
    → prints one JSON line per event to stdout throughout the run.
      Node.js reads these line-by-line and forwards them via WebSocket.

All progress/debug text goes to stderr (never pollutes stdout JSON).
"""

import sys
import json
import math
import time
import argparse

from instance_reader import load_instance
from hd_gwo import HDGWO


def lower_bound(items, container):
    cap   = container['L'] * container['H'] * container['D']
    total = sum(i['L'] * i['H'] * i['D'] for i in items)
    return math.ceil(total / cap) if cap > 0 else 1


def main():
    # ── Arguments ─────────────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(description="3-D Bin Packing — HD-GWO Optimizer")
    parser.add_argument("instance_path",  help="Path to BR dataset JSON file")
    parser.add_argument("--stream", action="store_true",
                        help="Emit JSON progress lines to stdout (for batch/WebSocket mode)")
    parser.add_argument("--max-time", type=int, default=90,
                    help="Wall-clock time limit in seconds (default 90)")
    args = parser.parse_args()

    streaming = args.stream

    # ── Load instance ──────────────────────────────────────────────────────────
    try:
        container, items = load_instance(args.instance_path)
    except Exception as e:
        print(json.dumps({"type": "error", "error": f"Failed to load: {e}"}), flush=True)
        sys.exit(1)

    n  = len(items)
    lb = lower_bound(items, container)

    print(f"Instance  : {args.instance_path}", file=sys.stderr, flush=True)
    print(f"Container : L={container['L']} H={container['H']} D={container['D']}",
          file=sys.stderr, flush=True)
    print(f"Items     : {n}  (lower bound: {lb} bin(s))",
          file=sys.stderr, flush=True)

    # ── Scale parameters to instance size ─────────────────────────────────────
    pop_size    = min(20, max(5,  n // 8))
    max_iter    = min(50, max(20, n // 4))
    max_process = min(15, max(5,  n // 10))

    print(f"Params    : pop={pop_size} iter={max_iter} proc={max_process}",
          file=sys.stderr, flush=True)

    # ── Streaming callback ─────────────────────────────────────────────────────
    def emit(event_type, data):
        """Print one JSON line to stdout and flush immediately."""
        msg = {"type": event_type, **data}
        print(json.dumps(msg), flush=True)

    # If streaming, emit instance metadata first so React knows the container dims
    if streaming:
        emit("instance_info", {
            "container":   container,
            "n_items":     n,
            "lower_bound": lb,
        })

    # ── Run optimizer ──────────────────────────────────────────────────────────
    _start_time = time.time()
    optimizer = HDGWO(
        items=items,
        container=container,
        pop_size=pop_size,
        max_iter=max_iter,
        T0=500.0,
        delta_T=25.0,
        freeze=10.0,
        max_process=max_process,
        max_time=args.max_time,
        stream_cb=emit if streaming else None,
    )

    best = optimizer.run()

    # ── Build final result ─────────────────────────────────────────────────────
    packed_items = []
    for item_idx, placement in best.placements.items():
        bin_id, x, y, z, l, h, d = placement
        packed_items.append({
            "item_idx": item_idx,
            "bin_id":   bin_id,
            "x": x, "y": y, "z": z,
            "l": l, "h": h, "d": d,
            "orig_L": items[item_idx]['L'],
            "orig_H": items[item_idx]['H'],
            "orig_D": items[item_idx]['D'],
        })
    packed_items.sort(key=lambda p: (p["bin_id"], p["z"], p["y"], p["x"]))

    cap_vol      = container['L'] * container['H'] * container['D']
    items_vol    = sum(p['l'] * p['h'] * p['d'] for p in packed_items)
    vol_util_pct = round(items_vol / (best.n_bins * cap_vol) * 100, 2) if cap_vol > 0 else 0.0

    result = {
        "status":          "ok",
        "instance":        args.instance_path,
        "bins_used":       best.n_bins,
        "lower_bound":     lb,
        "gap_pct":         round((best.n_bins - lb) / max(lb, 1) * 100, 2),
        "dissipation":     round(best.dissipation, 6),
        "composite_score": round(best.composite,   6),
        "volume_util_pct": vol_util_pct,
        "runtime_s":       round(time.time() - _start_time, 2),
        "container":       container,
        "n_items":         n,
        "items":           packed_items,
    }

    if streaming:
        # Emit as a typed message so Node.js/React can handle it
        emit("instance_complete", result)
    else:
        # Normal mode: single JSON blob to stdout
        print(json.dumps(result))


if __name__ == "__main__":
    main()