"""
hd_gwo.py  –  HD-GWO with optional real-time streaming.

New in this version
-------------------
* `stream_cb` parameter: a callable(event_type: str, data: dict) invoked
  after every GWO iteration and whenever integration reduces the bin count.
  Pass None (default) for the original silent behaviour.
* `_sa()` now returns (best_wolf, last_udhc_name, udhc_accepted, final_T).
* `_integrate()` now returns (wolf, bins_reduced_by).
* `_make_solution()` serialises the best wolf's packing to a compact list
  suitable for JSON transmission.
* `_apply_random_udhc()` returns (new_seq, operator_name).
"""

import random
import math
import time
import sys

from wolf import Wolf


class HDGWO:
    def __init__(self, items, container,
                 pop_size=20, max_iter=50,
                 T0=500.0, delta_T=25.0, freeze=10.0,
                 max_process=10, max_time=90,
                 stream_cb=None):
        self.items       = items
        self.container   = container
        self.pop_size    = pop_size
        self.max_iter    = max_iter
        self.T0          = T0
        self.delta_T     = delta_T
        self.freeze      = freeze
        self.max_process = max_process
        self.max_time    = max_time
        self.stream_cb   = stream_cb   # callable | None

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _init_population(self):
        return [Wolf(self.items, self.container) for _ in range(self.pop_size)]

    @staticmethod
    def _sort(pop):
        pop.sort(key=lambda w: (w.n_bins, w.dissipation))
        return pop

    def _make_solution(self, wolf):
        """Compact serialisable packing list for the current best wolf."""
        result = []
        for item_idx, placement in wolf.placements.items():
            bin_id, x, y, z, l, h, d = placement
            result.append({
                "item_idx": item_idx,
                "bin_id":   bin_id,
                "x": x, "y": y, "z": z,
                "l": l, "h": h, "d": d,
            })
        result.sort(key=lambda p: (p["bin_id"], p["z"], p["y"], p["x"]))
        return result

    # ── Algorithm 2 – Encircling ───────────────────────────────────────────────
    def _encircle(self, wolf, alpha, beta, delta):
        n       = wolf.n
        new_seq = [None] * n
        used    = [False] * n
        CUM     = (0.50, 0.80, 1.00)
        leaders = (alpha.sequence, beta.sequence, delta.sequence)

        for i in range(n):
            r    = random.random()
            pref = leaders[0 if r < CUM[0] else 1 if r < CUM[1] else 2][i]
            if not used[pref]:
                new_seq[i] = pref
                used[pref] = True
            else:
                for gene in alpha.sequence:
                    if not used[gene]:
                        new_seq[i] = gene
                        used[gene] = True
                        break

        wolf.set_sequence(new_seq)

    # ── UDHC operators ─────────────────────────────────────────────────────────
    @staticmethod
    def _udhc1(seq):
        s = seq[:]
        for i in range(0, len(s) - 1, 2):
            s[i], s[i + 1] = s[i + 1], s[i]
        return s

    @staticmethod
    def _udhc2(seq):
        s = seq[:]
        for i in range(1, len(s) - 1, 2):
            s[i], s[i + 1] = s[i + 1], s[i]
        return s

    @staticmethod
    def _udhc3(seq):
        n = len(seq)
        if n < 2: return seq[:]
        cut = random.randint(1, n - 1)
        return seq[cut:] + seq[:cut]

    @staticmethod
    def _udhc4(seq):
        n = len(seq)
        if n < 2: return seq[:]
        i, j = sorted(random.sample(range(n), 2))
        s = seq[:]
        s[i:j + 1] = s[i:j + 1][::-1]
        return s

    @staticmethod
    def _udhc5(seq):
        n = len(seq)
        if n < 2: return seq[:]
        i, j = random.sample(range(n), 2)
        s = seq[:]
        s[i], s[j] = s[j], s[i]
        return s

    def _apply_random_udhc(self, seq):
        """Apply a randomly chosen UDHC operator. Returns (new_seq, op_name)."""
        op   = random.randint(1, 5)
        name = f"UDHC{op}"
        if op == 1: return self._udhc1(seq), name
        if op == 2: return self._udhc2(seq), name
        if op == 3: return self._udhc3(seq), name
        if op == 4: return self._udhc4(seq), name
        return          self._udhc5(seq), name

    # ── Simulated Annealing ────────────────────────────────────────────────────
    def _sa(self, seed_wolf):
        """
        Returns
        -------
        (best_sa, last_udhc_name, udhc_accepted, final_T)
        """
        current     = seed_wolf.copy()
        best_sa     = current.copy()
        T           = self.T0
        last_udhc   = "UDHC5"
        udhc_accept = False

        while T > self.freeze:
            for _ in range(self.max_process):
                new_seq, udhc_name = self._apply_random_udhc(current.sequence)
                candidate          = current.copy()
                candidate.set_sequence(new_seq)

                accept = False
                if candidate.n_bins < current.n_bins:
                    accept = True
                elif candidate.n_bins == current.n_bins:
                    dd = candidate.dissipation - current.dissipation
                    if dd <= 0 or random.random() < math.exp(-dd / max(T, 1e-10)):
                        accept = True
                else:
                    df = candidate.composite - current.composite
                    if random.random() < math.exp(-df / max(T, 1e-10)):
                        accept = True

                if accept:
                    current     = candidate
                    last_udhc   = udhc_name
                    udhc_accept = True

                if current.composite < best_sa.composite:
                    best_sa = current.copy()

            T -= self.delta_T

        return best_sa, last_udhc, udhc_accept, max(T, 0.0)

    # ── Algorithm 3 – Integration ──────────────────────────────────────────────
    def _integrate(self, wolf):
        """
        Returns
        -------
        (wolf_after, bins_reduced_by: int)
        """
        if wolf.n_bins <= 1:
            return wolf, 0

        cap   = self.container['L'] * self.container['H'] * self.container['D']
        utils = []
        for bp in wolf.bins_placed:
            used = sum(l * h * d for (_, _, _, l, h, d) in bp)
            utils.append(used / cap if cap > 0 else 0.0)

        src     = min(range(len(utils)), key=lambda i: utils[i])
        src_set = set(wolf.bin_items[src])
        front   = [i for i in wolf.sequence if i not in src_set]
        back    = [i for i in wolf.sequence if i     in src_set]
        trial   = wolf.copy()
        trial.set_sequence(front + back)

        if trial.n_bins <= wolf.n_bins:
            return trial, wolf.n_bins - trial.n_bins
        return wolf, 0

    # ── Algorithm 1 – Main loop ────────────────────────────────────────────────
    def run(self):
        start = time.time()
        pop   = self._sort(self._init_population())

        alpha = pop[0].copy()
        beta  = pop[min(1, len(pop) - 1)].copy()
        delta = pop[min(2, len(pop) - 1)].copy()
        best  = alpha.copy()

        print(f"  Initial best: bins={best.n_bins}, "
              f"dissipation={best.dissipation:.4f}",
              file=sys.stderr, flush=True)

        no_improve = 0

        for iteration in range(self.max_iter):
            if time.time() - start > self.max_time:
                print(f"  [iter {iteration+1}] Time limit reached.",
                      file=sys.stderr, flush=True)
                break

            for i in range(3, len(pop)):
                self._encircle(pop[i], alpha, beta, delta)

            sa_best, last_udhc, udhc_accepted, final_T = self._sa(best)
            sa_best, bins_reduced                       = self._integrate(sa_best)

            if bins_reduced > 0:
                print(f"  [iter {iteration+1}] Integration: -{bins_reduced} bin(s)",
                      file=sys.stderr, flush=True)
                if self.stream_cb:
                    self.stream_cb("integration_applied", {
                        "bins_reduced_by": bins_reduced,
                        "new_bins":        sa_best.n_bins,
                    })

            pop = self._sort(pop)
            if sa_best.composite < pop[-1].composite:
                pop[-1] = sa_best
            pop = self._sort(pop)

            alpha = pop[0].copy()
            beta  = pop[min(1, len(pop) - 1)].copy()
            delta = pop[min(2, len(pop) - 1)].copy()

            if alpha.composite < best.composite:
                best       = alpha.copy()
                no_improve = 0
                print(f"  [iter {iteration+1}] ★ bins={best.n_bins} "
                      f"score={best.composite:.4f}",
                      file=sys.stderr, flush=True)
            else:
                no_improve += 1

            # ── Emit streaming update every iteration ─────────────────────────
            if self.stream_cb:
                self.stream_cb("iteration_update", {
                    "iteration":        iteration + 1,
                    "max_iter":         self.max_iter,
                    "best_bins":        best.n_bins,
                    "best_dissipation": round(best.dissipation, 4),
                    "temperature":      round(final_T, 1),
                    "last_udhc":        last_udhc,
                    "udhc_accepted":    udhc_accepted,
                    "solution":         self._make_solution(best),
                })

            if no_improve >= 20:
                print(f"  [iter {iteration+1}] Early stop.",
                      file=sys.stderr, flush=True)
                break

        elapsed = time.time() - start
        print(f"  Done in {elapsed:.1f}s — bins={best.n_bins}",
              file=sys.stderr, flush=True)
        return best