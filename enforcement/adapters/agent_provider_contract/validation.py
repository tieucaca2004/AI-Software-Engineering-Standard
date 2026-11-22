"""Agent Provider Contract validation — stdlib-only, deterministic.

Implements the accepted schemas ases-provider/1, ases-exec-request/1 and
ases-exec-result/1 and their cross-field invariants. This module validates
contract records only; it does NOT grant authorization and does NOT re-implement
ASES governance.
"""
import re

PROVIDER_SCHEMA = "ases-provider/1"
REQUEST_SCHEMA = "ases-exec-request/1"
RESULT_SCHEMA = "ases-exec-result/1"

STATUSES = ("SUCCEEDED", "FAILED", "TIMED_OUT", "INTERRUPTED", "UNKNOWN")
TERMINATION_REASONS = ("none", "start-failed", "timeout", "interrupted", "external", "lost-observability")
OUTPUT_STATES = ("none", "complete", "partial", "unavailable")
EVIDENCE_STATES = ("complete", "partial", "unavailable")
ERROR_SCOPES = ("provider", "output", "evidence", "termination", "observability")

REQUEST_REQUIRED = ("schema", "request_id", "work_unit_id", "authorization_decision_ref",
                    "approved_scope_ref", "objective", "working_directory", "instructions", "config")
REQUEST_OPTIONAL = ("baseline_ref", "intent_decision_ref")
CONFIG_KNOWN = ("provider", "model", "permission_mode", "allowed_tools", "disallowed_tools")


class ValidationError(ValueError):
    pass


def _check(cond, msg):
    if not cond:
        raise ValidationError(msg)


def validate_provider(obj):
    if not isinstance(obj, dict):
        raise ValidationError("provider must be an object")
    _check(obj.get("schema") == PROVIDER_SCHEMA, "schema must be %r" % PROVIDER_SCHEMA)
    _check(isinstance(obj.get("provider_id"), str) and obj["provider_id"], "provider_id is required")
    _check(isinstance(obj.get("provider_version"), str) and obj["provider_version"], "provider_version is required")
    _check(isinstance(obj.get("adapter_version"), str) and obj["adapter_version"], "adapter_version is required")
    if "capabilities" in obj:
        _check(isinstance(obj["capabilities"], list) and all(isinstance(c, str) for c in obj["capabilities"]),
               "capabilities must be a list of strings")
    return obj


def validate_request(obj):
    if not isinstance(obj, dict):
        raise ValidationError("request must be an object")
    _check(obj.get("schema") == REQUEST_SCHEMA, "schema must be %r" % REQUEST_SCHEMA)
    for f in REQUEST_REQUIRED:
        _check(f in obj, "required field %r missing" % f)
    for f in REQUEST_OPTIONAL:
        if f in obj and obj[f] is not None:
            _check(isinstance(obj[f], str) and obj[f], "%r must be a non-empty string or null" % f)
    _check(isinstance(obj.get("request_id"), str) and obj["request_id"], "request_id is required")
    _check(isinstance(obj.get("work_unit_id"), str) and obj["work_unit_id"], "work_unit_id is required")
    _check(isinstance(obj.get("objective"), str), "objective must be a string")
    _check(isinstance(obj.get("working_directory"), str), "working_directory must be a string")
    _check(isinstance(obj.get("instructions"), str), "instructions must be a string")
    config = obj.get("config")
    _check(isinstance(config, dict), "config must be an object")
    _check(isinstance(config.get("provider"), str) and config["provider"], "config.provider is required")
    for k in config:
        if k not in CONFIG_KNOWN:
            # unknown execution-config fields are treated as constraining/security -> fail closed
            raise ValidationError("unknown execution-config field %r" % k)
    if "allowed_tools" in config:
        _check(isinstance(config["allowed_tools"], list), "config.allowed_tools must be a list")
    if "disallowed_tools" in config:
        _check(isinstance(config["disallowed_tools"], list), "config.disallowed_tools must be a list")
    return obj


