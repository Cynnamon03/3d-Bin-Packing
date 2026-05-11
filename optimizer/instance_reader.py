"""
instance_reader.py
Reads a Bischoff-Ratcliff (BR) dataset JSON file and returns
a container dict and a flat list of item dicts.

BR JSON structure (confirmed from BR0/1.json):
  Objects[0]: { Length, Height, Depth, Stock, Cost }   <- the bin/container
  Items[]:    { Length, Height, Depth, C1_Length,
                C1_Height, C1_Depth, Demand, Value }   <- items to pack

C1_X == 1 means that dimension can participate in a rotation.
Demand is how many copies of this item type must be packed.
"""

import json


def load_instance(json_path):
    """
    Load a BR JSON file.

    Returns
    -------
    container : dict
        {'L': int, 'H': int, 'D': int}
    items : list of dict
        Each dict: {'L', 'H', 'D', 'can_rotate': bool, 'stop': int}
        The list is already expanded by Demand (one entry per physical item).
    """
    with open(json_path, 'r') as f:
        data = json.load(f)

    # ── Container ────────────────────────────────────────────────────────────
    obj = data['Objects'][0]
    container = {
        'L': int(obj['Length']),
        'H': int(obj['Height']),
        'D': int(obj['Depth']),
    }

    # ── Items (expanded by Demand) ────────────────────────────────────────────
    items = []
    for item_def in data['Items']:
        demand = int(item_def.get('Demand') or 1)

        # An item may be rotated if any C1 flag is 1.
        # (C1_Height=1 means the item can be placed on its side in that axis.)
        can_rotate = bool(
            item_def.get('C1_Length', 0) or
            item_def.get('C1_Height', 0) or
            item_def.get('C1_Depth', 0)
        )

        for _ in range(demand):
            items.append({
                'L': int(item_def['Length']),
                'H': int(item_def['Height']),
                'D': int(item_def['Depth']),
                'can_rotate': can_rotate,
                'stop': 1,   # single-stop default; extend for LIFO later
            })

    return container, items


# ── Quick smoke-test ──────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python instance_reader.py <path_to_instance.json>")
        sys.exit(1)

    c, its = load_instance(sys.argv[1])
    print(f"Container : L={c['L']}  H={c['H']}  D={c['D']}")
    print(f"Items     : {len(its)} total")
    vol_container = c['L'] * c['H'] * c['D']
    vol_items = sum(i['L'] * i['H'] * i['D'] for i in its)
    print(f"Volume fill ratio (lower bound): "
          f"{vol_items / vol_container:.2%}  "
          f"→ at least {-(-vol_items // vol_container)} bin(s) needed")
    print("First 3 items:", its[:3])