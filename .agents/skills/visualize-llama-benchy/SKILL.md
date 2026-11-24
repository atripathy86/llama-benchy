---
name: visualize-llama-benchy
description: Visualize saved llama-benchy JSON benchmark reports or multi-model summaries as throughput and latency graphs without rerunning benchmarks.
---

# Visualize llama-benchy

Help the user visualize completed llama-benchy experiments. Use existing data;
do not contact an endpoint or rerun a benchmark. Respect a request for commands
only: do not install dependencies or generate files in that case.

## Find the results and choose an output

1. Use the input path supplied by the user or the report path from the current
   benchmark conversation. Otherwise, inspect likely `results` directories for
   JSON files and ask the user to select among plausible experiments. Do not
   assume the latest file is the desired experiment.
2. Read and validate the JSON. A single-model report has a `model` and a
   `benchmarks` list; a multi-model runner's `summary.json` has a `models` list
   containing status and embedded reports. Report failed or killed models and
   empty or missing benchmark data; only `ok` models are plotted from
   summaries. Check endpoint/time provenance: single-model JSON should contain
   `base_url` and `timestamp`; runner `summary.json` should contain `endpoint`
   and `generated_at`. Report legacy files that lack these fields instead of
   guessing.
   The plotting script does not read CSV, Markdown, progress JSONL or raw
   console output. Ask for the saved JSON rather than fabricating data.
3. Use a fresh, unique output directory beside the selected result, such as
   `plots-<UTCtimestamp>`, and verify it does not exist. The script can overwrite
   PNGs in an existing directory. If multiple reports are selected, use a
   separate fresh output directory for each. For a summary, check whether
   model names become identical after replacing characters other than ASCII
   letters, digits, `.`, `_` or `-` with `_` and stripping leading/trailing
   dots and underscores; the script uses `model` for an empty name. On Windows,
   also compare filenames case-insensitively. If names collide, use the
   individual reports and separate output directories rather than allowing
   graphs to overwrite each other. Preserve the source report's explicit
   `model-endpoint-test-type-UTCtimestamp` identity in visualization labels and
   output directory naming when available. Do not load `.env` or contact an
   endpoint for visualization; endpoint provenance comes from the saved JSON.

## Generate graphs

The script lives in a llama-benchy checkout at `scripts/plot_summary.py`; it is
not included with this skill when installed separately. Locate a checkout
containing a version of that script which supports single-model reports, or ask
the user for one. Do not silently clone or install anything. Use `uv` to run
the script with the checkout's project environment. It requires Python 3.10+
and matplotlib, a project dependency. Check that `uv` is available first;
request permission before installing `uv`, Python, dependencies, or creating
an environment.

From the checkout root, use syntax appropriate to the user's operating system
and shell; do not assume Windows. Either command works with a single report or
a combined summary. Replace the example paths with the selected JSON file and
a fresh output directory.

Linux or macOS (shell):

```sh
uv run python scripts/plot_summary.py "results/my-report.json" --output-dir "results/my-plots"
```

Windows (PowerShell):

```powershell
uv run python scripts\plot_summary.py "results\my-report.json" --output-dir "results\my-plots"
```

Use shell-appropriate quoting, including for paths with spaces, and absolute
input and output paths if the files are outside the checkout.
Do not rely on the script's default `results/summary.json`: the benchmark skill
saves single-model reports and multi-model runs in distinct locations. If
`uv run` would install dependencies, ask permission first.

Show the actual command before execution. Check its exit status and confirm the
generated PNG files exist; `Generated 0 graph(s)` is not a successful
visualization. Investigate missing data or errors and report them explicitly.
For commands-only requests, provide a shell-appropriate command and expected
output directory without claiming files exist.

## Explain and report

The script creates up to two PNGs per model: throughput (prompt processing,
token generation, and peak, in tokens/s) and latency (TTFR, estimated prompt
processing time, and end-to-end TTFT, in ms). Points are benchmark shapes
(prompt, response, context depth, concurrency, and prefill phase), and error
bars represent standard deviations. Missing metrics are omitted, not zero.
Throughput shown is total, not per-request; the script does not graph time
series or overlay models. Do not claim a cross-model overlay was generated.
When comparing experiments, highlight differences in shape, latency mode,
concurrency, prefix caching, tokenizer accuracy, and possible parallel-model
contention rather than treating unlike runs as equivalent.

Link the input and each generated graph when supported, summarize what was
plotted and any skipped models or caveats. The repository's Jupyter notebook
is a separate example that runs a benchmark before plotting; it is not a
saved-report viewer and may install packages or contact an endpoint.