def validate_result(obj, request=None):
    if not isinstance(obj, dict):
        raise ValidationError("result must be an object")
    _check(obj.get("schema") == RESULT_SCHEMA, "schema must be %r" % RESULT_SCHEMA)
    status = obj.get("status")
    _check(status in STATUSES, "status must be one of %r" % (STATUSES,))
    reason = obj.get("termination_reason")
    _check(reason in TERMINATION_REASONS, "termination_reason must be one of %r" % (TERMINATION_REASONS,))
    _check(obj.get("output_state") in OUTPUT_STATES, "output_state invalid")
    _check(obj.get("evidence_state") in EVIDENCE_STATES, "evidence_state invalid")
    _check(isinstance(obj.get("errors", []), list), "errors must be a list")
    for e in obj.get("errors", []):
        _check(isinstance(e, dict) and e.get("scope") in ERROR_SCOPES, "error must have a valid scope")
        _check(isinstance(e.get("message", ""), str), "error message must be a string")
    _check(isinstance(obj.get("request_id"), str) and obj["request_id"], "request_id is required")
    _check(isinstance(obj.get("work_unit_id"), str) and obj["work_unit_id"], "work_unit_id is required")
    _check(isinstance(obj.get("provider_id"), str) and obj["provider_id"], "provider_id is required")
    if request is not None:
        _check(obj.get("request_id") == request.get("request_id"), "request_id mismatch with request")
        _check(obj.get("work_unit_id") == request.get("work_unit_id"), "work_unit_id mismatch with request")

    started = obj.get("started_utc")
    completed = obj.get("completed_utc")
    terminated = obj.get("terminated_utc")
    exit_code = obj.get("exit_code")
    mechanism = obj.get("termination_mechanism")
    errors = obj.get("errors", [])
    has = lambda scope: any(e.get("scope") == scope for e in errors)

    if status == "SUCCEEDED":
        _check(exit_code == 0, "SUCCEEDED requires exit_code == 0")
        _check(started is not None, "SUCCEEDED requires started_utc")
        _check(completed is not None, "SUCCEEDED requires completed_utc")
        _check(reason == "none", "SUCCEEDED requires termination_reason=none")
        _check(terminated is None, "SUCCEEDED must not have terminated_utc")
    elif status == "FAILED":
        if reason == "start-failed":
            _check(exit_code is None, "start-failed requires exit_code=null")
            _check(started is None, "start-failed requires started_utc=null")
            _check(completed is None and terminated is None, "start-failed requires no completion/termination")
            _check(has("provider"), "start-failed requires a provider error")
        else:
            _check(exit_code is not None and exit_code != 0, "FAILED(ran) requires a non-zero exit_code")
            _check(started is not None, "FAILED(ran) requires started_utc")
            _check(completed is not None, "FAILED(ran) requires completed_utc")
            _check(reason == "none", "FAILED(ran) requires termination_reason=none")
            _check(has("provider"), "FAILED(ran) requires a provider error")
    elif status == "TIMED_OUT":
        _check(reason == "timeout", "TIMED_OUT requires termination_reason=timeout")
        _check(started is not None, "TIMED_OUT requires started_utc")
        _check(terminated is not None, "TIMED_OUT requires terminated_utc")
        _check(completed is None, "TIMED_OUT must not report natural completion")
        _check(mechanism is not None, "TIMED_OUT requires termination_mechanism")
        _check(has("termination"), "TIMED_OUT requires a termination error")
    elif status == "INTERRUPTED":
        _check(reason in ("interrupted", "external"), "INTERRUPTED requires reason=interrupted|external")
        _check(started is not None, "INTERRUPTED requires started_utc")
        _check(terminated is not None, "INTERRUPTED requires terminated_utc (termination evidence)")
        _check(completed is None, "INTERRUPTED must not report natural completion")
        if reason == "interrupted":
            _check(mechanism is not None, "adapter-initiated INTERRUPTED requires termination_mechanism")
        _check(has("termination"), "INTERRUPTED requires a termination error")
    elif status == "UNKNOWN":
        _check(reason == "lost-observability", "UNKNOWN requires termination_reason=lost-observability")
        _check(terminated is None, "UNKNOWN must not have terminated_utc")
        _check(completed is None, "UNKNOWN must not have completed_utc")
        _check(obj.get("evidence_state") != "complete", "UNKNOWN cannot have complete evidence")
        _check(has("observability"), "UNKNOWN requires an observability error")

    os_state = obj.get("output_state")
    out_ref = obj.get("output_ref")
    if os_state == "none":
        _check(out_ref is None, "output_state=none requires output_ref=null")
    elif os_state == "complete":
        _check(out_ref is not None, "output_state=complete requires output_ref")
    elif os_state == "unavailable":
        _check(out_ref is None, "output_state=unavailable requires output_ref=null")
        _check(has("output"), "output unavailable requires an output error")

    ev_state = obj.get("evidence_state")
    ev_ref = obj.get("evidence_ref")
    if ev_state == "complete":
        _check(ev_ref is not None, "evidence_state=complete requires evidence_ref")
    elif ev_state == "unavailable":
        _check(ev_ref is None, "evidence_state=unavailable requires evidence_ref=null")
        _check(has("evidence"), "evidence unavailable requires an evidence error")
    return obj


