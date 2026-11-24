import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".agents"
    / "skills"
    / "run-llama-benchy"
    / "scripts"
    / "discover_models.py"
)


@pytest.fixture
def endpoint():
    class Handler(BaseHTTPRequestHandler):
        requests = []

        def do_GET(self):
            self.requests.append((self.path, self.headers.get("Authorization")))
            if self.path == "/redirect/models":
                self.send_response(302)
                self.send_header("Location", "/v1/models")
                self.end_headers()
                return
            if self.path == "/bad/models":
                body = b'{"error": "bad response"}'
            else:
                body = json.dumps({"data": [
                    {"id": "org/one", "root": "org/base", "max_input_tokens": 4096},
                    {"id": "two"},
                ]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", Handler.requests
    server.shutdown()
    thread.join()
    server.server_close()


@pytest.mark.parametrize("suffix", ["", "/v1/", "/v1/models", "/v1/chat/completions"])
def test_discovery_lists_all_models_for_endpoint_forms(endpoint, suffix):
    base, requests = endpoint
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base-url", base + suffix, "--format", "json"],
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == [
        {"id": "org/one", "root": "org/base", "max_input_tokens": 4096},
        {"id": "two"},
    ]
    assert requests == [("/v1/models", None)]


def test_discovery_uses_explicit_key_environment_variable(endpoint):
    base, requests = endpoint
    env = {**os.environ, "TEST_BENCHY_KEY": "test-key"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base-url", base, "--api-key-env", "TEST_BENCHY_KEY"],
        capture_output=True, text=True, env=env, check=True,
    )
    assert requests == [("/v1/models", "Bearer test-key")]
    assert "test-key" not in result.stdout + result.stderr


def test_discovery_reports_invalid_response(endpoint):
    base, _ = endpoint
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base-url", base + "/bad"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "data" in result.stderr


def test_discovery_rejects_url_credentials():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base-url", "http://user:secret@localhost/v1"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "secret" not in result.stderr


def test_discovery_does_not_follow_redirects(endpoint):
    base, requests = endpoint
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base-url", base + "/redirect"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "HTTP 302" in result.stderr
    assert requests == [("/redirect/models", None)]
