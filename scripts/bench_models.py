#!/usr/bin/env python3
"""Discover models on an OpenAI-compatible endpoint, select targets, and run
llama-benchy benchmarks on all selected models in parallel, then produce a
combined summary report.

Pseudocode:

    parse CLI args (+ unknown trailing args are passed through to llama-benchy)

    models     = GET {base-url}/models                  # with API key, read max_input_tokens
    candidates = models minus embedding/reranker        # generic, name-based filter

    selected   = --models <list> | --all | interactive numbered picker ('a', '1,3,5-8', 'q')
    profile    = --profile | interactive menu           # smoke | sweep | throughput | full

    apply CLI overrides: --pp --tg --depth --concurrency
    for each selected model:
        depths = [d for d in profile.depths
                  if d + pp + tg + margin <= (max_input_tokens or unknown-cap)]

    print plan (models, resolved depths, contamination warning)
    if --dry-run: print each resolved command and exit

    launch one llama-benchy subprocess PER MODEL, all at the same time:
        llama-benchy --base-url ... --model <m> --latency-mode generation
                     --runs N --warmup-runs M --format json
                     --save-result <out>/<model>.json
                     [+ profile flags] [+ passthrough extras]
                     > <out>/logs/<model>.log 2>&1

    monitor loop (Ctrl+C terminates all children, then still summarizes):
        refresh per-model status/elapsed; --stream <model> tails that log live

    for each finished job:
        exit==0 and valid JSON report -> ok, else failed (record exit code + log tail)

    write combined summary: one pp + one tg row per report entry
        -> <out>/summary.md + <out>/summary.json; print failures with log tails
    exit 0 if all models ok else 1

Profiles (all use --latency-mode generation and --runs/--warmup-runs as given):

    smoke       Single test shape at depth 0: pp2048 / tg32.
                Quick sanity check that a model is reachable, coherent and
                responding; yields baseline single-context pp/tg numbers.

    sweep       llama-bench style context sweep: pp2048 / tg32 measured at
                depths 0, 4K, 8K, 16K, 32K. Shows how prefill and decode
                degrade as the prompt context grows. Depths exceeding a
                model's context limit are auto-dropped (see --margin,
                --unknown-cap).

    throughput  Fixed-output-length decode benchmark: pp2048 / tg256 with
                --exact-tg (min_tokens + ignore_eos) at depth 0. For
                comparing sustained generation speed across models with a
                guaranteed identical output length.

    full        sweep plus load scaling: same depth sweep but repeated at
                --concurrency 1 and 4, reporting total vs per-request
                throughput to reveal how the server saturates. Longest
                runtime.

Examples:
  python3 scripts/bench_models.py --base-url http://localhost:8000/v1
  python3 scripts/bench_models.py --base-url http://localhost:8000/v1 --all --profile sweep
  python3 scripts/bench_models.py --base-url http://localhost:8000/v1 --models model-a,model-b --profile smoke
  python3 scripts/bench_models.py --base-url http://localhost:8000/v1 --all --profile sweep --dry-run

Results:  <output-dir>/<model>.json + <output-dir>/summary.{md,json}
Logs:     <output-dir>/logs/<model>.log
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

EXCLUDE_RE = re.compile(r"embedding|reranker", re.I)
POLL_INTERVAL = 2.0

PROFILES = {
    "smoke": dict(
        pp=[2048], tg=[32], depth=[0], concurrency=[1], exact_tg=False,
        desc="pp2048/tg32 @ depth 0 (quick sanity check)",
    ),
    "sweep": dict(
        pp=[2048], tg=[32], depth=[0, 4096, 8192, 16384, 32768], concurrency=[1], exact_tg=False,
        desc="pp2048/tg32 across depths (llama-bench style)",
    ),
    "throughput": dict(
        pp=[2048], tg=[256], depth=[0], concurrency=[1], exact_tg=True,
        desc="pp2048/tg256 fixed output length (--exact-tg)",
    ),
    "full": dict(
        pp=[2048], tg=[32], depth=[0, 4096, 8192, 16384, 32768], concurrency=[1, 4], exact_tg=False,
        desc="sweep depths + concurrency 1,4 (load scaling)",
    ),
}


def parse_args():
    default_key = (
        os.environ.get("LLAMA_BENCHY_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or "EMPTY"
    )
    p = argparse.ArgumentParser(
        description="Run llama-benchy against multiple models in parallel and build a combined summary.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--base-url", required=True, help="OpenAI-compatible endpoint URL (e.g. http://localhost:8000/v1)")
    p.add_argument("--api-key", default=default_key, help="API key (env: LLAMA_BENCHY_API_KEY or OPENAI_API_KEY)")
    p.add_argument("--profile", choices=sorted(PROFILES), help="Benchmark profile (interactive menu if omitted)")
    p.add_argument("--models", help="Comma-separated model ids to benchmark (skips interactive selection)")
    p.add_argument("--all", action="store_true", help="Benchmark every non-embedding/reranker model")
    p.add_argument("--output-dir", default="results", help="Directory for reports, logs and summary")
    p.add_argument("--runs", type=int, default=3, help="Measurement runs per test shape")
    p.add_argument("--warmup-runs", type=int, default=1, help="Discarded warmup runs per test shape")
    p.add_argument("--pp", type=int, nargs="+", help="Override profile prompt token counts")
    p.add_argument("--tg", type=int, nargs="+", help="Override profile generation token counts")
    p.add_argument("--depth", type=int, nargs="+", help="Override profile context depths (still auto-capped)")
    p.add_argument("--concurrency", type=int, nargs="+", help="Override profile concurrency levels")
    p.add_argument("--enable-prefix-caching", action="store_true", help="Add --enable-prefix-caching when depth > 0 is present")
    p.add_argument("--unknown-cap", type=int, default=32768, help="Context cap for models that do not report max_input_tokens")
    p.add_argument("--margin", type=int, default=512, help="Token safety margin (depth+pp+tg+margin <= context limit)")
    p.add_argument("--llama-benchy", dest="benchy", help="Path to llama-benchy executable (default: auto-detect)")
    p.add_argument("--stream", metavar="MODEL", help="Tail one model's log output live while running")
    p.add_argument("--dry-run", action="store_true", help="Show model list and resolved commands, then exit")
    p.add_argument("--yes", action="store_true", help="Skip the launch confirmation prompt")
    args, extras = p.parse_known_args()
    return args, extras


def parse_compact_models(text):
    models = []
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return models
    fields = []
    header = lines[0]
    if "{" in header and "}" in header:
        spec = header[header.index("{") + 1:header.index("}")]
        fields = [f.split(":")[0].strip() for f in spec.split(",")]
        rows = lines[1:]
    else:
        rows = lines
    for row in rows:
        parts = row.split(",")
        rec = dict(zip(fields, parts)) if fields and len(parts) == len(fields) else {}
        mid = (rec.get("id") or (parts[1] if len(parts) > 1 else "")).strip()
        if not mid:
            continue
        mi = (rec.get("max_input_tokens") or (parts[5] if len(parts) > 5 else "")).strip()
        max_in = int(mi) if mi.isdigit() else None
        models.append({"id": mid, "max_input_tokens": max_in})
    return models


def fetch_models(base_url, api_key):
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        sys.exit(f"error: /models returned HTTP {e.code}: {body}")
    except Exception as e:
        sys.exit(f"error: failed to fetch {url}: {e}")
    data = payload.get("data", [])
    models = []
    if isinstance(data, list):
        for m in data:
            if isinstance(m, dict) and m.get("id"):
                models.append({"id": m["id"], "max_input_tokens": m.get("max_input_tokens")})
    elif isinstance(data, str):
        models = parse_compact_models(data)
    if not models:
        sys.exit("error: no models returned by the endpoint")
    return models


def parse_selection(spec, n):
    selected = set()
    for tok in re.split(r"[,\s]+", spec.strip()):
        if not tok:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", tok)
        if not m:
            raise ValueError(f"invalid selection token: {tok!r}")
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if a < 1 or b > n or a > b:
            raise ValueError(f"index out of range 1..{n}: {tok}")
        selected.update(range(a, b + 1))
    if not selected:
        raise ValueError("empty selection")
    return sorted(selected)


def select_models_interactive(models):
    print("\nAvailable models:")
    for i, m in enumerate(models, 1):
        cap = m["max_input_tokens"] if m["max_input_tokens"] is not None else "?"
        print(f"  [{i:2d}] {m['id']:<45} max_input: {cap}")
    while True:
        try:
            spec = input("\nSelect models ('a'=all, e.g. '1,3,5-8', 'q'=quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit("\naborted")
        if spec.lower() in ("q", "quit", "exit"):
            sys.exit("aborted")
        if spec.lower() in ("a", "all"):
            return list(range(1, len(models) + 1))
        try:
            return parse_selection(spec, len(models))
        except ValueError as e:
            print(f"  {e}; try again")


def choose_profile_interactive():
    print("\nBenchmark profiles:")
    names = sorted(PROFILES)
    for i, name in enumerate(names, 1):
        print(f"  [{i}] {name:<12} {PROFILES[name]['desc']}")
    while True:
        try:
            spec = input(f"\nSelect profile [1-{len(names)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit("\naborted")
        if spec.isdigit() and 1 <= int(spec) <= len(names):
            return names[int(spec) - 1]
        if spec in PROFILES:
            return spec
        print("  invalid choice; try again")


def ask_prefix_caching():
    try:
        spec = input("Enable prefix-caching measurement (--enable-prefix-caching)? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\naborted")
    return spec in ("y", "yes")


def resolve_depths(depths, pp, tg, max_input, unknown_cap, margin):
    limit = max_input if max_input is not None else unknown_cap
    kept = sorted({d for d in depths if d + pp + tg + margin <= limit})
    return kept or [0]


def find_benchy(explicit):
    if explicit:
        return [explicit]
    repo_venv = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "llama-benchy"
    if repo_venv.exists():
        return [str(repo_venv)]
    which = shutil.which("llama-benchy")
    if which:
        return [which]
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "llama-benchy"]
    sys.exit("error: llama-benchy executable not found (tried .venv, PATH, uv)")


def safe_name(model_id, taken):
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", model_id).strip("_") or "model"
    name, i = base, 1
    while name in taken:
        i += 1
        name = f"{base}_{i}"
    taken.add(name)
    return name


def build_command(benchy, args, extras, model, prof, depths, json_path):
    cmd = list(benchy) + [
        "--base-url", args.base_url,
        "--api-key", args.api_key,
        "--model", model,
        "--pp", *[str(v) for v in prof["pp"]],
        "--tg", *[str(v) for v in prof["tg"]],
        "--depth", *[str(v) for v in depths],
        "--concurrency", *[str(v) for v in prof["concurrency"]],
        "--latency-mode", "generation",
        "--runs", str(args.runs),
        "--warmup-runs", str(args.warmup_runs),
        "--format", "json",
        "--save-result", str(json_path),
    ]
    if prof["exact_tg"]:
        cmd.append("--exact-tg")
    if args.enable_prefix_caching and any(d > 0 for d in depths):
        cmd.append("--enable-prefix-caching")
    return cmd + list(extras)


def fmt_elapsed(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def print_status_block(jobs, first):
    header = f"  {'Model':<40} {'Status':<9} {'Elapsed':>9}"
    lines = [header] + [
        f"  {j['model']:<40} {j['status']:<9} {fmt_elapsed((j['end'] or time.time()) - j['start']):>9}"
        for j in jobs
    ]
    if first:
        print("\n".join(lines), flush=True)
        return
    sys.stdout.write(f"\x1b[{len(lines)}A\r\x1b[J")
    print("\n".join(lines), flush=True)


def drain_log(job):
    if job.get("read_fh") is None:
        try:
            job["read_fh"] = open(job["log_path"], "r")
        except OSError:
            return
    data = job["read_fh"].read()
    if data:
        sys.stdout.write(data)
        sys.stdout.flush()


def run_jobs(jobs, stream_model):
    streamed = next((j for j in jobs if j["model"] == stream_model), None)
    tty = sys.stdout.isatty()
    first = True
    last_status = {j["model"]: j["status"] for j in jobs}
    try:
        while any(j["proc"].poll() is None for j in jobs):
            time.sleep(POLL_INTERVAL)
            now = time.time()
            for j in jobs:
                if j["proc"].poll() is None:
                    j["status"] = "RUNNING"
                elif j["end"] is None:
                    j["end"] = now
                    j["status"] = "DONE" if j["proc"].returncode == 0 else "FAILED"
                    last_status[j["model"]] = None
            if streamed is not None:
                drain_log(streamed)
                for j in jobs:
                    if last_status[j["model"]] is None:
                        last_status[j["model"]] = j["status"]
                        print(f"\n[bench] {j['model']}: {j['status']} ({fmt_elapsed(j['end'] - j['start'])})", flush=True)
            elif tty:
                print_status_block(jobs, first)
                first = False
            else:
                for j in jobs:
                    if last_status[j["model"]] is None:
                        last_status[j["model"]] = j["status"]
                        print(f"[bench] {j['model']}: {j['status']} ({fmt_elapsed(j['end'] - j['start'])})", flush=True)
    except KeyboardInterrupt:
        print("\n\n[bench] Ctrl+C received: terminating benchmark processes...", file=sys.stderr, flush=True)
        for j in jobs:
            if j["proc"].poll() is None:
                j["status"] = "KILLED"
                j["end"] = time.time()
                j["proc"].terminate()
        deadline = time.time() + 5
        for j in jobs:
            if j["status"] == "KILLED":
                try:
                    j["proc"].wait(timeout=max(0.1, deadline - time.time()))
                except subprocess.TimeoutExpired:
                    j["proc"].kill()
        if streamed is not None:
            drain_log(streamed)
    if streamed is not None:
        drain_log(streamed)
        print()


def load_report(path):
    try:
        with open(path, "r") as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(report, dict) or "benchmarks" not in report:
        return None
    return report


def log_tail(path, n=10):
    try:
        with open(path, "r", errors="replace") as f:
            lines = [ln.rstrip() for ln in f if ln.strip()]
        return lines[-n:]
    except OSError:
        return []


def fmt_stat(d):
    if not isinstance(d, dict) or d.get("mean") is None:
        return ""
    std = d.get("std") or 0.0
    return f"{d['mean']:.2f} ± {std:.2f}"


def test_label(entry, phase):
    cs = entry.get("context_size") or 0
    cc = entry.get("concurrency") or 1
    size = entry.get("prompt_size") if phase == "pp" else entry.get("response_size")
    label = f"{'ctx_' if entry.get('is_context_prefill_phase') else ''}{phase}{size}"
    if cs:
        label += f" @ d{cs}"
    if cc > 1:
        label += f" (c{cc})"
    return label


def collect_rows(report):
    rows = []
    for e in report.get("benchmarks", []):
        cc = e.get("concurrency") or 1
        pp_label = test_label(e, "pp")
        tg_label = test_label(e, "tg")
        rows.append({
            "test": pp_label, "t/s": fmt_stat(e.get("pp_throughput")),
            "t/s (req)": fmt_stat(e.get("pp_req_throughput")) if cc > 1 else "",
            "peak t/s": "", "ttfr (ms)": fmt_stat(e.get("ttfr")),
            "est_ppt (ms)": fmt_stat(e.get("est_ppt")), "e2e_ttft (ms)": fmt_stat(e.get("e2e_ttft")),
        })
        rows.append({
            "test": tg_label, "t/s": fmt_stat(e.get("tg_throughput")),
            "t/s (req)": fmt_stat(e.get("tg_req_throughput")) if cc > 1 else "",
            "peak t/s": fmt_stat(e.get("peak_throughput")), "ttfr (ms)": "",
            "est_ppt (ms)": "", "e2e_ttft (ms)": "",
        })
    return rows


def write_summary(out_dir, args, profile, jobs, results):
    md_cols = ["model", "test", "t/s", "peak t/s", "ttfr (ms)", "est_ppt (ms)", "e2e_ttft (ms)"]
    any_cc = any((r.get("concurrency") or 1) > 1 for res in results if res["report"] for r in res["report"].get("benchmarks", []))
    if any_cc:
        md_cols.insert(3, "t/s (req)")
    md_lines = [
        "# llama-benchy combined summary",
        "",
        f"- endpoint: `{args.base_url}`",
        f"- profile: `{profile}` ({PROFILES[profile]['desc']})",
        f"- generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- runs: {args.runs} (+{args.warmup_runs} warmup) | latency-mode: generation",
        "",
        "| " + " | ".join(md_cols) + " |",
        "|" + "|".join("---:" if c != "model" and c != "test" else "---" for c in md_cols) + "|",
    ]
    for res in results:
        if res["status"] != "ok":
            continue
        for row in collect_rows(res["report"]):
            cells = [res["model"], row["test"], row["t/s"]]
            if any_cc:
                cells.append(row["t/s (req)"])
            cells += [row["peak t/s"], row["ttfr (ms)"], row["est_ppt (ms)"], row["e2e_ttft (ms)"]]
            md_lines.append("| " + " | ".join(cells) + " |")
    md_lines += ["", "## Status", ""]
    for res in results:
        mark = "OK " if res["status"] == "ok" else "ERR"
        detail = f" — {res['error']}" if res.get("error") else ""
        md_lines.append(f"- [{mark}] {res['model']} ({res['status']}, exit {res['exit_code']}, {fmt_elapsed(res['elapsed'])}){detail}")
    for res in results:
        if res["status"] == "ok":
            continue
        md_lines += ["", f"### {res['model']} log tail", "", "```", *log_tail(res["log_path"]), "```"]
    md_path = out_dir / "summary.md"
    md_path.write_text("\n".join(md_lines) + "\n")

    summary_json = {
        "endpoint": args.base_url,
        "profile": profile,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "models": [
            {
                "model": res["model"],
                "status": res["status"],
                "exit_code": res["exit_code"],
                "elapsed_s": int(res["elapsed"]),
                "report": res["report"],
                "error": res.get("error"),
            }
            for res in results
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary_json, indent=2) + "\n")
    return md_path


def main():
    args, extras = parse_args()
    models = fetch_models(args.base_url, args.api_key)
    excluded = [m["id"] for m in models if EXCLUDE_RE.search(m["id"])]
    candidates = [m for m in models if not EXCLUDE_RE.search(m["id"])]

    print(f"Endpoint: {args.base_url}")
    print(f"Discovered {len(models)} models ({len(excluded)} excluded as embedding/reranker: {', '.join(excluded) or '-'})")
    if not candidates:
        sys.exit("error: no benchmarkable models after filtering")

    if args.models:
        wanted = [w.strip() for w in args.models.split(",") if w.strip()]
        by_lower = {m["id"].lower(): m["id"] for m in candidates}
        missing = [w for w in wanted if w.lower() not in by_lower]
        if missing:
            sys.exit(f"error: unknown/unavailable models: {', '.join(missing)}\navailable: {', '.join(m['id'] for m in candidates)}")
        selected = [by_lower[w.lower()] for w in wanted]
    elif args.all:
        selected = [m["id"] for m in candidates]
    elif sys.stdin.isatty():
        picks = select_models_interactive(candidates)
        selected = [candidates[i - 1]["id"] for i in picks]
    else:
        sys.exit("error: non-interactive session requires --models or --all")

    profile = args.profile or (choose_profile_interactive() if sys.stdin.isatty() else "sweep")
    prof = dict(PROFILES[profile])
    if args.pp:
        prof["pp"] = args.pp
    if args.tg:
        prof["tg"] = args.tg
    if args.depth:
        prof["depth"] = args.depth
    if args.concurrency:
        prof["concurrency"] = args.concurrency
    if args.profile is None and profile in ("sweep", "full") and not args.enable_prefix_caching:
        args.enable_prefix_caching = ask_prefix_caching()
    if args.enable_prefix_caching and all(d == 0 for d in prof["depth"]):
        print("note: --enable-prefix-caching has no effect without depth > 0; ignoring")
        args.enable_prefix_caching = False

    pp_val = prof["pp"][0]
    tg_val = prof["tg"][0]
    cap_info = []
    for m in candidates:
        if m["id"] in selected:
            depths = resolve_depths(prof["depth"], pp_val, tg_val, m["max_input_tokens"], args.unknown_cap, args.margin)
            dropped = [d for d in prof["depth"] if d not in depths]
            cap_info.append((m["id"], m["max_input_tokens"], depths, dropped))

    out_dir = Path(args.output_dir)
    logs_dir = out_dir / "logs"
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nProfile: {profile} — {prof['desc']}")
    print(f"Runs: {args.runs} (+{args.warmup_runs} warmup) | latency-mode: generation | prefix-caching: {'on' if args.enable_prefix_caching else 'off'}")
    print(f"Depth capping: margin={args.margin}, unknown-cap={args.unknown_cap}")
    print(f"\nModels ({len(selected)}) — will run in TRUE PARALLEL on one shared server:")
    print("  (results may be contaminated by GPU contention; measurements are not isolated)")
    for name, cap, depths, dropped in cap_info:
        cap_s = cap if cap is not None else f"? (capped at {args.unknown_cap})"
        drop_s = f"  [dropped: {', '.join(map(str, dropped))}]" if dropped else ""
        print(f"  - {name:<45} max_input: {cap_s}\n      depths: {' '.join(map(str, depths))}{drop_s}")
    print(f"\nOutput: {out_dir}/<model>.json | Logs: {logs_dir}/<model>.log | Summary: {out_dir}/summary.md")

    if extras:
        print(f"Passthrough extras: {' '.join(extras)}")

    benchy = find_benchy(args.benchy)
    taken = set()
    plan = []
    for name, cap, depths, dropped in cap_info:
        sname = safe_name(name, taken)
        json_path = out_dir / f"{sname}.json"
        log_path = logs_dir / f"{sname}.log"
        cmd = build_command(benchy, args, extras, name, prof, depths, json_path)
        plan.append({"model": name, "safe": sname, "cmd": cmd, "json_path": json_path, "log_path": log_path})

    if args.dry_run:
        print("\nDry run — resolved commands:")
        for p in plan:
            print(f"\n[{p['model']}]\n  {' '.join(p['cmd'])}")
        return

    if not args.yes and sys.stdin.isatty():
        try:
            spec = input(f"\nLaunch {len(plan)} benchmarks in parallel? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit("\naborted")
        if spec in ("n", "no"):
            sys.exit("aborted")

    print(f"\nLaunching {len(plan)} benchmarks in parallel (binary: {' '.join(benchy)})...\n")
    jobs = []
    for p in plan:
        fh = open(p["log_path"], "w")
        proc = subprocess.Popen(p["cmd"], stdout=fh, stderr=subprocess.STDOUT)
        jobs.append({
            "model": p["model"], "proc": proc, "log_path": str(p["log_path"]),
            "json_path": str(p["json_path"]), "start": time.time(), "end": None,
            "status": "RUNNING", "log_fh": fh, "read_fh": None,
        })

    stream_model = None
    if args.stream:
        matches = [j for j in jobs if j["model"].lower() == args.stream.lower()]
        if not matches:
            print(f"warning: --stream {args.stream}: no such model selected; streaming disabled")
        else:
            stream_model = matches[0]["model"]

    run_jobs(jobs, stream_model)
    for j in jobs:
        try:
            j["log_fh"].close()
        except OSError:
            pass

    results = []
    for j in jobs:
        report = load_report(j["json_path"])
        rc = j["proc"].returncode
        if rc == 0 and report is not None:
            status, error = "ok", None
        else:
            status = "failed" if j["status"] != "KILLED" else "killed"
            reasons = []
            if rc != 0:
                reasons.append(f"exit code {rc}")
            if report is None:
                reasons.append("missing or invalid JSON report")
            error = "; ".join(reasons) or "unknown error"
        results.append({
            "model": j["model"], "status": status, "exit_code": rc,
            "elapsed": (j["end"] or time.time()) - j["start"],
            "report": report, "error": error, "log_path": j["log_path"],
            "json_path": j["json_path"],
        })

    md_path = write_summary(out_dir, args, profile, jobs, results)

    ok = [r for r in results if r["status"] == "ok"]
    bad = [r for r in results if r["status"] != "ok"]
    print(f"\n{'=' * 70}\nCompleted: {len(ok)} succeeded, {len(bad)} failed/killed of {len(results)}")
    for r in bad:
        print(f"  FAILED/KILLED: {r['model']} ({r['error']})")
    print(f"\nSummary:   {md_path}")
    print(f"Machine:   {out_dir / 'summary.json'}")
    for r in ok:
        print(f"  report:   {r['model']} -> {r['json_path']}")
    if bad:
        print("\nFailure details (last log lines):")
        for r in bad:
            print(f"\n--- {r['model']} ---")
            for line in log_tail(r["log_path"], 5):
                print(f"  {line}")

    sys.exit(0 if not bad else 1)


if __name__ == "__main__":
    main()
