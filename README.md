# 3D Bin Packing Preprocessing and Baseline Pipeline

## Pipeline Architecture

This repository separates dataset preparation from optimization execution.

- `preprocess.py` is the deterministic data preparation pipeline.
- The optimizer in `optimizer/` consumes only preprocessed JSON.

The architecture enforces a strict boundary:
- Preprocessing performs auditing, parsing, cleaning, normalization, orientation generation, and greedy seeding.
- The optimizer no longer performs raw data parsing or cleaning.
- `data/held_out/` is isolated for final validation only and must not be used during baseline tuning.

## The Preprocessing Workflow

`preprocess.py` implements a seven-step preparation pipeline for 3D bin packing datasets:

1. **Audit (data integrity)**
   - Scans raw input files for JSON formatting issues, missing schema fields, non-numeric tokens, and empty lines.

2. **Parsing**
   - Loads `.json`, `.txt`, and `.dat` files from the raw dataset root.
   - Extracts container and item definitions into a normalized instance model.

3. **Cleaning (Zero-dim, Oversized, Duplicates)**
   - Removes items with zero or negative dimensions.
   - Discards items that cannot fit any container orientation.
   - Filters duplicate instances and malformed data.

4. **Item Expansion (Qty to individual IDs)**
   - Converts quantity fields into individual item objects.
   - Each expanded item receives a unique ID for deterministic downstream processing.

5. **Normalisation ([0,1] scaling)**
   - Scales item dimensions relative to the container.
   - Produces normalized item fields such as `L_norm`, `W_norm`, and `H_norm`.

6. **Orientation Pre-generation**
   - Computes all distinct valid 3D orientations for each item.
   - Stores orientation candidates in each instance before optimization.

7. **Greedy Seeding (Volume-based sorting)**
   - Computes a deterministic greedy seed order by sorting items by volume in descending order.
   - This order supports reproducible heuristic initialization.

## Data Split Protocol

The preprocessing pipeline produces two disjoint datasets:

- `data/train/instances.json`
- `data/held_out/instances.json`

The split is:
- **70% training data**
- **30% held-out validation data**
- **Fixed random seed: `42`** for reproducible shuffling and assignment

> `data/held_out/` is strictly reserved for final validation and must never be used during baseline execution.

## Usage Guide

### 1. Run the preprocessing pipeline

From the repository root:

```bash
python preprocess.py \
  --source data/CLP-Datasets-main \
  --train-dir data/train \
  --held-out-dir data/held_out \
  --report-path preprocessing_report.txt \
  --train-ratio 0.7 \
  --random-seed 42
```

This command:
- audits and parses raw dataset files,
- cleans and normalizes each instance,
- expands item quantities,
- generates orientation metadata,
- sorts greedy seeds deterministically,
- writes training and held-out JSON payloads,
- writes `preprocessing_report.txt`.

### 2. Run the baseline optimizer on the training set

From the repository root:

```bash
python optimizer/run_baseline.py
```

By default, this command uses the preprocessed training file:

```text
data/train/instances.json
```

Optional flags:

```bash
python optimizer/run_baseline.py \
  --data_path data/train/instances.json \
  --count 5 \
  --pop 20 \
  --iter 50 \
  --max-time 60 \
  --out optimizer/results.json
```

## Before vs. After: Data Formats

| Stage | Format | Purpose |
|---|---|---|
| Raw | `JSON`, `TXT`, `DAT` | Diverse benchmark input formats with container/item definitions |
| Preprocessed | `data/train/instances.json` / `data/held_out/instances.json` | Clean, normalized JSON ready for optimizer execution |

### Raw data example

```json
{
  "Objects": [{ "Length": 100, "Depth": 50, "Height": 50 }],
  "Items": [
    { "Length": 10, "Depth": 20, "Height": 30, "Demand": 2 }
  ]
}
```

### Preprocessed output example

```json
{
  "instances": [
    {
      "id": "BR0_1",
      "container": { "L": 100, "W": 50, "H": 50 },
      "container_norm": { "L": 1.0, "W": 1.0, "H": 1.0 },
      "items": [
        {
          "id": "BR0_1_1_1",
          "L": 10,
          "W": 20,
          "H": 30,
          "qty": 1,
          "volume": 6000,
          "L_norm": 0.1,
          "W_norm": 0.4,
          "H_norm": 0.6,
          "orientations": [
            { "L": 10, "W": 20, "H": 30 },
            { "L": 10, "W": 30, "H": 20 }
          ]
        }
      ],
      "greedy_seed": ["BR0_1_1_1"],
      "item_count": 1
    }
  ]
}
```

## Directory Structure

```text
3d-bin-packing/
├── data/
│   ├── train/
│   │   └── instances.json
│   ├── held_out/
│   │   └── instances.json
│   └── CLP-Datasets-main/  # raw benchmark source files
├── optimizer/
│   ├── baseline_2d.py
│   ├── processed_instance_reader.py
│   └── run_baseline.py
├── preprocess.py
└── preprocessing_report.txt
```

## Key Notes

- The optimizer is now a consumer of preprocessed JSON only.
- No data cleaning or normalization occurs inside `optimizer/run_baseline.py`.
- `preprocess.py` is responsible for all data hygiene, reproducible splitting, and metadata generation.
- `data/held_out/` is isolated for validation and should never be used for baseline tuning or training.

## Validation and Reproducibility

The preprocessing stage is designed for scientific rigor:
- deterministic sorting and greedy seed generation,
- fixed seed `42` for split reproducibility,
- explicit audit reporting,
- normalized dimensions in the range `[0, 1]`.

Use `preprocessing_report.txt` to review dataset integrity, cleaning statistics, and normalization ranges.
