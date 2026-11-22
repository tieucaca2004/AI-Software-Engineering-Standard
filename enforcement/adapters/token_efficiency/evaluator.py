"""Deterministic budget evaluator for ASES Token Efficiency.

Accepts a validated budget policy and a prepared usage input (usage total/snapshot)
and returns an ases-budget-decision/1 record. It never raises into ALLOW and never
auto-retries UNKNOWN. Partial/unavailable usage cannot drive a definitive budget decision.
"""
import datetime
import uuid

from . import decision as D
from . import policy as P

USAGE_COMPLETENESS = ("complete", "partial", "unavailable")


class UsageInputError(ValueError):
    pass


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _check(cond, msg):
    if not cond:
        raise UsageInputError(msg)


def _is_nonneg_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0


def validate_usage_input(obj):
    """Validate the evaluator's prepared usage-total input contract (M4 supplies this)."""
    if not isinstance(obj, dict):
        raise UsageInputError("usage input must be an object")
    _check(obj.get("scope") in P.SCOPES, "usage input scope must be one of %r" % (P.SCOPES,))
    _check(isinstance(obj.get("work_unit_id"), str) and obj["work_unit_id"], "usage input work_unit_id is required")
    _check(obj.get("completeness") in USAGE_COMPLETENESS,
           "usage input completeness must be one of %r" % (USAGE_COMPLETENESS,))
    tt = obj.get("total_tokens")
    tc = obj.get("total_cost_usd")
    _check(tt is None or _is_nonneg_number(tt), "total_tokens must be a non-negative number or null")
    _check(tc is None or _is_nonneg_number(tc), "total_cost_usd must be a non-negative number or null")
    if "evidence_refs" in obj:
        _check(isinstance(obj["evidence_refs"], list), "evidence_refs must be a list")
    return obj


def _make_decision(policy, usage_input, decision, reason, measured, policy_ref, decision_id=None):
    admits = decision in ("ALLOW", "WARN")
    return {
        "schema": D.DECISION_SCHEMA,
        "decision_id": decision_id or str(uuid.uuid4()),
        "evaluated_utc": _utcnow(),
        "scope": policy.get("scope"),
        "work_unit_id": usage_input.get("work_unit_id"),
        "decision": decision,
        "reason": reason,
        "policy_ref": policy_ref,
        "policy_version": policy.get("policy_version"),
        "metric": policy.get("metric"),
        "measured_value": measured,
        "warning_threshold": policy.get("warning_threshold"),
        "block_threshold": policy.get("block_threshold"),
        "usage_refs": usage_input.get("evidence_refs", []),
        "admits_next": admits,
        "override": None,
    }


def evaluate(policy, usage_input, policy_ref=None, decision_id=None):
    """Return an ases-budget-decision/1 record. Never raises into ALLOW."""
    policy_ref = policy_ref or (policy.get("policy_id") if isinstance(policy, dict) else None)

    try:
        P.validate_policy(policy)
    except P.PolicyError as exc:
        return _make_decision(
            policy if isinstance(policy, dict) else {}, usage_input if isinstance(usage_input, dict) else {},
            "UNAVAILABLE", "invalid budget policy: %s" % exc, None, policy_ref, decision_id)

    try:
        validate_usage_input(usage_input)
    except UsageInputError as exc:
        return _make_decision(policy, usage_input if isinstance(usage_input, dict) else {},
                              "UNAVAILABLE", "invalid usage input: %s" % exc, None, policy_ref, decision_id)

    metric = policy["metric"]
    if metric == "tokens":
        measured = usage_input.get("total_tokens")
        value_label = "total_tokens"
    else:
        measured = usage_input.get("total_cost_usd")
        value_label = "total_cost_usd"

    completeness = usage_input.get("completeness")
    if completeness != "complete" or measured is None:
        return _make_decision(policy, usage_input, "UNAVAILABLE",
                              "cannot determine budget status: usage completeness=%r, %s=%r"
                              % (completeness, value_label, measured),
                              measured, policy_ref, decision_id)

    warn = policy.get("warning_threshold")
    block = policy.get("block_threshold")

    if block is not None and measured >= block:
        return _make_decision(policy, usage_input, "BLOCK",
                              "usage %s (%s=%r) >= block_threshold (%r)"
                              % ("at/above block", value_label, measured, block),
                              measured, policy_ref, decision_id)
    if warn is not None and measured >= warn:
        return _make_decision(policy, usage_input, "WARN",
                              "usage at/above warning_threshold (%r), below block_threshold"
                              % (warn,),
                              measured, policy_ref, decision_id)
    return _make_decision(policy, usage_input, "ALLOW",
                          "usage within budget (%s=%r)" % (value_label, measured),
                          measured, policy_ref, decision_id)
