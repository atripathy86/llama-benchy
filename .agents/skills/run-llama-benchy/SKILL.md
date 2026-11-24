---
name: run-llama-benchy
description: Guide, construct commands for, or run llama-benchy benchmarks against OpenAI-compatible endpoints, including selecting and comparing multiple models.
---

# Run llama-benchy

Help the user configure a benchmark, then either run it or provide ready-to-run
commands, according to their preference. Find this skill's installed directory
for its bundled discovery script. The skill can set up llama-benchy with `uv`
when necessary. Do not install software or start a benchmark if the user only
wants commands.

## Keep the user informed

At the start, give a short numbered outline of the steps you plan to take,
tailored to the request. As you work, briefly state what you are doing and what
comes next at each step or material change. Before a download, install, or
benchmark, say what will happen and wait for consent when required below. End
with what completed, any issues, and the next action if one remains. Do not
repeat the full plan in every update or narrate routine tool calls.

Typical run:

1. Check the endpoint and discover available models.
2. Confirm model selection and benchmark settings.
3. Check `uv` and tokenizer/corpus requirements; set up llama-benchy if needed.
4. Run the benchmark, or provide commands if requested.
5. Verify the result and summarize metrics and caveats.

## Gather requirements

Before asking the user for endpoint details, inspect the current checkout for
`.env` without printing it. If it exists, interpret the keys described in
`.env.example`; otherwise ask the user to save or attach a `.env` in that exact
simple `KEY=value` format. Never ask them to paste a secret into chat, and never
print or echo secret values:

```dotenv
API_BASE=https://inference.example
API_KEY=
LLAMA_BENCHY_MODELS=
LLAMA_BENCHY_PROFILE=
```

`API_BASE` is the server root or OpenAI base. When it is supplied through the
environment, remove a trailing slash and normalize `/v1/models` or
`/v1/chat/completions` to `/v1`; otherwise append `/v1` when it is absent.
`API_KEY` may be empty for an unauthenticated endpoint. `LLAMA_BENCHY_MODELS`
is an optional comma-separated list for the multi-model runner.
`LLAMA_BENCHY_PROFILE` is also optional and accepts comma-separated profile
names; its presence means only those profiles should run, sequentially. The
explicit `--profile` option overrides it. Do not put a discovered model list,
token, or other secret into chat.

1. Do not ask open-endedly what benchmark the user wants. Use structured
   selections with recommendations and defaults. Offer free-text input only
   for exceptional values. Default to **Smoke test** if the user asks to run
   a benchmark without specifying its scope. Ask for the endpoint only when
   none is provided, and retain settings the user has already specified.
2. Use an OpenAI-compatible API base URL, normally ending in `/v1`, without a
   trailing slash. For a bare server URL, append `/v1`. If given `/v1/models`
   or `/v1/chat/completions`, remove that suffix to obtain the base. Do not
   silently add `/v1` to an explicitly supplied custom API base path. The
   llama-benchy single-model CLI and `scripts/bench_models.py` load `.env`
   automatically; `--env-file <path>` selects another file. Explicit CLI
   arguments override `.env`, while existing shell environment values override
   file values. The client appends `/models` and `/chat/completions` itself, so
   use the normalized OpenAI base rather than a complete operation URL.
3. If an endpoint is given, query it live before model selection using the
   cross-platform Python script in this skill. Run it with `uv run` from the
   llama-benchy checkout root so discovery and benchmarking use the same
   project environment:

   ```text
   uv run python .agents/skills/run-llama-benchy/scripts/discover_models.py --base-url "<endpoint>" --format json
   ```

   On Windows PowerShell, use
   `uv run python .agents\skills\run-llama-benchy\scripts\discover_models.py --base-url "<endpoint>" --format json`.
   When installed elsewhere with `npx skills add`, use the installed skill's
   `scripts/discover_models.py` path instead of assuming it is under the
   checkout's `.agents/skills/` directory, but still run it with
   `uv run --project <llama-benchy-checkout> python <skill-script-path>` so it
   uses the checkout's environment. If no checkout exists yet, set it up before
   endpoint discovery.
   The script accepts a bare server URL, `/v1`, `/v1/models`,
   `/v1/chat/completions`, or a custom API base path. It prints an array of
   model objects containing `id` and, when available, `root` and
   `max_input_tokens`. If multiple models are returned, show them in a
   multi-select form, including **All models** and **Other** for IDs not listed;
   never assume the first model. For the multi-select field, encode each option
   with `items.anyOf` entries containing `const` and `title`, and provide a
   separate free-text field for an **Other** model ID. Explain that a listed
   model may still need loading or may not support chat completions.
   If discovery fails, report the error and ask for a usable endpoint,
   authentication, or explicit model IDs; do not invent models.
