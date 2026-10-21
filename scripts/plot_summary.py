#!/usr/bin/env python3
"""Plot the per-model benchmark data in a combined summary JSON file."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def safe_filename(value: str) -> str:
    """Return a model name that is safe to use as part of a filename."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "model"


def benchmark_label(benchmark: dict[str, Any]) -> str:
    context = benchmark.get("context_size", 0)
    prompt = benchmark.get("prompt_size", "?")
    response = benchmark.get("response_size", "?")
    concurrency = benchmark.get("concurrency", 1)
    phase = "ctx-pp" if benchmark.get("is_context_prefill_phase") else "pp/tg"
    return f"p{prompt}/r{response} d{context} c{concurrency} {phase}"


def metric_points(
    benchmarks: list[dict[str, Any]], metric: str
) -> tuple[list[int], list[float], list[float]]:
    positions: list[int] = []
    means: list[float] = []
    stds: list[float] = []
    for position, benchmark in enumerate(benchmarks):
        value = benchmark.get(metric)
        if not isinstance(value, dict) or not isinstance(value.get("mean"), (int, float)):
            continue
        positions.append(position)
        means.append(float(value["mean"]))
        stds.append(float(value.get("std", 0)))
    return positions, means, stds


def plot_model(model: str, benchmarks: list[dict[str, Any]], output_dir: Path) -> int:
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        if exc.name != "matplotlib":
            raise
        raise RuntimeError(
            "matplotlib is required for plotting; install the project dependencies "
            "with `python -m pip install -e .`"
        ) from exc

    prefix = output_dir / safe_filename(model)
    generated = 0

    throughput_metrics = [
        ("pp_throughput", "Prompt processing", "tab:blue"),
        ("tg_throughput", "Token generation", "tab:orange"),
        ("peak_throughput", "Peak", "tab:green"),
    ]
    fig, ax = plt.subplots(figsize=(max(11, len(benchmarks) * 0.55), 6))
    plotted = False
    for metric, label, color in throughput_metrics:
        positions, means, stds = metric_points(benchmarks, metric)
        if not means:
            continue
        plotted = True
        ax.errorbar(positions, means, yerr=stds, marker="o", linewidth=1.5, capsize=3, label=label, color=color)
    if plotted:
        labels = [benchmark_label(b) for b in benchmarks]
        ax.set_xticks(range(len(labels)), labels, rotation=70, ha="right", fontsize=8)
        ax.set_ylabel("Throughput (tokens/s)")
        ax.set_title(f"{model}: throughput")
        ax.grid(axis="y", alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(prefix.with_name(prefix.name + "-throughput.png"), dpi=160)
        generated += 1
    plt.close(fig)

    latency_metrics = [
        ("ttfr", "TTFR", "tab:red"),
        ("est_ppt", "Estimated prompt processing", "tab:purple"),
        ("e2e_ttft", "End-to-end TTFT", "tab:brown"),
    ]
    fig, ax = plt.subplots(figsize=(max(11, len(benchmarks) * 0.55), 6))
    plotted = False
    for metric, label, color in latency_metrics:
        positions, means, stds = metric_points(benchmarks, metric)
        if not means:
            continue
        plotted = True
        ax.errorbar(positions, means, yerr=stds, marker="o", linewidth=1.5, capsize=3, label=label, color=color)
    if plotted:
        labels = [benchmark_label(b) for b in benchmarks]
        ax.set_xticks(range(len(labels)), labels, rotation=70, ha="right", fontsize=8)
        ax.set_ylabel("Latency (ms)")
        ax.set_title(f"{model}: latency")
        ax.grid(axis="y", alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(prefix.with_name(prefix.name + "-latency.png"), dpi=160)
        generated += 1
    plt.close(fig)
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "summary", nargs="?", type=Path, default=REPOSITORY_ROOT / "results/summary.json"
    )
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=REPOSITORY_ROOT / "results/plots"
    )
    args = parser.parse_args()

    try:
        data = json.loads(args.summary.read_text())
    except FileNotFoundError:
        parser.error(f"summary file not found: {args.summary}")
    except json.JSONDecodeError as exc:
        parser.error(f"invalid JSON in {args.summary}: {exc}")

    models = data.get("models", [])
    if not isinstance(models, list):
        parser.error("summary JSON must contain a models list")

    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        generated = 0
        for entry in models:
            if entry.get("status") != "ok":
                continue
            report = entry.get("report") or {}
            benchmarks = report.get("benchmarks") or []
            if benchmarks:
                generated += plot_model(entry.get("model", "model"), benchmarks, args.output_dir)
    except RuntimeError as exc:
        parser.error(str(exc))

    print(f"Generated {generated} graph(s) in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
