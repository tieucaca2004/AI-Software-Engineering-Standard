"""ASES Token Efficiency budget policy representation and validation."""
POLICY_SCHEMA = "ases-budget-policy/1"
SCOPES = ("work-unit", "request")
METRICS = ("tokens", "cost")


class PolicyError(ValueError):
    pass


def _check(cond, msg):
    if not cond:
        raise PolicyError(msg)


def _is_nonneg_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0


def validate_policy(obj):
    if not isinstance(obj, dict):
        raise PolicyError("policy must be an object")
    _check(obj.get("schema") == POLICY_SCHEMA, "schema must be %r" % POLICY_SCHEMA)
    _check(isinstance(obj.get("policy_id"), str) and obj["policy_id"], "policy_id is required")
    _check(isinstance(obj.get("policy_version"), str) and obj["policy_version"], "policy_version is required")
    _check(obj.get("scope") in SCOPES, "scope must be one of %r" % (SCOPES,))
    _check(obj.get("metric") in METRICS, "metric must be one of %r" % (METRICS,))
    warn = obj.get("warning_threshold")
    block = obj.get("block_threshold")
    _check(warn is None or _is_nonneg_number(warn), "warning_threshold must be a non-negative number or null")
    _check(block is None or _is_nonneg_number(block), "block_threshold must be a non-negative number or null")
    _check(warn is not None or block is not None, "at least one of warning_threshold/block_threshold is required")
    if warn is not None and block is not None:
        _check(warn <= block, "warning_threshold must be <= block_threshold")
    return obj


def total_tokens_from_usage(usage):
    """Sum the four core metrics of an ases-usage/1 record (additive categories)."""
    core = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    vals = [usage.get(k) for k in core if isinstance(usage.get(k), int) and not isinstance(usage.get(k), bool)]
    return sum(vals) if vals else None
