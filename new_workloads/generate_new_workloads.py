#!/usr/bin/env python3
"""Generate workload files described by workload_specification.md."""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GENERATED_WORKLOADS = ROOT / "generated_workloads"
sys.path.insert(0, str(GENERATED_WORKLOADS))

from generate_ycsb_workloads import ZipfianGenerator  # noqa: E402


OUT_DIR = ROOT / "new_workloads"

RECORD_COUNT = 600_000
OPS_PER_FILE = 1_000
FILES_PER_TYPE = 50
WINDOW_SIZE = 60_000
TAIL_SIZE = 60_000
ZIPF_THETA = 0.99
SCAN_LEN = 50
BASE_SEED = 20_260_617

READ_VALID_START = 1
READ_VALID_END = RECORD_COUNT
SCAN_VALID_START = 1
SCAN_VALID_END = RECORD_COUNT - SCAN_LEN + 1

SUMMARY_FIELDS = [
    "filename",
    "type",
    "operation",
    "distribution",
    "range_type",
    "file_index",
    "seed",
    "record_count",
    "op_count",
    "valid_id_start",
    "valid_id_end",
    "range_start",
    "range_end",
    "window_size",
    "tail_size",
    "zipf_theta",
    "zipf_direction",
    "scan_len",
]

WORKLOAD_TYPES = [
    ("read_uniform_full", "read", "uniform", "full"),
    ("read_uniform_window", "read", "uniform", "window"),
    ("read_uniform_tail", "read", "uniform", "tail"),
    ("read_zipf_full", "read", "zipf", "full"),
    ("read_zipf_window", "read", "zipf", "window"),
    ("read_zipf_tail", "read", "zipf", "tail"),
    ("scan_uniform_full", "scan", "uniform", "full"),
    ("scan_uniform_window", "scan", "uniform", "window"),
    ("scan_uniform_tail", "scan", "uniform", "tail"),
    ("scan_zipf_full", "scan", "zipf", "full"),
    ("scan_zipf_window", "scan", "zipf", "window"),
    ("scan_zipf_tail", "scan", "zipf", "tail"),
]


def valid_range(operation: str) -> tuple[int, int]:
    if operation == "read":
        return READ_VALID_START, READ_VALID_END
    if operation == "scan":
        return SCAN_VALID_START, SCAN_VALID_END
    raise ValueError(f"unsupported operation: {operation}")


def choose_range(operation: str, range_type: str, rng: random.Random) -> tuple[int, int]:
    if operation == "read":
        if range_type == "full":
            return 1, RECORD_COUNT
        if range_type == "window":
            start = rng.randint(1, RECORD_COUNT - TAIL_SIZE - WINDOW_SIZE + 1)
            return start, start + WINDOW_SIZE - 1
        if range_type == "tail":
            return RECORD_COUNT - TAIL_SIZE + 1, RECORD_COUNT
    elif operation == "scan":
        if range_type == "full":
            return 1, SCAN_VALID_END
        if range_type == "window":
            start = rng.randint(1, SCAN_VALID_END - TAIL_SIZE - WINDOW_SIZE + 1)
            return start, start + WINDOW_SIZE - 1
        if range_type == "tail":
            return SCAN_VALID_END - TAIL_SIZE + 1, SCAN_VALID_END
    raise ValueError(f"unsupported operation/range_type: {operation}/{range_type}")


def zipf_direction(range_type: str) -> str:
    if range_type in {"full", "window"}:
        return "forward"
    if range_type == "tail":
        return "reverse"
    raise ValueError(f"unsupported range_type: {range_type}")


def iter_ids(
    distribution: str,
    range_type: str,
    range_start: int,
    range_end: int,
    rng: random.Random,
):
    if distribution == "uniform":
        for _ in range(OPS_PER_FILE):
            yield rng.randint(range_start, range_end)
        return

    if distribution == "zipf":
        size = range_end - range_start + 1
        generator = ZipfianGenerator(1, size, rng, theta=ZIPF_THETA)
        direction = zipf_direction(range_type)
        for _ in range(OPS_PER_FILE):
            rank = generator.next()
            if direction == "forward":
                yield range_start + rank - 1
            else:
                yield range_end - rank + 1
        return

    raise ValueError(f"unsupported distribution: {distribution}")


def write_workload(
    filename: str,
    operation: str,
    distribution: str,
    range_type: str,
    range_start: int,
    range_end: int,
    rng: random.Random,
) -> None:
    path = OUT_DIR / filename
    with path.open("w", encoding="utf-8", newline="\n") as out:
        for item_id in iter_ids(distribution, range_type, range_start, range_end, rng):
            if operation == "read":
                out.write(f"read {item_id}\n")
            elif operation == "scan":
                out.write(f"scan {item_id} {SCAN_LEN}\n")
            else:
                raise ValueError(f"unsupported operation: {operation}")


def build_summary_row(
    filename: str,
    workload_type: str,
    operation: str,
    distribution: str,
    range_type: str,
    file_index: int,
    seed: int,
    range_start: int,
    range_end: int,
) -> dict[str, object]:
    valid_id_start, valid_id_end = valid_range(operation)
    return {
        "filename": filename,
        "type": workload_type,
        "operation": operation,
        "distribution": distribution,
        "range_type": range_type,
        "file_index": file_index,
        "seed": seed,
        "record_count": RECORD_COUNT,
        "op_count": OPS_PER_FILE,
        "valid_id_start": valid_id_start,
        "valid_id_end": valid_id_end,
        "range_start": range_start,
        "range_end": range_end,
        "window_size": WINDOW_SIZE,
        "tail_size": TAIL_SIZE,
        "zipf_theta": ZIPF_THETA,
        "zipf_direction": zipf_direction(range_type) if distribution == "zipf" else "",
        "scan_len": SCAN_LEN if operation == "scan" else "",
    }


def generate() -> list[dict[str, object]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, object]] = []

    for type_index, (workload_type, operation, distribution, range_type) in enumerate(WORKLOAD_TYPES):
        for file_index in range(1, FILES_PER_TYPE + 1):
            seed = BASE_SEED + type_index * 1000 + file_index
            rng = random.Random(seed)
            range_start, range_end = choose_range(operation, range_type, rng)
            filename = f"{operation}_{distribution}_{range_type}_{file_index:03d}.txt"

            write_workload(
                filename,
                operation,
                distribution,
                range_type,
                range_start,
                range_end,
                rng,
            )
            summary_rows.append(
                build_summary_row(
                    filename,
                    workload_type,
                    operation,
                    distribution,
                    range_type,
                    file_index,
                    seed,
                    range_start,
                    range_end,
                )
            )

    summary_path = OUT_DIR / "SUMMARY.csv"
    with summary_path.open("w", encoding="utf-8", newline="\n") as out:
        writer = csv.DictWriter(out, fieldnames=SUMMARY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary_rows)

    return summary_rows


def main() -> int:
    summary_rows = generate()
    print(f"generated {len(summary_rows)} workload files in {OUT_DIR}")
    print(f"summary -> {OUT_DIR / 'SUMMARY.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
