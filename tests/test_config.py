import pytest
import sys

from llama_benchy.config import BenchmarkConfig


def test_parse_extra_body_accepts_repeated_key_value_entries():
    extra = BenchmarkConfig._parse_extra_body([
        "min_tokens=1024",
        "ignore_eos=true",
        "temperature=0",
    ])

    assert extra == {
        "min_tokens": 1024,
        "ignore_eos": True,
        "temperature": 0,
    }


def test_parse_extra_body_accepts_aiperf_style_comma_separated_entries():
    extra = BenchmarkConfig._parse_extra_body([
        "max_tokens:1024,min_tokens:1024,ignore_eos:true",
    ])

    assert extra == {
        "max_tokens": 1024,
        "min_tokens": 1024,
        "ignore_eos": True,
    }


def test_parse_extra_body_rejects_entries_without_separator():
    with pytest.raises(ValueError):
        BenchmarkConfig._parse_extra_body(["ignore_eos"])


def test_from_args_loads_api_defaults_from_env_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("API_BASE=https://inference.example\nAPI_KEY=test-key\n")
    for key in (
        "API_BASE",
        "API_KEY",
        "LLAMA_BENCHY_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["llama-benchy", "--env-file", str(env_file), "--model", "model-a"],
    )

    config = BenchmarkConfig.from_args()

    assert config.base_url == "https://inference.example/v1"
    assert config.api_key == "test-key"


def test_from_args_preserves_explicit_custom_base_path(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("API_BASE=https://unused.example\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "llama-benchy",
            "--env-file",
            str(env_file),
            "--base-url",
            "https://inference.example/openai/v2/",
            "--model",
            "model-a",
        ],
    )

    config = BenchmarkConfig.from_args()

    assert config.base_url == "https://inference.example/openai/v2"


def test_default_book_url_uses_waterloo_mirror(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("API_BASE=https://inference.example\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "llama-benchy",
            "--env-file",
            str(env_file),
            "--model",
            "model-a",
        ],
    )

    config = BenchmarkConfig.from_args()

    assert config.book_url == (
        "https://mirror.csclub.uwaterloo.ca/gutenberg/"
        "1/6/6/1661/1661-0.txt"
    )
