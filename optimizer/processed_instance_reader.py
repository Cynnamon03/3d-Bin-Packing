#!/usr/bin/env python3
"""Load preprocessed training instances from data/train/instances.json."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

TRAIN_DIR = Path(__file__).resolve().parents[1] / 'data' / 'train'
TRAIN_JSON = TRAIN_DIR / 'instances.json'


def _assert_train_path(path: Path) -> None:
    resolved = path.resolve()
    train_root = TRAIN_DIR.resolve()
    if train_root not in [resolved, *resolved.parents]:
        raise PermissionError(
            f"Unauthorized Access: data must be loaded from the training set under {train_root}"
        )


def load_train_dataset(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load the full preprocessed training dataset."""
    json_path = Path(path) if path else TRAIN_JSON
    _assert_train_path(json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"Training JSON not found: {json_path}")

    with json_path.open('r', encoding='utf-8') as infile:
        payload = json.load(infile)

    instances = payload.get('instances')
    if not isinstance(instances, list):
        raise ValueError(f"Malformed training JSON: {json_path}")
    return instances


def load_train_instance(index: int = 0, path: Optional[str] = None) -> Dict[str, Any]:
    """Return a single training instance by zero-based index."""
    instances = load_train_dataset(path)
    if index < 0 or index >= len(instances):
        raise IndexError(f"Instance index {index} out of range (0..{len(instances)-1})")
    return instances[index]
