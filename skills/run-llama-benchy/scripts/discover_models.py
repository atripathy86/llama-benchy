#!/usr/bin/env python3
"""List models from an OpenAI-compatible endpoint without extra dependencies."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit


def models_url(endpoint: str) -> str:
    parts = urlsplit(endpoint)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise ValueError("endpoint must be an HTTP(S) URL without credentials, query, or fragment")
    path = parts.path.rstrip("/")
    if not path:
        path = "/v1"
    elif path.endswith("/v1/chat/completions"):
        path = path[: -len("/chat/completions")]
    elif path.endswith("/v1/models"):
        path = path[: -len("/models")]
    return urlunsplit((parts.scheme, parts.netloc, path + "/models", "", ""))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def discover(endpoint: str, api_key: str | None) -> list[dict]:
    url = models_url(endpoint)
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise ValueError(f"{url} returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise ValueError(f"could not reach {url}: {error.reason}") from error
    except OSError as error:
        raise ValueError(f"request to {url} failed: {error}") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{url} did not return valid JSON") from error

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise ValueError("response must contain a 'data' array")
    models = [
        {key: item[key] for key in ("id", "root", "max_input_tokens") if key in item}
        for item in data
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
    ]
    if not models:
        raise ValueError("endpoint returned no model IDs")
    return models


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Endpoint URL, with or without /v1")
    parser.add_argument(
        "--api-key-env",
        metavar="VARIABLE",
        help="Read the API key from this environment variable (only for a trusted endpoint)",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    api_key = None
    if args.api_key_env:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            print(f"error: environment variable {args.api_key_env!r} is not set", file=sys.stderr)
            return 1
    try:
        models = discover(args.base_url, api_key)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(models, indent=2))
    else:
        for model in models:
            print(json.dumps(model, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
