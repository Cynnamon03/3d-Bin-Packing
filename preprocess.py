#!/usr/bin/env python3
"""Standalone preprocessing pipeline for 3D bin-packing datasets."""

import argparse
import json
import math
import os
import random
from collections import Counter
from typing import Any, Dict, List, Tuple


def audit_file(file_path: str) -> List[Dict[str, Any]]:
    """Inspect a raw dataset file and return a list of formatting issues."""
    issues = []
    if file_path.lower().endswith('.json'):
        try:
            with open(file_path, 'r', encoding='utf-8') as infile:
                payload = json.load(infile)
        except Exception as exc:
            issues.append({'path': file_path, 'type': 'json_parse_error', 'message': str(exc)})
            print(f"[AUDIT] {file_path}: JSON parse error: {exc}")
            return issues

        if not isinstance(payload, dict):
            issues.append({'path': file_path, 'type': 'json_format_error', 'message': 'Root element is not an object'})
            print(f"[AUDIT] {file_path}: root JSON is not an object")
            return issues

        if 'Objects' not in payload or 'Items' not in payload:
            issues.append({'path': file_path, 'type': 'json_schema_error', 'message': 'Missing Objects or Items arrays'})
            print(f"[AUDIT] {file_path}: missing Objects or Items")
            return issues

        for side, collection in [('container', payload.get('Objects', [])), ('items', payload.get('Items', []))]:
            if not isinstance(collection, list):
                issues.append({'path': file_path, 'type': 'json_schema_error', 'message': f'{side} is not a list'})
                continue
            for index, entry in enumerate(collection, start=1):
                if not isinstance(entry, dict):
                    issues.append({'path': file_path, 'type': 'json_schema_error', 'message': f'{side}[{index}] is not an object'})
                    continue
                for key in ('Length', 'Height', 'Depth'):
                    if key in entry:
                        try:
                            float(entry[key])
                        except Exception:
                            issues.append({'path': file_path, 'type': 'non_numeric_token', 'line': index, 'token': key, 'message': f'Non-numeric {key} in {side}[{index}]'})
        if issues:
            print(f"[AUDIT] {file_path}: found {len(issues)} JSON issues")
        else:
            print(f"[AUDIT] {file_path}: OK")
        return issues

    with open(file_path, 'r', encoding='utf-8', errors='replace') as infile:
        lines = infile.readlines()

    for line_num, line in enumerate(lines, start=1):
        if line.strip() == '':
            issues.append({'path': file_path, 'line': line_num, 'type': 'empty_line', 'message': 'Empty or whitespace-only line'})
            continue
        tokens = line.strip().split()
        for token in tokens:
            try:
                float(token)
            except ValueError:
                issues.append({'path': file_path, 'line': line_num, 'type': 'non_numeric_token', 'token': token, 'message': 'Non-numeric token'})

    if issues:
        print(f"[AUDIT] {file_path}: found {len(issues)} issues")
    else:
        print(f"[AUDIT] {file_path}: OK")
    return issues


def _normalize_container(raw_container: Dict[str, Any]) -> Dict[str, float]:
    return {
        'L': float(raw_container.get('Length') or raw_container.get('L') or raw_container.get('Width') or 0),
        'W': float(raw_container.get('Depth') or raw_container.get('Width') or raw_container.get('W') or 0),
        'H': float(raw_container.get('Height') or raw_container.get('H') or 0),
    }


def _normalize_item(raw_item: Dict[str, Any], item_id: str) -> Dict[str, Any]:
    return {
        'id': item_id,
        'L': float(raw_item.get('Length') or raw_item.get('L') or raw_item.get('Width') or 0),
        'W': float(raw_item.get('Depth') or raw_item.get('Width') or raw_item.get('W') or 0),
        'H': float(raw_item.get('Height') or raw_item.get('H') or 0),
        'qty': int(raw_item.get('Demand') or raw_item.get('qty') or raw_item.get('quantity') or 1),
        'seed': raw_item.get('seed'),
        'source': raw_item.get('source'),
    }


def _item_fits_bin(item: Dict[str, Any], container: Dict[str, float]) -> bool:
    dims = (item['L'], item['W'], item['H'])
    for perm in {
        (dims[0], dims[1], dims[2]),
        (dims[0], dims[2], dims[1]),
        (dims[1], dims[0], dims[2]),
        (dims[1], dims[2], dims[0]),
        (dims[2], dims[0], dims[1]),
        (dims[2], dims[1], dims[0]),
    }:
        if perm[0] <= container['L'] and perm[1] <= container['W'] and perm[2] <= container['H']:
            return True
    return False