4. If authentication is required, explain that `API_KEY` in `.env` is
   supported and that the file must remain untracked; alternatively explain
   how to provide it through an environment variable. Never ask the user to
   paste a secret
   into chat or put secrets in skill files, printed commands, or logs. For the
   multi-model runner, the user can set `LLAMA_BENCHY_API_KEY` or
   `OPENAI_API_KEY` in their shell. To send a key during discovery, explicitly
   add `--api-key-env LLAMA_BENCHY_API_KEY` (or the chosen variable name).
   Discovery does not automatically send environment credentials and refuses
   HTTP redirects. The single-model CLI requires `--api-key`; pass a shell variable
   reference rather than the literal value, and warn that process arguments
   may be visible locally. Do not send credentials to an untrusted endpoint.
5. Present the following profiles and a single-select profile selector with
   **Smoke test** selected by default. Keep each choice as a separate
   block with one setting per line; do not compress settings into slash-
   separated text or a wide table. Let the user accept a profile unchanged or
   choose to adjust it; do not ask users to invent parameters:

   **Smoke test (recommended)** — quick endpoint check
   - Prompt length: 512 tokens
   - Generation length: 32 tokens
   - Context depth: 0 tokens
   - Measured runs: 1
   - Concurrency: 1

   **Context sweep** — measure performance as context grows
   - Prompt length: 2048 tokens
   - Generation length: 32 tokens
   - Context depths: 0, 4096, 8192, 16384, 32768 tokens
   - Measured runs: 3
   - Concurrency: 1

   **Fixed-length throughput** — compare sustained generation
   - Prompt length: 2048 tokens
   - Generation length: exactly 256 tokens
   - Context depth: 0 tokens
   - Measured runs: 3
   - Concurrency: 1
   - Requirement: server supports `min_tokens` and `ignore_eos`

   **Load scaling** — compare throughput under parallel requests
   - Prompt length: 2048 tokens
   - Generation length: 32 tokens
   - Context depths: 0, 4096, 8192, 16384, 32768 tokens
   - Measured runs: 3
   - Concurrency levels: 1 and 4
   - Note: models share server resources while running in parallel.

   **Full matrix** — widest and longest test
   - Prompt lengths: 512, 2048, and 8192 tokens
   - Generation lengths: 32 and 128 tokens
   - Context depths: 0, 8192, and 16384 tokens
   - Measured runs: 3 per shape
   - Concurrency: 1
   - Total: 18 test shapes

   Every profile uses 1 warmup run and generation latency mode. Explain that
   depths may be capped and that context depth + prompt + generation + chat
   template headroom must fit the server's context limit. If discovery omits
   `max_input_tokens`, do not infer an unlimited context: the single-model CLI
   does not cap requested depths, so warn that oversized cases may fail. Never
   silently remove requested depths; the multi-model runner's cap behavior is
   described below.

   Ask **Use these settings (recommended)** or **Adjust settings**, defaulting
   to use as-is. If adjustment is selected, present labeled structured choices
   in a form, preselected to the chosen profile's values (or the user's
   explicit values). Offer an `Other` free-text option for each numeric field
   when supported, rather than a single textbox for the whole configuration:

   - Prompt lengths: 512, 2048, 8192; multi-select for multiple values.
   - Generation lengths: 32, 128, 256; multi-select for multiple values.
   - Context depths: 0, 4096, 8192, 16384, 32768; multi-select.
   - Measured runs: 1 (quick), 3 (recommended for comparison), 5.
   - Warmup runs: 0, 1 (recommended), 2.
   - Concurrency levels: 1, 2, 4; multi-select for a load sweep.
   - Exact output length: off (recommended unless the server supports
     `min_tokens` and `ignore_eos`) or on.
   - Prefix-caching measurement: off (recommended) or on for nonzero depths.
   - Results: save JSON (recommended and default), or choose Markdown, CSV, or
     console only. Generate a fresh, non-existing JSON path under `results`
     for each run and let the user change it. For the single-model CLI, create
     the parent directory if it does not exist and verify the target file is
     absent; the CLI does not create parent directories and may overwrite files.

   Artifact names must be explicit and use:
   `model-endpoint-test-type-UTCtimestamp.extension` (for example
   `llama-3-localhost-smoke-20261124T183914Z.json` or
   `GLM-5.3-Flash-ai11-smoke-20261124T191008Z.json`). Use the first DNS label of
   an FQDN for the endpoint, but preserve an IP address as written. Do not
   include the port, scheme, domain suffix, or API version path in the filename;
   the exact normalized base URL including `/v1` belongs in report JSON. Apply
   the same convention to Markdown companions and logs. Multi-model summary
   names use `summary-endpoint-test-type-UTCtimestamp.extension`.

   Defaults for options absent from a profile are exact output off, prefix
   caching off, and a JSON report saved under `results`. Use a unique timestamp
   in the filename and verify the path does not already exist. For the
   multi-model runner, use a fresh, unique `--output-dir` under `results`.
   Validate custom numbers and context limits; never silently discard values.
   Explain that parameter lists form a cross-product, then confirm the resolved
   settings, report path, and runtime implications.
   Offer **Run now** or **Only prepare commands** if not already specified.

