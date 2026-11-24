import importlib.util
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "bench_models.py"
SPEC = importlib.util.spec_from_file_location("bench_models", SCRIPT_PATH)
assert SPEC and SPEC.loader
bench_models = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench_models)


def test_build_command_omits_key_loaded_from_environment(tmp_path):
    args = SimpleNamespace(
        base_url="https://localhost/v1",
        api_key="secret-key",
        runs=1,
        warmup_runs=1,
        enable_prefix_caching=False,
    )
    report_path = tmp_path / "model-endpoint-smoke-date.json"
    profile = {
        "pp": [512],
        "tg": [32],
        "concurrency": [1],
        "exact_tg": False,
    }

    command = bench_models.build_command(
        ["llama-benchy"],
        args,
        [],
        set(),
        "model-a",
        profile,
        [0],
        report_path,
    )

    assert "--api-key" not in command
    assert "secret-key" not in command


def test_summary_uses_endpoint_profile_and_timestamp_name(tmp_path):
    args = SimpleNamespace(
        base_url="https://localhost:8000/v1",
        runs=1,
        warmup_runs=0,
    )
    result = {
        "model": "model-a",
        "status": "failed",
        "exit_code": 1,
        "elapsed": 0,
        "report": None,
        "error": "test failure",
        "log_path": str(tmp_path / "missing.log"),
        "run_timestamp": "20261124T183914Z",
    }

    markdown_path = bench_models.write_summary(
        tmp_path, args, "smoke", [], [result]
    )

    assert markdown_path.name == (
        "summary-localhost-smoke-20261124T183914Z.md"
    )
    assert markdown_path.with_suffix(".json").exists()


def test_endpoint_name_uses_short_fqdn_label():
    assert (
        bench_models.endpoint_name("https://ai11.labs.hpecorp.net/v1")
        == "ai11"
    )


def test_endpoint_name_preserves_ip_address():
    assert bench_models.endpoint_name("http://192.0.2.10:8000/v1") == "192.0.2.10"


def test_parse_profiles_accepts_comma_separated_unique_values():
    assert bench_models.parse_profiles("smoke, sweep,smoke") == [
        "smoke",
        "sweep",
    ]


def test_parse_profiles_rejects_unknown_value():
    try:
        bench_models.parse_profiles("smoke,unknown")
    except SystemExit as error:
        assert "unknown profile(s): unknown" in str(error)
    else:
        raise AssertionError("unknown profile was accepted")