# ---- ases-usage/1 ----
USAGE_SCHEMA = "ases-usage/1"
USAGE_SOURCES = ("provider-reported", "estimated", "unavailable")
USAGE_COMPLETENESS = ("complete", "partial", "unavailable")
USAGE_CORE = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
USAGE_OPTIONAL = ("thinking_tokens", "total_cost_usd")
USAGE_REQUIRED = ("schema", "request_id", "work_unit_id", "provider_id", "source", "completeness",
                  "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                  "captured_utc")


def _is_nonneg_int(x):
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def _is_nonneg_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0


def validate_usage(obj):
    """Validate an ases-usage/1 token-usage record."""
    if not isinstance(obj, dict):
        raise ValidationError("usage must be an object")
    _check(obj.get("schema") == USAGE_SCHEMA, "schema must be %r" % USAGE_SCHEMA)
    for f in USAGE_REQUIRED:
        _check(f in obj, "required field %r missing" % f)
    _check(isinstance(obj.get("request_id"), str) and obj["request_id"], "request_id is required")
    _check(isinstance(obj.get("work_unit_id"), str) and obj["work_unit_id"], "work_unit_id is required")
    _check(isinstance(obj.get("provider_id"), str) and obj["provider_id"], "provider_id is required")
    _check(isinstance(obj.get("captured_utc"), str) and obj["captured_utc"], "captured_utc is required")

    source = obj.get("source")
    completeness = obj.get("completeness")
    _check(source in USAGE_SOURCES, "source must be one of %r" % (USAGE_SOURCES,))
    _check(completeness in USAGE_COMPLETENESS, "completeness must be one of %r" % (USAGE_COMPLETENESS,))

    # core metrics: non-negative integer or null
    core = {f: obj.get(f) for f in USAGE_CORE}
    for f in USAGE_CORE:
        _check(core[f] is None or _is_nonneg_int(core[f]),
               "%r must be a non-negative integer or null" % f)

    # optional metrics
    thinking = obj.get("thinking_tokens")
    cost = obj.get("total_cost_usd")
    if "thinking_tokens" in obj:
        _check(thinking is None or _is_nonneg_int(thinking), "thinking_tokens must be a non-negative integer or null")
    if "total_cost_usd" in obj:
        _check(cost is None or _is_nonneg_number(cost), "total_cost_usd must be a non-negative number or null")
    if "raw_ref" in obj:
        _check(obj["raw_ref"] is None or (isinstance(obj["raw_ref"], str) and obj["raw_ref"]),
               "raw_ref must be a non-empty string or null")

    non_null = [f for f in USAGE_CORE if core[f] is not None]
    if completeness == "complete":
        _check(len(non_null) == 4, "complete requires all four core metrics non-null")
        _check(source in ("provider-reported", "estimated"),
               "complete usage cannot have source=unavailable")
    elif completeness == "partial":
        _check(0 < len(non_null) < 4, "partial requires at least one (not all) core metric non-null")
        _check(source in ("provider-reported", "estimated"),
               "partial usage cannot have source=unavailable")
    elif completeness == "unavailable":
        _check(len(non_null) == 0, "unavailable requires all core metrics null")
        _check(source == "unavailable", "unavailable usage requires source=unavailable")

    # consistency: source=unavailable implies completeness=unavailable
    if source == "unavailable":
        _check(completeness == "unavailable", "source=unavailable requires completeness=unavailable")

    return obj