def parse_json_instance(file_path: str) -> List[Dict[str, Any]]:
    """Parse a dataset instance from a JSON file."""
    with open(file_path, 'r', encoding='utf-8') as infile:
        payload = json.load(infile)

    container = None
    if isinstance(payload.get('Objects'), list) and payload['Objects']:
        container = _normalize_container(payload['Objects'][0])
    if container is None or min(container.values()) <= 0:
        raise ValueError(f"Invalid container in {file_path}")

    items = []
    for item_index, raw_item in enumerate(payload.get('Items', []), start=1):
        normalized = _normalize_item(raw_item, item_id=str(item_index))
        normalized['source'] = 'json'
        normalized['original_id'] = raw_item.get('id') or raw_item.get('ID') or item_index
        items.append(normalized)

    folder = os.path.basename(os.path.dirname(file_path))
    instance_id = f"{folder}_{payload.get('Name') or os.path.splitext(os.path.basename(file_path))[0]}"
    return [{'id': instance_id, 'container': container, 'items': items, 'source_path': file_path}]


def parse_clp_raw_file(file_path: str) -> List[Dict[str, Any]]:
    """Parse a raw CLP text file into structured instances."""
    with open(file_path, 'r', encoding='utf-8', errors='replace') as infile:
        lines = [line.strip() for line in infile.readlines() if line.strip() != '']

    if not lines:
        return []

    number_of_instances = int(lines[0])
    if len(lines) < 4:
        raise ValueError(f"Unexpected CLP raw format in {file_path}")

    number_of_item_types = int(lines[3])
    instances = []
    for instance_index in range(number_of_instances):
        base_pos = instance_index * (number_of_item_types + 3) + 1
        header_line = lines[base_pos + 1].split()
        if len(header_line) != 3:
            raise ValueError(f"Expected container dimension line with 3 values in {file_path} at instance {instance_index + 1}")
        container = {'L': float(header_line[0]), 'W': float(header_line[2]), 'H': float(header_line[1])}

        items = []
        for item_offset in range(number_of_item_types):
            raw_tokens = lines[base_pos + 3 + item_offset].split()
            if len(raw_tokens) < 8:
                raise ValueError(f"Expected 8 tokens for item line in {file_path} at instance {instance_index + 1}, item {item_offset + 1}")
            _, l_item, _, d_item, _, h_item, _, quantity = raw_tokens[:8]
            item = {
                'Length': float(l_item),
                'Depth': float(d_item),
                'Height': float(h_item),
                'Demand': int(quantity),
            }
            items.append(_normalize_item(item, item_id=str(item_offset + 1)))

        folder = os.path.basename(os.path.dirname(file_path))
        instance_id = f"{folder}_{instance_index + 1}"
        instances.append({
            'id': instance_id,
            'container': container,
            'items': items,
            'source_path': f"{file_path}#{instance_index + 1}",
        })
    return instances


def load_instances(source_root: str) -> List[Dict[str, Any]]:
    """Traverse the source folder and load dataset instances from JSON and raw text files."""
    instances = []
    supported = {'.json', '.txt', '.dat'}
    for root, _, files in os.walk(source_root):
        for file_name in sorted(files):
            ext = os.path.splitext(file_name)[1].lower()
            if ext not in supported:
                continue
            path = os.path.join(root, file_name)
            if ext == '.json':
                try:
                    instances.extend(parse_json_instance(path))
                except Exception as exc:
                    print(f"[PARSE] Skipping {path}: {exc}")
            else:
                try:
                    instances.extend(parse_clp_raw_file(path))
                except Exception as exc:
                    print(f"[PARSE] Skipping {path}: {exc}")
    return instances


