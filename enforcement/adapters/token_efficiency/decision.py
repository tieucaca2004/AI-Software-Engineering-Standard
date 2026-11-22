"""ases-budget-decision/1 schema and validation."""
DECISION_SCHEMA = "ases-budget-decision/1"
DECISIONS = ("ALLOW", "WARN", "BLOCK", "UNAVAILABLE")
METRICS = ("tokens", "cost")
SCOPES = ("work-unit", "request")


class DecisionError(ValueError):
    pass


def _check(cond, msg):
    if not cond:
        raise DecisionError(msg)


def _is_nonneg_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0


def validate_decision(obj):
    if not isinstance(obj, dict):
        raise DecisionError("decision must be an object")
    _check(obj.get("schema") == DECISION_SCHEMA, "schema must be %r" % DECISION_SCHEMA)
    _check(isinstance(obj.get("decision_id"), str) and obj["decision_id"], "decision_id is required")
    _check(isinstance(obj.get("evaluated_utc"), str) and obj["evaluated_utc"], "evaluated_utc is required")
    _check(obj.get("scope") in SCOPES, "scope must be one of %r" % (SCOPES,))
    _check(isinstance(obj.get("work_unit_id"), str) and obj["work_unit_id"], "work_unit_id is required")
    _check(obj.get("decision") in DECISIONS, "decision must be one of %r" % (DECISIONS,))
    _check(isinstance(obj.get("reason"), str) and obj["reason"], "reason is required")
    _check(isinstance(obj.get("policy_ref"), str) and obj["policy_ref"], "policy_ref is required")
    _check(isinstance(obj.get("policy_version"), str) and obj["policy_version"], "policy_version is required")
    _check(obj.get("metric") in METRICS, "metric must be one of %r" % (METRICS,))
    _check(isinstance(obj.get("admits_next"), bool), "admits_next must be a bool")

    mv = obj.get("measured_value")
    _check(mv is None or _is_nonneg_number(mv), "measured_value must be a non-negative number or null")
    for key in ("warning_threshold", "block_threshold"):
        v = obj.get(key)
        _check(v is None or _is_nonneg_number(v), "%s must be a non-negative number or null" % key)

    if "usage_refs" in obj:
        _check(isinstance(obj["usage_refs"], list), "usage_refs must be a list")

    decision = obj["decision"]
    override = obj.get("override")
    if override is not None:
        _check(isinstance(override, dict), "override must be an object or null")
        _check(isinstance(override.get("authorized_by"), str) and override["authorized_by"],
               "override.authorized_by is required")
        _check(isinstance(override.get("scope"), str) and override["scope"], "override.scope is required")

    # admits_next consistency: ALLOW/WARN always admit; BLOCK/UNAVAILABLE admit only via override
    if decision in ("ALLOW", "WARN"):
        _check(obj["admits_next"] is True, "%s must admit the next Work Unit" % decision)
    else:
        if obj["admits_next"] is True:
            _check(override is not None, "%s requires an explicit override to admit" % decision)
        else:
            _check(override is None, "a non-admitting decision must not carry an override")
    return obj
