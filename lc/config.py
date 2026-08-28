"""Configuration read/write/validate layer.

Layout: ~/.algocoach/config.toml with a schema_version field reserved for
future migrations. Priority chain for every value: CLI arguments >
environment variables > config file. POSIX permissions are tightened to 600;
on Windows no POSIX permission semantics exist and security relies on storing
outside any repo under the user home directory.
"""

from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path

from lc.atomicio import atomic_write_text

try:
    import tomllib as _toml_reader
except ModuleNotFoundError:
    _toml_reader = None

SCHEMA_VERSION = 1

APP_DIR_NAME = ".algocoach"
CONFIG_FILE_NAME = "config.toml"
PROBLEMS_CACHE_NAME = "problems.json"
ARCHIVE_FILE_NAME = "submissions.jsonl"
FAVORITES_FILE_NAME = "favorites.json"
INSTANCE_LOCK_NAME = "instance.lock"

DEFAULTS = {
    "schema_version": SCHEMA_VERSION,
    "cookie": "",
    "csrf_token": "",
    "llm_api_key": "",
    "llm_base_url": "",
    "llm_model": "",
    "llm_thinking": "default",
    "llm_timeout": 120.0,
    "default_language": "cpp",
    "request_interval": 2.0,
    "workspace_root": "",
}

# Politeness bounds for the leetcode.cn rate limiter: below 0.5s the pacing
# gate is effectively off (risking site-side throttling/bans), above 60s a
# full sync would take hours; the LLM timeout must stay inside [5, 600] so a
# typo cannot hang or instantly fail every AI call. These live here - not in
# the settings API - because env overrides and CLI flows write the same keys
# through a different door and used to bypass the range policy entirely.
REQUEST_INTERVAL_MIN = 0.5
REQUEST_INTERVAL_MAX = 60.0
LLM_TIMEOUT_MIN = 5.0
LLM_TIMEOUT_MAX = 600.0

RANGE_LIMITS = {
    "request_interval": (REQUEST_INTERVAL_MIN, REQUEST_INTERVAL_MAX),
    "llm_timeout": (LLM_TIMEOUT_MIN, LLM_TIMEOUT_MAX),
}

# Note on UI preferences (theme / interface language): they are browser-side
# concerns persisted in localStorage by the web app. They deliberately do NOT
# live here - duplicating them created dead config keys nothing consumed.

ENV_OVERRIDES = {
    "cookie": "ALGOCOACH_COOKIE",
    "llm_api_key": "ALGOCOACH_LLM_API_KEY",
    "llm_base_url": "ALGOCOACH_LLM_BASE_URL",
    "llm_model": "ALGOCOACH_LLM_MODEL",
    "llm_thinking": "ALGOCOACH_LLM_THINKING",
    "llm_timeout": "ALGOCOACH_LLM_TIMEOUT",
    "default_language": "ALGOCOACH_DEFAULT_LANGUAGE",
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


def favorites_path() -> Path:
    return app_dir() / FAVORITES_FILE_NAME


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


# Single arbiter for config.toml mutations. Several agents rewrite the whole
# file (settings API save, cookie-rotation persist, data wipe) and each used
# to guard only its own window with a caller-local lock - so a settings save
# could be reverted by a rotation snapshot, and the wipe could race a persist
# into resurrecting the erased cookie. The mutex lives here, next to the file
# it protects; whole-file RMW sequences must hold update_lock().
_CONFIG_LOCK = threading.RLock()


@contextlib.contextmanager
def update_lock():
    """Hold across a load→mutate→save sequence to make it atomic."""
    with _CONFIG_LOCK:
        yield


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
    payload = dict(DEFAULTS)
    payload.update({k: v for k, v in config.items()})
    payload["schema_version"] = SCHEMA_VERSION
    # atomic_write_text serializes the swap under _CONFIG_LOCK and keeps the
    # owner-only tmp permissions (mkstemp) through the rename, which replaces
    # the previous explicit POSIX chmod
    with _CONFIG_LOCK:
        atomic_write_text(path, dump_toml(payload))


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


def validate_environment(environ=None) -> None:
    """Eagerly validate ALGOCOACH_* environment overrides.

    Without this, one malformed value (e.g. ALGOCOACH_REQUEST_INTERVAL=abc)
    exploded as a ValueError inside effective_config() on every endpoint -
    including the settings API the operator would need to fix it. Called
    once at startup so misconfiguration fails loudly at the door. Range
    bounds are enforced here too: the env path used to skip the policy the
    settings API applies, so ALGOCOACH_REQUEST_INTERVAL=0.01 silently
    disabled the pacing gate it exists to enforce.
    """
    environ = os.environ if environ is None else environ
    for key, env_name in ENV_OVERRIDES.items():
        raw = environ.get(env_name)
        if raw:
            try:
                value = _coerce(key, raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"environment variable {env_name}={raw!r} is not a valid "
                    f"value for {key}: {exc}"
                ) from None
            bounds = RANGE_LIMITS.get(key)
            if bounds and not bounds[0] <= value <= bounds[1]:
                raise ValueError(
                    f"environment variable {env_name}={raw!r} is out of range "
                    f"[{bounds[0]}, {bounds[1]}] for {key}"
                )


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