def clean_instances(instances: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Apply cleaning rules to a parsed instance list."""
    seen_fingerprints = set()
    clean_list = []
    stats = Counter()

    for instance in instances:
        if instance.get('id') is None:
            stats['duplicate_instance'] += 1
            continue

        fingerprint = instance.get('source_path') or instance.get('id')
        if fingerprint in seen_fingerprints:
            stats['duplicate_instance'] += 1
            continue

        seen_fingerprints.add(fingerprint)
        valid_items = []
        for item in instance['items']:
            if item['L'] <= 0 or item['W'] <= 0 or item['H'] <= 0:
                stats['zero_dimension'] += 1
                continue
            if not _item_fits_bin(item, instance['container']):
                stats['oversized_item'] += 1
                continue
            valid_items.append(item)

        if not valid_items:
            stats['malformed_instance'] += 1
            continue

        instance['items'] = valid_items
        clean_list.append(instance)

    return clean_list, dict(stats)


def expand_items(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Expand quantity fields into individual item objects."""
    expanded = []
    for item_index, item in enumerate(instance['items'], start=1):
        qty = max(1, int(item.get('qty', 1)))
        for copy_index in range(qty):
            expanded.append({
                'id': f"{instance['id']}_{item_index}_{copy_index + 1}",
                'L': item['L'],
                'W': item['W'],
                'H': item['H'],
                'qty': 1,
                'source': item.get('source'),
                'original_id': item.get('original_id'),
            })
    instance['items'] = expanded
    return instance


def pre_generate_orientations(item: Dict[str, Any], container: Dict[str, float]) -> List[Dict[str, float]]:
    """Create all distinct valid orientations for a single item."""
    dims = (item['L'], item['W'], item['H'])
    orientations = []
    seen = set()
    for perm in [
        (dims[0], dims[1], dims[2]),
        (dims[0], dims[2], dims[1]),
        (dims[1], dims[0], dims[2]),
        (dims[1], dims[2], dims[0]),
        (dims[2], dims[0], dims[1]),
        (dims[2], dims[1], dims[0]),
    ]:
        if perm in seen:
            continue
        seen.add(perm)
        if perm[0] <= container['L'] and perm[1] <= container['W'] and perm[2] <= container['H']:
            orientations.append({'L': perm[0], 'W': perm[1], 'H': perm[2]})
    return orientations


def normalize_instance(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize dimensions and compute orientation and greedy seed metadata."""
    container = instance['container']
    if container['L'] <= 0 or container['W'] <= 0 or container['H'] <= 0:
        raise ValueError(f"Invalid container dimensions in instance {instance.get('id')}")

    instance['container_norm'] = {
        'L': 1.0,
        'W': 1.0,
        'H': 1.0,
    }
    instance['items'] = [
        {
            **item,
            'volume': item['L'] * item['W'] * item['H'],
            'L_norm': item['L'] / container['L'],
            'W_norm': item['W'] / container['W'],
            'H_norm': item['H'] / container['H'],
            'orientations': pre_generate_orientations(item, container),
        }
        for item in instance['items']
    ]

    instance['greedy_seed'] = [item['id'] for item in sorted(instance['items'], key=lambda x: x['volume'], reverse=True)]
    instance['item_count'] = len(instance['items'])
    instance['container'] = {
        'L': container['L'],
        'W': container['W'],
        'H': container['H'],
    }
    return instance


def split_instances(instances: List[Dict[str, Any]], train_ratio: float, seed: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rng = random.Random(seed)
    shuffled = list(instances)
    rng.shuffle(shuffled)
    split_index = int(len(shuffled) * train_ratio)
    return shuffled[:split_index], shuffled[split_index:]


def save_json(data: Any, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as outfile:
        json.dump(data, outfile, indent=2)


def write_report(report_path: str, summary: Dict[str, Any]) -> None:
    lines = [
        'Preprocessing Report',
        '====================',
        f"Total instances parsed: {summary['total_instances_parsed']}",
        f"Instances after cleaning: {summary['instances_after_cleaning']}",
        f"Train instances: {summary['train_count']}",
        f"Held-out instances: {summary['held_out_count']}",
        '',
        'Cleaning summary:',
        f"  Zero-dimension items removed: {summary['removed_zero_dimension']}",
        f"  Oversized items removed: {summary['removed_oversized_item']}",
        f"  Duplicate instances removed: {summary['removed_duplicate_instance']}",
        f"  Malformed instances removed: {summary['removed_malformed_instance']}",
        '',
        'Dimension range before normalization:',
        f"  Container L: {summary['container_min_before_L']:.3f} - {summary['container_max_before_L']:.3f}",
        f"  Container W: {summary['container_min_before_W']:.3f} - {summary['container_max_before_W']:.3f}",
        f"  Container H: {summary['container_min_before_H']:.3f} - {summary['container_max_before_H']:.3f}",
        f"  Item L: {summary['item_min_before_L']:.3f} - {summary['item_max_before_L']:.3f}",
        f"  Item W: {summary['item_min_before_W']:.3f} - {summary['item_max_before_W']:.3f}",
        f"  Item H: {summary['item_min_before_H']:.3f} - {summary['item_max_before_H']:.3f}",
        '',
        'Dimension range after normalization:',
        f"  Item L_norm: {summary['item_min_after_L']:.6f} - {summary['item_max_after_L']:.6f}",
        f"  Item W_norm: {summary['item_min_after_W']:.6f} - {summary['item_max_after_W']:.6f}",
        f"  Item H_norm: {summary['item_min_after_H']:.6f} - {summary['item_max_after_H']:.6f}",
    ]
    with open(report_path, 'w', encoding='utf-8') as outfile:
        outfile.write('\n'.join(lines) + '\n')
    print(f"[REPORT] Wrote report to {report_path}")


def compute_dimension_stats(instances: List[Dict[str, Any]]) -> Dict[str, float]:
    container_L = [instance['container']['L'] for instance in instances]
    container_W = [instance['container']['W'] for instance in instances]
    container_H = [instance['container']['H'] for instance in instances]
    item_L = [item['L'] for instance in instances for item in instance['items']]
    item_W = [item['W'] for instance in instances for item in instance['items']]
    item_H = [item['H'] for instance in instances for item in instance['items']]
    item_L_norm = [item['L_norm'] for instance in instances for item in instance['items']]
    item_W_norm = [item['W_norm'] for instance in instances for item in instance['items']]
    item_H_norm = [item['H_norm'] for instance in instances for item in instance['items']]
    return {
        'container_min_before_L': min(container_L) if container_L else 0.0,
        'container_max_before_L': max(container_L) if container_L else 0.0,
        'container_min_before_W': min(container_W) if container_W else 0.0,
        'container_max_before_W': max(container_W) if container_W else 0.0,
        'container_min_before_H': min(container_H) if container_H else 0.0,
        'container_max_before_H': max(container_H) if container_H else 0.0,
        'item_min_before_L': min(item_L) if item_L else 0.0,
        'item_max_before_L': max(item_L) if item_L else 0.0,
        'item_min_before_W': min(item_W) if item_W else 0.0,
        'item_max_before_W': max(item_W) if item_W else 0.0,
        'item_min_before_H': min(item_H) if item_H else 0.0,
        'item_max_before_H': max(item_H) if item_H else 0.0,
        'item_min_after_L': min(item_L_norm) if item_L_norm else 0.0,
        'item_max_after_L': max(item_L_norm) if item_L_norm else 0.0,
        'item_min_after_W': min(item_W_norm) if item_W_norm else 0.0,
        'item_max_after_W': max(item_W_norm) if item_W_norm else 0.0,
        'item_min_after_H': min(item_H_norm) if item_H_norm else 0.0,
        'item_max_after_H': max(item_H_norm) if item_H_norm else 0.0,
    }


def build_pipeline(args: argparse.Namespace) -> None:
    print(f"[PIPELINE] Loading dataset from {args.source}")
    if not os.path.isdir(args.source):
        raise FileNotFoundError(f"Source dataset folder not found: {args.source}")

    instance_files = []
    for root, _, files in os.walk(args.source):
        for filename in sorted(files):
            ext = os.path.splitext(filename)[1].lower()
            if ext in {'.json', '.txt', '.dat'}:
                instance_files.append(os.path.join(root, filename))

    audit_issues = []
    for path in instance_files:
        audit_issues.extend(audit_file(path))

    if audit_issues:
        print(f"[PIPELINE] Audit completed with {len(audit_issues)} issues across {len(instance_files)} files")
    else:
        print(f"[PIPELINE] Audit completed: no issues found in {len(instance_files)} files")

    raw_instances = load_instances(args.source)
    print(f"[PIPELINE] Parsed {len(raw_instances)} instances")

    clean_list, clean_stats = clean_instances(raw_instances)
    print(f"[PIPELINE] Cleaned to {len(clean_list)} instances")

    expanded_instances = [expand_items(instance) for instance in clean_list]
    normalized_instances = [normalize_instance(instance) for instance in expanded_instances]

    train_instances, held_out_instances = split_instances(normalized_instances, args.train_ratio, args.random_seed)

    os.makedirs(args.train_dir, exist_ok=True)
    os.makedirs(args.held_out_dir, exist_ok=True)
    save_json({'instances': train_instances}, os.path.join(args.train_dir, 'instances.json'))
    save_json({'instances': held_out_instances}, os.path.join(args.held_out_dir, 'instances.json'))

    stats = compute_dimension_stats(normalized_instances)
    summary = {
        'total_instances_parsed': len(raw_instances),
        'instances_after_cleaning': len(clean_list),
        'train_count': len(train_instances),
        'held_out_count': len(held_out_instances),
        'removed_zero_dimension': clean_stats.get('zero_dimension', 0),
        'removed_oversized_item': clean_stats.get('oversized_item', 0),
        'removed_duplicate_instance': clean_stats.get('duplicate_instance', 0),
        'removed_malformed_instance': clean_stats.get('malformed_instance', 0),
        **stats,
    }
    write_report(args.report_path, summary)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Preprocess 3D bin-packing datasets into normalized JSON.')
    parser.add_argument('--source', default='data/CLP-Datasets-main', help='Root path to raw dataset files.')
    parser.add_argument('--train-dir', default='data/train', help='Output directory for training JSON.')
    parser.add_argument('--held-out-dir', default='data/held_out', help='Output directory for held-out JSON.')
    parser.add_argument('--report-path', default='preprocessing_report.txt', help='Path for the preprocessing report.')
    parser.add_argument('--train-ratio', type=float, default=0.7, help='Fraction of instances allocated to training.')
    parser.add_argument('--random-seed', type=int, default=42, help='Seed for shuffle and split reproducibility.')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    build_pipeline(args)
