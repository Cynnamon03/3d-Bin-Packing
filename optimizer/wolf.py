"""
wolf.py
Wolf class and all 3-D bin-packing geometry helpers.

Encoding
--------
Each Wolf's "genotype" is a permutation (sequence) of item indices.
The "phenotype" (actual packing) is decoded by placing items in that
order using Deep-Bottom-Left-Fill (DBLF) with Extreme Points.

Extreme Points (EP) approach
-----------------------------
After placing each item, three new candidate positions are generated
(one on each axis face of the newly placed box).  Invalid positions
(outside the container or inside an already-placed box) are pruned.
EPs are sorted in DBLF order: deepest Z first, then lowest Y, then
leftmost X.  The first orientation that fits at the first valid EP wins.
"""

import random
import math

# Cap how many EPs we track per bin to keep decode times bounded.
MAX_EPS_PER_BIN = 60


# ─────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_orientations(item):
    """Return all distinct (l, h, d) orientations allowed for an item."""
    L, H, D = item['L'], item['H'], item['D']
    if item['can_rotate']:
        seen, result = set(), []
        for perm in [(L,H,D), (L,D,H), (H,L,D), (H,D,L), (D,L,H), (D,H,L)]:
            if perm not in seen:
                seen.add(perm)
                result.append(perm)
        return result
    return [(L, H, D)]


def _overlaps(ax, ay, az, al, ah, ad, bx, by, bz, bl, bh, bd):
    """True if box A overlaps box B (both half-open intervals)."""
    return (ax < bx + bl and ax + al > bx and
            ay < by + bh and ay + ah > by and
            az < bz + bd and az + ad > bz)


def _fits(ex, ey, ez, l, h, d, CL, CH, CD, placed_in_bin):
    """True if item (l,h,d) can be placed at (ex,ey,ez) without conflict."""
    if ex + l > CL or ey + h > CH or ez + d > CD:
        return False
    for (px, py, pz, pl, ph, pd) in placed_in_bin:
        if _overlaps(ex, ey, ez, l, h, d, px, py, pz, pl, ph, pd):
            return False
    return True


def _update_eps(eps, placed_in_bin, nx, ny, nz, nl, nh, nd, CL, CH, CD):
    """
    Incrementally update extreme points after placing item at (nx,ny,nz)
    with dimensions (nl,nh,nd).

    `placed_in_bin` already contains the newly placed item.
    """
    candidates = list(eps) + [
        (nx + nl, ny,      nz),
        (nx,      ny + nh, nz),
        (nx,      ny,      nz + nd),
    ]

    result = []
    seen = set()
    for (ex, ey, ez) in candidates:
        if (ex, ey, ez) in seen:
            continue
        seen.add((ex, ey, ez))
        # Must be inside container
        if ex >= CL or ey >= CH or ez >= CD:
            continue
        # Must not be inside any already-placed box
        blocked = False
        for (px, py, pz, pl, ph, pd) in placed_in_bin:
            if px <= ex < px + pl and py <= ey < py + ph and pz <= ez < pz + pd:
                blocked = True
                break
        if not blocked:
            result.append((ex, ey, ez))

    # DBLF sort: deepest Z, then lowest Y, then leftmost X
    result.sort(key=lambda ep: (ep[2], ep[1], ep[0]))
    return result[:MAX_EPS_PER_BIN]


# ─────────────────────────────────────────────────────────────────────────────
# DBLF decoder
# ─────────────────────────────────────────────────────────────────────────────

