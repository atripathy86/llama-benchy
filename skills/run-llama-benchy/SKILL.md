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

1. Do not ask open-endedly what benchmark the user wants. Use structured
   selections with recommendations and defaults. Offer free-text input only
   for exceptional values. Default to **Smoke test** if the user asks to run
   a benchmark without specifying its scope. Ask for the endpoint only when
   none is provided, and retain settings the user has already specified.
2. Use an OpenAI-compatible API base URL, normally ending in `/v1`, without a
   trailing slash. For a bare server URL, append `/v1`. If given `/v1/models`
   or `/v1/chat/completions`, remove that suffix to obtain the base. Do not
   silently add `/v1` to an explicitly supplied custom API base path.
3. If an endpoint is given, query it live before model selection using the
   cross-platform Python script in this skill. Run it with `uv run` from the
   llama-benchy checkout root so discovery and benchmarking use the same
   project environment:

   ```text
   uv run python skills/run-llama-benchy/scripts/discover_models.py --base-url "<endpoint>" --format json
   ```

   On Windows PowerShell, use
   `uv run python skills\run-llama-benchy\scripts\discover_models.py --base-url "<endpoint>" --format json`.
   When installed elsewhere with `npx skills add`, use the installed skill's
   `scripts/discover_models.py` path instead of assuming it is under the
   checkout's `skills/` directory, but still run it with
   `uv run --project <llama-benchy-checkout> python <skill-script-path>` so it
   uses the checkout's environment. If no checkout exists yet, set it up before
   endpoint discovery.
   The script accepts a bare server URL, `/v1`, `/v1/models`,
   `/v1/chat/completions`, or a custom API base path. It prints an array of
   model objects containing `id` and, when available, `root` and
   `max_input_tokens`. If multiple models are returned, show them in a
   multi-select form, including **All models** and **Other** for IDs not listed;
   never assume the first model. Explain that a
   listed model may still need loading or may not support chat completions.
   If discovery fails, report the error and ask for a usable endpoint,
   authentication, or explicit model IDs; do not invent models.
4. If authentication is required, explain how to provide it through an
   environment variable. Never ask the user to paste a secret
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
   template headroom must fit the server's context limit.

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
   - Results: console only (recommended for a quick test), or save as JSON,
     Markdown, or CSV. For saved results suggest a new, non-existing path and
     allow the user to change it.

   Defaults for options absent from a profile are exact output off, prefix
   caching off, and console only. If the selected runner always saves reports,
   explain this and ask the user to approve a fresh output directory instead of
   promising console-only output. Validate custom numbers and context limits;
   never silently discard values. Explain that parameter lists form a
   cross-product, then confirm the resolved settings and runtime implications.
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
Gutenberg corpus. If the corpus URL fails, report the error and ask for an
accessible plain-text HTTP(S) URL via `--book-url`; for example, the same book
is available at
`https://mirror.csclub.uwaterloo.ca/gutenberg/1/6/6/1661/1661-0.txt`.
Check that the mirror is reachable before offering it; local `file://` URLs
are not supported. Do not use unrelated HTML as a substitute without agreement.
Keep coherence testing enabled unless the user chooses to skip it.

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
- The multi-model runner requires a `bench-models` checkout of
  `https://github.com/atripathy86/llama-benchy.git`. With permission, clone it
  into a new directory; otherwise use sequential single-model runs. Do not
  overwrite existing files or switch a dirty checkout.

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
`--api-key EMPTY` when unauthenticated and `--format md` when not saving JSON
or CSV. State false boolean settings (for example coherence check enabled,
prefix caching disabled) next to the command rather than suggesting their
flags were passed. Add selected flags such as `--exact-tg` or
`--enable-prefix-caching`; do not include unrelated options.

If the user approved changing only the corpus URL, keep every other argument
the same and show the approved URL as the `--book-url` value. Never silently
change other settings.

For multi-model runs, show the runner command and the resolved llama-benchy
command for each selected model, including its resolved context depths and
distinct output path. Never expose a real API or HF token in displayed
commands. Use an environment-variable reference or `<redacted>` placeholder,
and explain if the program must receive a secret through a process argument.
When using `.env`, show `--env-file .env` in the `uv` command so the actual
invocation is reproducible.

For one model, a small starting point is:

```text
uv run llama-benchy --base-url <base-url> --api-key EMPTY --model <api-model-id> --pp 512 --tg 32 --depth 0 --concurrency 1 --runs 1 --warmup-runs 1 --latency-mode generation --adapt-prompt --format md --book-url https://www.gutenberg.org/files/1661/1661-0.txt
```

This example uses a checkout; substitute the selected `uvx` prefix when using
the release or upstream main branch.

Add a matching `--tokenizer` or `--served-model-name` when needed. For JSON
output, include `--format json --save-result <path>`; use a distinct path per
model and avoid overwriting existing results. If the user wants commands only,
quote model IDs and paths for their shell, and provide PowerShell syntax on
Windows or POSIX shell syntax on macOS/Linux. Use single-line commands where
practical. Explain prerequisites and placeholders.

For multiple models, the branch's existing runner discovers models and can
produce JSON reports, logs, and a combined summary:

```text
uv run python scripts/bench_models.py --base-url <base-url> --models <id1,id2> --profile smoke --runs 1 --yes
```

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
The runner writes under `results` by default; choose a fresh `--output-dir` to
avoid overwriting earlier reports and logs.

`--dry-run` on the runner discovers models and prints resolved commands without
starting benchmarks, but prints API keys in those commands, including keys
loaded from the environment. Do not use it with a real key. When authenticated,
avoid printing the runner's resolved subprocess commands and do not include
`--api-key` as an explicit runner argument, since it prints an equivalent
command. The runner passes the key to child process arguments; disclose that
local process visibility risk.

## Verify and report

For actual runs, monitor until completion; report failures and inspect logs
rather than claiming success from launch alone. Verify exit status and, when
requested, the output files and per-model status. The multi-model runner writes
`summary.md`, `summary.json`, per-model reports, and `logs/` in its output
directory. Report selected models, benchmark settings, relevant metrics and
output locations, including any tokenizer fallback, skipped tests, dropped
depths, or parallel contention. If a test fails, surface the error and next
step; do not silently change the corpus, tokenizer, or coherence settings.