## Tokenizer and corpus

The API's served model ID is not necessarily a Hugging Face tokenizer ID.
Prefer the matching Hugging Face model/tokenizer or a local tokenizer path.
With a different served ID, use `--model <hf-model>` and
`--served-model-name <api-model-id>`, or use the API ID with
`--tokenizer <matching-tokenizer>`. A failed tokenizer load falls back to GPT-2,
which makes prompt lengths and some metrics approximate: report this clearly
and ask for the correct tokenizer when accuracy matters. Do not claim a
successful result has exact token counts when a fallback was used.

The first run may download dependencies, tokenizer files and a Project
Gutenberg corpus. Always pass `--book-url` explicitly. Use this checked
plain-text Sherlock Holmes mirror by default:
`https://mirror.csclub.uwaterloo.ca/gutenberg/1/6/6/1661/1661-0.txt`.
Before starting the benchmark, preflight the selected URL with a bounded HTTP
request and confirm it returns a successful 2xx response (including 206) and
plain text. If it is unavailable, do not start the benchmark or silently switch
sources: report the status and ask the user to approve another accessible
plain-text HTTP(S) URL. Local `file://` URLs are not supported. Do not use
unrelated HTML as a substitute without agreement. Keep coherence testing
enabled unless the user chooses to skip it.

An unauthenticated Hugging Face warning alone is not a failure; public files
may still download. Authentication can help with rate limits or gated models.
Check for `HF_TOKEN` in the process environment or in `.env` in the current
directory without displaying its value. `huggingface_hub` reads `HF_TOKEN`
automatically. When it is in `.env`, load it into the command with
`uv run --env-file .env ...` (or `uvx --env-file .env ...`); do not parse or
print the secret. For example:

```text
uv run --env-file .env llama-benchy --base-url <base-url> --model <model>
```

Alternatively, log in once in a local terminal with `hf auth login`; enter the
token only at its prompt. If `hf` is unavailable, use
`uv run hf auth login` from a checkout or
`uvx --with huggingface-hub hf auth login`. Never request, echo, or place the
token in command arguments or chat. After setting the environment variable,
loading `.env`, or logging in, retry the benchmark.
On Windows PowerShell, redirecting native stderr with `2>&1` can make warnings
look like `NativeCommandError`; check the actual process exit code and results.
Missing streamed token IDs can cause a fallback to the server's usage token
count; report it without claiming token-level precision. If output characters
such as `±` are garbled, use a UTF-8 terminal or save JSON for inspection.

## Set up llama-benchy

The skill does not install llama-benchy automatically. Check for `uv` and an
existing installation; request consent before downloading Python 3.10+ or
packages. If needed, use the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)
and verify `uv --version`.

- PyPI release: `uvx llama-benchy`.
- Upstream main: `uvx --from git+https://github.com/eugr/llama-benchy llama-benchy`.
- From a checkout: `uv run llama-benchy`. For an editable install, create
  `.venv` with `uv venv` if needed, then run `uv pip install -e .`.
- The multi-model runner is `scripts/bench_models.py` in this checkout. It uses
  one endpoint and can benchmark multiple served model IDs in parallel. A
  separate checkout or client is not required. Do not overwrite existing files
  or switch a dirty checkout.

