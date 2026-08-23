"""Configuration read/write/validate layer.

Layout: ~/.algocoach/config.toml with a schema_version field reserved for
future migrations. Priority chain for every value: CLI arguments >
environment variables > config file. POSIX permissions are tightened to 600;
on Windows no POSIX permission semantics exist and security relies on storing
outside any repo under the user home directory.
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

try:
    import tomllib as _toml_reader
except ModuleNotFoundError:
    _toml_reader = None

SCHEMA_VERSION = 1

APP_DIR_NAME = ".algocoach"
CONFIG_FILE_NAME = "config.toml"
PROBLEMS_CACHE_NAME = "problems.json"
ARCHIVE_FILE_NAME = "submissions.jsonl"
INSTANCE_LOCK_NAME = "instance.lock"

DEFAULTS = {
    "schema_version": SCHEMA_VERSION,
    "cookie": "",
    "csrf_token": "",
    "llm_api_key": "",
    "llm_base_url": "",
    "llm_model": "",
    "llm_timeout": 120.0,
    "default_language": "cpp",
    "ui_language": "",
    "theme": "system",
    "request_interval": 2.0,
    "workspace_root": "",
}

ENV_OVERRIDES = {
    "cookie": "ALGOCOACH_COOKIE",
    "llm_api_key": "ALGOCOACH_LLM_API_KEY",
    "llm_base_url": "ALGOCOACH_LLM_BASE_URL",
    "llm_model": "ALGOCOACH_LLM_MODEL",
    "llm_timeout": "ALGOCOACH_LLM_TIMEOUT",
    "default_language": "ALGOCOACH_DEFAULT_LANGUAGE",
    "ui_language": "ALGOCOACH_UI_LANGUAGE",
    "theme": "ALGOCOACH_THEME",
    "request_interval": "ALGOCOACH_REQUEST_INTERVAL",
    "workspace_root": "ALGOCOACH_WORKSPACE_ROOT",
}

_MIGRATIONS = {}


def app_dir() -> Path:
    override = os.environ.get("ALGOCOACH_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / APP_DIR_NAME


def config_path() -> Path:
    return app_dir() / CONFIG_FILE_NAME


def problems_cache_path() -> Path:
    return app_dir() / PROBLEMS_CACHE_NAME


def archive_path() -> Path:
    return app_dir() / ARCHIVE_FILE_NAME


def workspace_root_path(config: dict) -> Path:
    custom = str(config.get("workspace_root", "") or "")
    if custom:
        return Path(custom).expanduser()
    return app_dir() / "workspace"


def _escape_toml_string(value: str) -> str:
    out = []
    for ch in value:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def dump_toml(data: dict) -> str:
    lines = []
    keys = [k for k in DEFAULTS if k in data]
    keys += sorted(k for k in data if k not in DEFAULTS)
    for key in keys:
        value = data[key]
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (int, float)):
            rendered = repr(value)
        else:
            rendered = _escape_toml_string(str(value))
        lines.append(f"{key} = {rendered}")
    return "\n".join(lines) + "\n"


def _strip_comment(line: str) -> str:
    in_quotes = False
    escaped = False
    for idx, ch in enumerate(line):
        if ch == '"' and not escaped:
            in_quotes = not in_quotes
        if ch == "\\" and in_quotes:
            escaped = not escaped
            continue
        escaped = False
        if ch == "#" and not in_quotes:
            return line[:idx]
    return line


def _unescape_string(inner: str) -> str:
    mapping = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "r": "\r"}
    out = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner):
            nxt = inner[i + 1]
            if nxt in mapping:
                out.append(mapping[nxt])
                i += 2
                continue
            if nxt == "u" and i + 6 <= len(inner):
                try:
                    out.append(chr(int(inner[i + 2:i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_value(raw: str):
    raw = raw.strip()
    if raw.startswith('"'):
        end = 1
        while end < len(raw):
            if raw[end] == "\\":
                end += 2
                continue
            if raw[end] == '"':
                break
            end += 1
        if end >= len(raw):
            raise ValueError("unterminated string")
        return _unescape_string(raw[1:end])
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"unsupported TOML value: {raw!r}") from None


def parse_simple_toml(text: str) -> dict:
    """Fallback parser for the flat key=value subset this module writes."""
    result = {}
    for raw_line in text.splitlines():
        line = _strip_comment(raw_line).strip()
        if not line or line.startswith("["):
            continue
        name, sep, value = line.partition("=")
        if not sep:
            continue
        name = name.strip().strip('"')
        result[name.strip()] = _parse_value(value)
    return result


def parse_toml(text: str) -> dict:
    if _toml_reader is not None:
        return _toml_reader.loads(text)
    return parse_simple_toml(text)


def load(path=None) -> dict:
    path = Path(path) if path is not None else config_path()
    merged = dict(DEFAULTS)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        parsed = parse_toml(text)
        migrated = _migrate(parsed)
        for key in DEFAULTS:
            if key in migrated and migrated[key] is not None:
                merged[key] = _coerce(key, migrated[key])
    return merged


def save(config: dict, path=None) -> None:
    path = Path(path) if path is not None else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(DEFAULTS)
    payload.update({k: v for k, v in config.items()})
    payload["schema_version"] = SCHEMA_VERSION
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(dump_toml(payload))
        if os.name == "posix":
            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def effective_config(cli_overrides=None, path=None, environ=None) -> dict:
    environ = os.environ if environ is None else environ
    config = load(path)

    for key, env_name in ENV_OVERRIDES.items():
        env_value = environ.get(env_name)
        if env_value is not None and env_value != "":
            config[key] = _coerce(key, env_value)

    if cli_overrides:
        for key, value in cli_overrides.items():
            if value is None:
                continue
            config[key] = _coerce(key, value)
    return config


def _coerce(key, value):
    default = DEFAULTS.get(key)
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int) and not isinstance(default, bool):
        return int(str(value).strip())
    if isinstance(default, float):
        return float(str(value).strip())
    return str(value)


def _migrate(data: dict) -> dict:
    version = int(data.get("schema_version", 0) or 0)
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"config schema_version {version} is newer than supported {SCHEMA_VERSION}"
        )
    while version < SCHEMA_VERSION:
        version += 1
        migrator = _MIGRATIONS.get(version)
        if migrator is not None:
            data = migrator(data)
    return data