def place_items(sequence, items, container):
    """
    Decode an item-index permutation into a bin packing using DBLF.

    Parameters
    ----------
    sequence  : list of int   – permutation of item indices
    items     : list of dict  – all items (from instance_reader)
    container : dict          – {'L', 'H', 'D'}

    Returns
    -------
    bins_placed  : list of list of (x,y,z,l,h,d) tuples, one list per bin
    placements   : dict  item_idx -> (bin_idx, x, y, z, l, h, d)
    bin_items    : list of list of int   – which item indices are in each bin
    """
    CL, CH, CD = container['L'], container['H'], container['D']
    bins_placed = []    # bins_placed[b] = [(x,y,z,l,h,d), ...]
    bins_eps    = []    # bins_eps[b]    = [(ex,ey,ez), ...]  sorted DBLF
    bin_items   = []    # bin_items[b]   = [item_idx, ...]
    placements  = {}    # item_idx -> (bin_idx, x, y, z, l, h, d)

    for item_idx in sequence:
        item   = items[item_idx]
        orients = get_orientations(item)
        placed = False

        # ── Try existing bins ────────────────────────────────────────────────
        for bin_idx in range(len(bins_placed)):
            placed_in_bin = bins_placed[bin_idx]
            for (ex, ey, ez) in bins_eps[bin_idx]:    # already DBLF-sorted
                for (l, h, d) in orients:
                    if _fits(ex, ey, ez, l, h, d, CL, CH, CD, placed_in_bin):
                        placed_in_bin.append((ex, ey, ez, l, h, d))
                        bin_items[bin_idx].append(item_idx)
                        placements[item_idx] = (bin_idx, ex, ey, ez, l, h, d)
                        bins_eps[bin_idx] = _update_eps(
                            bins_eps[bin_idx], placed_in_bin,
                            ex, ey, ez, l, h, d, CL, CH, CD
                        )
                        placed = True
                        break
                if placed:
                    break
            if placed:
                break

        # ── Open a new bin ───────────────────────────────────────────────────
        if not placed:
            for (l, h, d) in orients:
                if l <= CL and h <= CH and d <= CD:
                    new_bin = [(0, 0, 0, l, h, d)]
                    bins_placed.append(new_bin)
                    bin_items.append([item_idx])
                    placements[item_idx] = (len(bins_placed) - 1, 0, 0, 0, l, h, d)
                    # Initial EPs after placing one item at origin
                    init_eps = [(l, 0, 0), (0, h, 0), (0, 0, d)]
                    valid_eps = [(x, y, z) for (x, y, z) in init_eps
                                 if x < CL and y < CH and z < CD]
                    valid_eps.sort(key=lambda ep: (ep[2], ep[1], ep[0]))
                    bins_eps.append(valid_eps)
                    placed = True
                    break

            if not placed:
                # Fallback: item larger than container (shouldn't happen)
                l, h, d = item['L'], item['H'], item['D']
                bins_placed.append([(0, 0, 0, l, h, d)])
                bin_items.append([item_idx])
                placements[item_idx] = (len(bins_placed) - 1, 0, 0, 0, l, h, d)
                bins_eps.append([])

    return bins_placed, placements, bin_items


def compute_fitness(bins_placed, container):
    """
    Compute fitness values for a packing.

    Returns
    -------
    n_bins       : int    – number of bins used (primary objective)
    dissipation  : float  – sum of (1 - util)^2 over all bins (secondary)
    composite    : float  – n_bins + 0.1 * dissipation  (single ranking key)
    """
    n_bins = len(bins_placed)
    if n_bins == 0:
        return 0, 0.0, 0.0

    cap = container['L'] * container['H'] * container['D']
    dissipation = 0.0
    for bp in bins_placed:
        used = sum(l * h * d for (_, _, _, l, h, d) in bp)
        util = used / cap if cap > 0 else 0.0
        dissipation += (1.0 - util) ** 2

    composite = float(n_bins) + 0.1 * dissipation
    return n_bins, dissipation, composite


# ─────────────────────────────────────────────────────────────────────────────
# Wolf class
# ─────────────────────────────────────────────────────────────────────────────

class Wolf:
    """
    A single GWO candidate solution.

    Genotype  : self.sequence  (permutation of item indices)
    Phenotype : self.bins_placed / self.placements  (decoded by DBLF)
    """

    __slots__ = ('items', 'container', 'n', 'sequence',
                 'bins_placed', 'placements', 'bin_items',
                 'n_bins', 'dissipation', 'composite')

    def __init__(self, items, container):
        self.items     = items
        self.container = container
        self.n         = len(items)
        self.sequence  = list(range(self.n))
        random.shuffle(self.sequence)
        self._decode()

    def _decode(self):
        """Decode current sequence into packing and evaluate fitness."""
        self.bins_placed, self.placements, self.bin_items = place_items(
            self.sequence, self.items, self.container
        )
        self.n_bins, self.dissipation, self.composite = compute_fitness(
            self.bins_placed, self.container
        )

    def set_sequence(self, seq):
        """Replace sequence and re-decode."""
        self.sequence = seq[:]
        self._decode()

    def copy(self):
        """Return a deep-enough copy (items/container are shared references)."""
        w = Wolf.__new__(Wolf)
        w.items      = self.items        # shared – never modified
        w.container  = self.container    # shared – never modified
        w.n          = self.n
        w.sequence   = self.sequence[:]
        w.bins_placed = [b[:] for b in self.bins_placed]
        w.placements  = dict(self.placements)
        w.bin_items   = [bi[:] for bi in self.bin_items]
        w.n_bins      = self.n_bins
        w.dissipation = self.dissipation
        w.composite   = self.composite
        return w