Verify the chosen CLI with `--help` or `--version` and report setup failures.
For command-only requests, provide setup instructions without running them.

## Run or construct commands

### Show the exact command before running

Before launching any benchmark, print a copyable, fully expanded command that
matches what will actually execute. Include the `uv run`/`uvx` prefix and every
selected or behavior-affecting option: endpoint, API key source, model and
served model if different, tokenizer if selected, `--pp`, `--tg`, `--depth`,
`--runs`, `--warmup-runs`, `--concurrency`, `--latency-mode`, `--book-url`,
format, and output path. Spell out defaults used by the run, including
`--api-key EMPTY` when unauthenticated. By default, save JSON and include
`--format json --save-result <fresh-path>`; use another format or console-only
output only if the user selects it. State false boolean settings (for example
coherence check enabled, prefix caching disabled) next to the command rather
than suggesting their flags were passed. Add selected flags such as
`--exact-tg` or `--enable-prefix-caching`; do not include unrelated options.

If the user approved changing only the corpus URL, keep every other argument
the same and show the approved URL as the `--book-url` value. Never silently
change other settings.

For multi-model runs, show the runner command and the resolved llama-benchy
command for each selected model, including its resolved context depths and
distinct output path. Never expose a real API or HF token in displayed
commands. Use an environment-variable reference or `<redacted>` placeholder,
and explain if the program must receive a secret through a process argument.
When using `.env`, show `--env-file .env` in the llama-benchy command (and
`uv run --env-file .env` when Hugging Face tooling must also see it) so the actual
invocation is reproducible.

For one model, a small starting point is:

```text
uv run llama-benchy --env-file .env --model <api-model-id> --pp 512 --tg 32 --depth 0 --concurrency 1 --runs 1 --warmup-runs 1 --latency-mode generation --adapt-prompt --format json --save-result results/<model-slug>-<endpoint-slug>-smoke-<UTCtimestamp>.json --book-url https://mirror.csclub.uwaterloo.ca/gutenberg/1/6/6/1661/1661-0.txt
```

This example uses a checkout; substitute the selected `uvx` prefix when using
the release or upstream main branch.

Add a matching `--tokenizer` or `--served-model-name` when needed. Generate a
fresh JSON path per model and avoid overwriting existing results. If the user
wants commands only, quote model IDs and paths for their shell, and provide
PowerShell syntax on Windows or POSIX shell syntax on macOS/Linux. Use
single-line commands where practical. Explain prerequisites and placeholders.

For multiple models, the branch's existing runner discovers models and can
produce JSON reports, logs, and a combined summary:

```text
uv run python scripts/bench_models.py --env-file .env --models <id1,id2> --profile smoke --runs 1 --output-dir results/<endpoint-short-name>-smoke-<UTCtimestamp> --yes
```

If `LLAMA_BENCHY_MODELS` contains the confirmed model subset, omit `--models`;
the runner reads the model subset from `.env`. `LLAMA_BENCHY_PROFILE` is
optional; when present, its comma-separated values constrain the runner to
those profiles. Run them sequentially with separate artifact names. An explicit
`--profile`, including a comma-separated list, overrides that environment
value. When neither is present, choose a profile interactively or explicitly
for a non-interactive run. Use `--all` only when the user requests all eligible
models. The runner supports multiple models on one `API_BASE`, not multiple
endpoint/client bases in one invocation.
Benchmark different endpoints with separate runner invocations and separate
endpoint-qualified output directories.

The runner's `smoke` profile defaults to pp 2048, not the skill's recommended
pp 512: add `--pp 512` when using the skill's smoke settings. Pass all other
overrides required to match the user's confirmed choices.

Use `--all` instead of `--models` only if the user requested all eligible
models. The runner excludes IDs containing `embedding` or `reranker`; explain
this to the user. It runs models **in parallel**, which can distort performance
on shared hardware. For isolated comparisons run the single-model CLI
sequentially instead, with separate output files. Do not use the runner when
different models require different tokenizer settings; run them separately.
Pass compatible CLI extras such as `--tokenizer` or `--book-url` to the runner
only when they apply to every selected model.

