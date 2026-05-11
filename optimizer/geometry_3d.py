"""
geometry_3d.py  -  Phase 2: 3-D Spatial Feasibility Engine
Pure geometry functions used by Wolf3D.
"""

import math
import random

# ── Orientation table ─────────────────────────────────────────────────────────
ORIENT_FNS = [
    lambda L, H, D: (L, H, D),
    lambda L, H, D: (L, D, H),
    lambda L, H, D: (H, L, D),
    lambda L, H, D: (H, D, L),
    lambda L, H, D: (D, L, H),
    lambda L, H, D: (D, H, L),
]
N_ORIENTATIONS = 6

def get_dims(item, orient_id):
    return ORIENT_FNS[orient_id](item['L'], item['H'], item['D'])

# ── AABB overlap ──────────────────────────────────────────────────────────────
def overlaps(ax, ay, az, al, ah, ad, bx, by, bz, bl, bh, bd):
    return (ax < bx+bl and ax+al > bx and
            ay < by+bh and ay+ah > by and
            az < bz+bd and az+ad > bz)

def can_place(x, y, z, l, h, d, CL, CH, CD, placed):
    if x+l > CL or y+h > CH or z+d > CD:
        return False
    for (px, py, pz, pl2, ph, pd) in placed:
        if overlaps(x, y, z, l, h, d, px, py, pz, pl2, ph, pd):
            return False
    return True

# ── Extreme Points ────────────────────────────────────────────────────────────
MAX_EPS = 200   # raised from 50 to prevent valid positions being dropped

def _update_eps(eps, placed, nx, ny, nz, nl, nh, nd, CL, CH, CD):
    candidates = list(eps) + [
        (nx+nl, ny,    nz),
        (nx,    ny+nh, nz),
        (nx,    ny,    nz+nd),
    ]
    result = []
    seen   = set()
    for (ex, ey, ez) in candidates:
        if (ex, ey, ez) in seen:
            continue
        seen.add((ex, ey, ez))
        if ex >= CL or ey >= CH or ez >= CD:
            continue
        blocked = any(
            px <= ex < px+pl2 and py <= ey < py+ph and pz <= ez < pz+pd
            for (px, py, pz, pl2, ph, pd) in placed
        )
        if not blocked:
            result.append((ex, ey, ez))
    result.sort(key=lambda ep: (ep[2], ep[1], ep[0]))
    return result[:MAX_EPS]

# ── DBLF placement for one bin ────────────────────────────────────────────────
def place_bin_dblf(item_indices, items, orient_ids, container, weight_capacity=None):
    CL, CH, CD = container['L'], container['H'], container['D']
    placed     = []
    eps        = [(0, 0, 0)]
    placements = {}
    overflow   = []
    total_wt   = 0.0

    sorted_items = sorted(
        item_indices,
        key=lambda i: items[i]['L'] * items[i]['H'] * items[i]['D'],
        reverse=True
    )

    for item_idx in sorted_items:
        item      = items[item_idx]
        orient_id = orient_ids.get(item_idx, 0)
        l, h, d   = get_dims(item, orient_id)
        wt        = item.get('weight', 1)

        if weight_capacity is not None and total_wt + wt > weight_capacity:
            overflow.append(item_idx)
            continue

        placed_flag = False
        for (ex, ey, ez) in eps:
            if can_place(ex, ey, ez, l, h, d, CL, CH, CD, placed):
                placed.append((ex, ey, ez, l, h, d))
                placements[item_idx] = (ex, ey, ez, l, h, d)
                eps = _update_eps(eps, placed, ex, ey, ez, l, h, d, CL, CH, CD)
                total_wt   += wt
                placed_flag = True
                break

        if not placed_flag:
            for alt_o in range(N_ORIENTATIONS):
                if alt_o == orient_id:
                    continue
                al, ah, ad = get_dims(item, alt_o)
                for (ex, ey, ez) in eps:
                    if can_place(ex, ey, ez, al, ah, ad, CL, CH, CD, placed):
                        placed.append((ex, ey, ez, al, ah, ad))
                        placements[item_idx] = (ex, ey, ez, al, ah, ad)
                        eps = _update_eps(eps, placed, ex, ey, ez, al, ah, ad, CL, CH, CD)
                        total_wt   += wt
                        placed_flag = True
                        break
                if placed_flag:
                    break

        if not placed_flag:
            overflow.append(item_idx)

    return placements, overflow

# ── Weight helpers ────────────────────────────────────────────────────────────
def assign_weights(items, seed=42):
    rng = random.Random(seed)
    for item in items:
        item['weight'] = rng.randint(1, 20)

def compute_weight_capacity(items, container):
    total_wt  = sum(item.get('weight', 1) for item in items)
    vol_cap   = container['L'] * container['H'] * container['D']
    vol_items = sum(i['L'] * i['H'] * i['D'] for i in items)
    lb        = max(1, math.ceil(vol_items / vol_cap))
    return math.ceil(total_wt / lb)

def volumetric_dissipation(bin_placements, container):
    cap  = container['L'] * container['H'] * container['D']
    diss = 0.0
    for bp in bin_placements:
        used = sum(l*h*d for (_, _, _, l, h, d) in bp)
        util = used / cap if cap > 0 else 0.0
        diss += (1.0 - util) ** 2
    return diss