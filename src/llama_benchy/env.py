import os
import re
from typing import Dict


def parse_env_file(path: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    with open(path, encoding="utf-8") as env_file:
        for line_number, raw_line in enumerate(env_file, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, raw_value = line.partition("=")
            if not separator or not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*", key.strip()
            ):
                raise ValueError(f"{path}:{line_number}: expected KEY=value")

            raw_value = raw_value.strip()
            if (
                len(raw_value) >= 2
                and raw_value[0] == raw_value[-1]
                and raw_value[0] in ("'", '"')
            ):
                raw_value = raw_value[1:-1]
            else:
                raw_value = re.split(r"\s+#", raw_value, maxsplit=1)[0].strip()
            values[key.strip()] = raw_value
    return values


def load_env_file(path: str, required: bool = False) -> Dict[str, str]:
    try:
        values = parse_env_file(path)
    except FileNotFoundError:
        if required:
            raise ValueError(f"environment file not found: {path}")
        return {}
    except OSError as error:
        raise ValueError(f"could not read environment file {path}: {error}") from error
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values


def normalize_env_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1/models"):
        normalized = normalized[: -len("/models")]
    elif normalized.endswith("/v1/chat/completions"):
        normalized = normalized[: -len("/chat/completions")]
    if not normalized.endswith("/v1"):
        normalized += "/v1"
    return normalized