Runner profiles: `smoke` (pp2048/tg32, depth 0), `sweep` (depths 0 through
32768), `throughput` (tg256 with `--exact-tg`), `full` (sweep at concurrency 1
and 4), and `matrix` (18 shapes). The throughput profile requires server
support for `min_tokens` and `ignore_eos`; do not assume all servers honor
them. Override profiles with `--pp`, `--tg`, `--depth`, or `--concurrency`.
The runner limits depths using reported `max_input_tokens` or `--unknown-cap`
(default 32768), with `--margin` (default 512). Its fallback to depth 0 does
not guarantee the remaining prompt fits: check context limits independently.
The runner writes under `results` by default; always pass a fresh, unique
`--output-dir` under `results` to avoid overwriting earlier reports and logs.

`--dry-run` on the runner discovers models and prints resolved commands without
starting benchmarks, but prints API keys in those commands, including keys
loaded from the environment. Do not use it with a real key. When authenticated,
avoid printing the runner's resolved subprocess commands and do not include
`--api-key` as an explicit runner argument, since it prints an equivalent
command. The runner passes the key to child process arguments; disclose that
local process visibility risk.

## Verify and report

For actual runs, monitor until completion; report failures and inspect logs
rather than claiming success from launch alone. Verify exit status and the
saved JSON file exists and parses; also verify per-model status for runner
results. The multi-model runner writes explicitly named `summary-*.md`,
`summary-*.json`, per-model reports, and `logs/` in its output directory. JSON
reports must contain `base_url` and `timestamp`; summaries must contain
`endpoint` and `generated_at`. Verify those provenance fields are populated.

End every run with a concise recap that includes:

- The exact llama-benchy CLI command(s) that ran. For a runner invocation,
  include the runner command and resolved CLI command(s) for each model.
  Redact secrets; do not imply a command ran if it was only prepared.
- The outcome and relevant results: selected models, benchmark settings,
  useful metrics, failures or skipped cases, and caveats such as tokenizer
  fallback, usage-token fallback, dropped depths, or parallel contention.
- The result files and their locations. Link to each report and summary when
  workspace file links are supported, and identify the output directory for
  logs. If a run failed before producing results, say no result file was
  created and give the failure and next step.
- A short result interpretation: what the completed shape measured, any
  notable throughput/latency behavior, and whether the result is suitable for
  isolated comparison. Do not over-interpret a single run or parallel-model
  run.

Then recommend 2-4 reasonable next tests derived from what actually ran. Do not
offer the full matrix indiscriminately. Present recommendations as a structured
multi-select or numbered choices with one-line rationale, estimated relative
cost, and the CLI/profile change required. Use these protocols as a starting
point and adapt choices to model context limits, server capabilities, and the
user's goal:

- **After smoke**: run `sweep` to measure context degradation; run
  `throughput` for stable fixed-length decode if `min_tokens` and `ignore_eos`
  are supported; or repeat the smoke test for a baseline/variance check.
- **After sweep**: run `full` or explicit `--concurrency 1 4` to test load
  scaling; narrow a promising model for isolated sequential runs; or add
  `--enable-prefix-caching` for nonzero-depth cache behavior.
- **After throughput**: run `sweep` to add prefill/context sensitivity; run
  selected concurrency levels to find saturation; or use different generation
  lengths to locate short- versus long-output behavior.
- **After full/load scaling**: repeat the strongest operating points in
  isolation for clean absolute numbers; vary prompt length or generation length
  if the bottleneck is unclear; or run the matrix only for finalists.
- **After matrix**: rerun the best/worst or unexpected shapes with more measured
  runs; test concurrency on the most relevant shape; or run fixed-length
  throughput on finalists.
- **After parallel multi-model runs**: offer sequential single-model reruns for
  fair comparisons, emphasizing that simultaneous models share server
  resources.
- **After failures, skipped depths, tokenizer fallback, or usage-token
  fallback**: prioritize correcting tokenizer/authentication/context settings
  or rerunning the failed shape before widening the benchmark.

Always offer **Plot these results** after a successful JSON report or summary.
If the user accepts, invoke the `visualize-llama-benchy` skill rather than
duplicating its visualization procedure. Pass the exact saved JSON path(s) and
preserve the run skill's endpoint/profile/time naming context. Plotting uses
saved data only and must not rerun the benchmark or contact the endpoint.
Also offer **Stop here** so the user is not forced into another run. Before a
new benchmark, confirm the selected follow-up and show the new exact command.

For command-only requests, finish with the prepared command(s) and expected
output path(s), clearly stating that no benchmark ran and no result files were
created. Still suggest the most relevant 2-4 follow-up tests, but do not plot
or call the visualization skill because no result exists. Do not silently
change the corpus, tokenizer, or coherence settings.
