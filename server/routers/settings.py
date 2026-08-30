"""App status, setup cookie validation, settings read/update, LLM probe."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, create_model

import lc
from lc import auth
from lc.auth import extract_csrf_token
from lc.config import (
    DEFAULTS,
    RANGE_LIMITS,
    SECRET_CONFIG_KEYS,
    app_dir,
    effective_config,
    save as save_config,
    update_lock,
)
from lc.langs import is_supported
from lc.llm import DEFAULT_MODEL, LLMClient, THINKING_LEVELS
from lc.logutil import logger
from server import state
from server.errors import http_domain_error

router = APIRouter()


@router.get("/api/status")
def get_status():
    config = effective_config()

    return {
        "app": "algocoach",
        "version": lc.__version__,
        "site": "leetcode.cn",
        "configured": bool(config.get("cookie")),
        # lets the AI coach sidebar gate on LLM availability the same way the
        # analytics page does, instead of only failing after a send
        "llm_configured": bool(config.get("llm_api_key"))
        and bool(config.get("llm_base_url")),
        "data_dir": str(app_dir()),
        "sync": state.sync_engine.progress(),
    }


@router.get("/api/heartbeat")
def heartbeat():
    """Liveness ping from every open web-UI tab (~every 20s); the cli
    --idle-exit watchdog shuts the server down once the age grows past the
    deadline, so closing the last tab retires the process."""
    state.touch_heartbeat()
    return {"ok": True}


class CookiePayload(BaseModel):
    cookie: str


@router.post("/api/setup/validate-cookie")
def validate_cookie(payload: CookiePayload):
    profile = state.validate_cookie_standalone(payload.cookie)
    return {"ok": True, "profile": profile}


def mask_secret(value: str) -> str:
    """Reveal only the tail: even a short prefix of a session token aids
    correlation attacks, so nothing but the last 4 chars is ever returned.
    Secrets shorter than 16 chars stay fully masked - on those the tail
    alone would expose too large a fraction of the entropy."""
    value = value or ""
    if not value:
        return ""
    if len(value) < 16:
        return "***"
    return f"…{value[-4:]}"


def masked_settings(config: dict) -> dict:
    """API view of the config, derived from DEFAULTS: secrets masked, the
    rest verbatim. Adding a setting to DEFAULTS extends this automatically."""
    masked: dict = {"configured": bool(config.get("cookie"))}
    for key in DEFAULTS:
        if key == "schema_version":
            continue
        if key in SECRET_CONFIG_KEYS:
            masked[f"{key}_masked"] = mask_secret(config.get(key, ""))
        else:
            masked[key] = config.get(key, DEFAULTS[key])
    return masked


@router.get("/api/settings")
def read_settings():
    return masked_settings(effective_config())


# Range policy lives in lc.config (RANGE_LIMITS) so every write door -
# settings API, env overrides, config file tooling - enforces the same
# bounds. The API still rejects (not clamps) so typos fail loudly.

# the only numeric settings (their RANGE_LIMITS keys); everything else str
_NUMERIC_SETTING_FIELDS = {"request_interval", "llm_timeout"}

# pydantic field type per setting; request_interval/llm_timeout are floats
_SETTING_FIELD_TYPES = {key: float for key in _NUMERIC_SETTING_FIELDS}


def _settings_update_model() -> type[BaseModel]:
    """Derive the PUT /api/settings body from lc.config.DEFAULTS.

    Every user-settable config key is accepted (schema_version is
    bookkeeping, not a setting) and unknown keys are rejected. Deriving the
    model keeps the config file, the environment overrides and this API from
    listing the fields independently and drifting apart.
    """
    fields = {
        key: (_SETTING_FIELD_TYPES.get(key, str) | None, None)
        for key in DEFAULTS
        if key != "schema_version"
    }
    return create_model(
        "SettingsUpdate", __config__=ConfigDict(extra="forbid"), **fields
    )


SettingsUpdate = _settings_update_model()


def _reject_invalid_updates(updates: dict) -> None:
    """Fail loudly on nulls, out-of-range numbers, bad enums and languages.

    One uniform rule for every field: an explicit null is a client bug
    (omitting the field already means "keep current value"). Letting nulls
    through used to mean a TypeError 500 for numeric fields and - worse -
    the string "None" silently written into config.toml for text fields.
    """
    null_fields = sorted(key for key, value in updates.items() if value is None)
    if null_fields:
        raise HTTPException(
            status_code=422,
            detail=(
                f"field(s) {', '.join(null_fields)} cannot be null; "
                "omit them to keep the current value"
            ),
        )
    for field, (low, high) in RANGE_LIMITS.items():
        if field in updates:
            value = float(updates[field])
            if not low <= value <= high:
                raise HTTPException(
                    status_code=422,
                    detail=f"{field} out of range [{low}, {high}]: {value}",
                )
    if "llm_thinking" in updates and updates["llm_thinking"] not in (
        "default",
        *THINKING_LEVELS,
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "llm_thinking must be one of: default, "
                + ", ".join(THINKING_LEVELS)
                + f"; got {updates['llm_thinking']!r}"
            ),
        )
    if "default_language" in updates and not is_supported(updates["default_language"]):
        raise HTTPException(
            status_code=422,
            detail=f"unsupported language: {updates['default_language']}",
        )


@router.put("/api/settings")
def update_settings(payload: SettingsUpdate):
    # the whole read→validate→mutate→save sequence holds the config update
    # lock: a cookie rotation persisting concurrently used to write its stale
    # whole-file snapshot afterwards and silently revert this save (including
    # resurrecting the pre-save cookie). rebuild() deliberately happens after
    # the lock is released - it acquires auth's persist lock, and no path may
    # take that lock while holding the config lock.
    with update_lock():
        config = effective_config()
        provided = payload.model_fields_set
        updates = payload.model_dump(exclude_unset=True)
        _reject_invalid_updates(updates)

        rebuild_needed = False
        if "cookie" in provided:
            config["cookie"] = updates["cookie"]
            config["csrf_token"] = extract_csrf_token(updates["cookie"])
            rebuild_needed = True
        config.update({key: value for key, value in updates.items() if key != "cookie"})

        save_config(config)
    if rebuild_needed:
        auth.rebuild(config["cookie"], request_interval=config["request_interval"])
    logger.info("settings updated (fields=%s)", sorted(provided))
    return masked_settings(effective_config())


class LlmTestPayload(BaseModel):
    model_config = {"extra": "forbid"}

    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_thinking: str | None = None


# A probe must feel snappy even when the saved llm_timeout is generous; 30s
# still clears slow cold-start endpoints but never hangs the settings page.
LLM_TEST_TIMEOUT_CAP = 30.0


@router.post("/api/llm/test")
def test_llm_endpoint(payload: LlmTestPayload):
    """One-shot LLM connectivity probe.

    Fields provided in the payload override the saved config, so the settings
    form can verify what the user just typed before saving; omitted fields
    fall back to the saved values. Uses a tiny max_tokens cap to keep the
    probe cheap.
    """
    config = effective_config()
    updates = payload.model_dump(exclude_unset=True)
    api_key = str(updates.get("llm_api_key", "") or config.get("llm_api_key", "") or "")
    base_url = str(updates.get("llm_base_url", "") or config.get("llm_base_url", "") or "")
    model = str(
        updates.get("llm_model", "") or config.get("llm_model", "") or DEFAULT_MODEL
    )
    thinking = str(
        updates.get("llm_thinking", "") or config.get("llm_thinking", "") or "default"
    )
    if not api_key or not base_url:
        raise http_domain_error(400, "ask_not_configured")
    timeout = min(float(config.get("llm_timeout", 120.0)), LLM_TEST_TIMEOUT_CAP)
    llm = LLMClient(
        base_url=base_url, api_key=api_key, model=model, timeout=timeout, thinking=thinking
    )
    reply = llm.chat([{"role": "user", "content": "ping"}], max_tokens=8)
    return {"ok": True, "model": llm.model, "reply": reply[:80]}
