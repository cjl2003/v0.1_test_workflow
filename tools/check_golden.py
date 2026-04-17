#!/usr/bin/env python3
"""Validate the repository golden vectors and optional simulation output."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


MASK24 = (1 << 24) - 1
LABELS = {
    "products": "products",
    "mode0_raw": "mode 0 raw",
    "mode0_sum_out": "mode 0 sum_out",
    "mode0_carry": "mode 0 carry",
    "mode1_raw": "mode 1 raw",
    "mode1_sum_out": "mode 1 sum_out",
    "mode1_carry": "mode 1 carry",
    "switch_sum_out": "switch sum_out",
    "switch_carry": "switch carry",
}


def parse_int_list(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def parse_pair_list(raw: str) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for left, right in re.findall(r"\((\d+),\s*(\d+)\)", raw):
        pairs.append((int(left), int(right)))
    return pairs


def parse_section(text: str, header: str) -> str:
    pattern = re.compile(
        rf"{re.escape(header)}:\s*(.*?)(?:\n\s*\n|\Z)",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Missing section: {header}")
    return match.group(1).strip()


def parse_golden_vectors(text: str) -> dict[str, list[int] | list[tuple[int, int]]]:
    input_pairs = parse_pair_list(parse_section(text, "Input pairs"))
    products = parse_int_list(parse_section(text, "Products"))

    mode0_block = parse_section(text, "mode 0")
    mode1_block = parse_section(text, "mode 1")
    switch_block = parse_section(text, "mode 0 -> 1 switch after (14,71)")

    def read_named_list(block: str, name: str) -> list[int]:
        match = re.search(rf"{re.escape(name)} = ([^\n]+)", block)
        if not match:
            raise ValueError(f"Missing line {name} in golden vector section.")
        return parse_int_list(match.group(1))

    return {
        "input_pairs": input_pairs,
        "products": products,
        "mode0_raw": read_named_list(mode0_block, "raw"),
        "mode0_sum_out": read_named_list(mode0_block, "sum_out[23:0]"),
        "mode0_carry": read_named_list(mode0_block, "carry"),
        "mode1_raw": read_named_list(mode1_block, "raw"),
        "mode1_sum_out": read_named_list(mode1_block, "sum_out[23:0]"),
        "mode1_carry": read_named_list(mode1_block, "carry"),
        "switch_sum_out": read_named_list(switch_block, "sum_out[23:0]"),
        "switch_carry": read_named_list(switch_block, "carry"),
    }


def compute_expected_vectors(
    input_pairs: list[tuple[int, int]]
) -> dict[str, list[int] | list[tuple[int, int]]]:
    products = [left * right for left, right in input_pairs]
    mode0_raw = [products[0]] + [
        products[index] + products[index - 1] for index in range(1, len(products))
    ]
    mode1_raw: list[int] = []
    running = 0
    for product in products:
        running += product
        mode1_raw.append(running)

    switch_raw = mode0_raw[:3]
    running = 0
    for product in products[3:]:
        running += product
        switch_raw.append(running)

    def sums(values: list[int]) -> list[int]:
        return [value & MASK24 for value in values]

    def carries(values: list[int]) -> list[int]:
        return [1 if value > MASK24 else 0 for value in values]

    return {
        "input_pairs": input_pairs,
        "products": products,
        "mode0_raw": mode0_raw,
        "mode0_sum_out": sums(mode0_raw),
        "mode0_carry": carries(mode0_raw),
        "mode1_raw": mode1_raw,
        "mode1_sum_out": sums(mode1_raw),
        "mode1_carry": carries(mode1_raw),
        "switch_sum_out": sums(switch_raw),
        "switch_carry": carries(switch_raw),
    }


def verify_golden_vectors(text: str) -> tuple[bool, list[str]]:
    parsed = parse_golden_vectors(text)
    expected = compute_expected_vectors(parsed["input_pairs"])  # type: ignore[arg-type]
    messages: list[str] = []

    for key in (
        "products",
        "mode0_raw",
        "mode0_sum_out",
        "mode0_carry",
        "mode1_raw",
        "mode1_sum_out",
        "mode1_carry",
        "switch_sum_out",
        "switch_carry",
    ):
        if parsed[key] != expected[key]:
            messages.append(
                f"Mismatch in {LABELS[key]}: expected {expected[key]}, got {parsed[key]}"
            )

    if messages:
        return False, messages
    return True, ["Golden vectors verified."]


def verify_simulation_log(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return True, f"Simulation log not found at {path}; skipping log check."

    content = path.read_text(encoding="utf-8", errors="ignore")
    if "Simulation Passed" not in content:
        return False, f"Simulation log does not contain 'Simulation Passed': {path}"
    return True, f"Simulation log contains 'Simulation Passed': {path}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate docs/golden_vectors.md.")
    parser.add_argument(
        "--golden-file",
        default="docs/golden_vectors.md",
        help="Path to the golden vector markdown document.",
    )
    parser.add_argument(
        "--sim-log",
        default=os.getenv("SIM_LOG_PATH", "sim/run_iverilog.log"),
        help="Optional simulation log path. Defaults to SIM_LOG_PATH or sim/run_iverilog.log.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    golden_text = Path(args.golden_file).read_text(encoding="utf-8")

    ok, messages = verify_golden_vectors(golden_text)
    for message in messages:
        print(message)
    if not ok:
        return 1

    sim_ok, sim_message = verify_simulation_log(Path(args.sim_log))
    print(sim_message)
    return 0 if sim_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
