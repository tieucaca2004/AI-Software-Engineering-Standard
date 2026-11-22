"""Budget workflow CLI: evaluate usage against policy and persist decision evidence.

Procedural workflow control (NOT an ASES Core hard gate):
    evaluate -> persist ases-budget-decision/1 -> exit code drives admission.

Exit codes: 0 = admit (ALLOW/WARN), 1 = BLOCK, 2 = UNAVAILABLE, 3 = error.
"""
import argparse
import json
import sys

from . import decision as D
from . import evaluator as E


def _load(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _persist(record, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    return path


def run(policy_path, usage_path, output_path, policy_ref=None):
    try:
        policy = _load(policy_path)
        usage = _load(usage_path)
        record = E.evaluate(policy, usage, policy_ref=policy_ref)
        D.validate_decision(record)
        _persist(record, output_path)
        return record
    except Exception as exc:  # noqa: BLE001 - surface as UNAVAILABLE, never ALLOW
        return {
            "schema": D.DECISION_SCHEMA, "decision_id": "error", "evaluated_utc": E._utcnow(),
            "scope": "work-unit", "work_unit_id": "unknown", "decision": "UNAVAILABLE",
            "reason": "evaluator error: %s" % exc, "policy_ref": policy_ref or "unknown",
            "policy_version": "unknown", "metric": "tokens", "measured_value": None,
            "warning_threshold": None, "block_threshold": None, "usage_refs": [],
            "admits_next": False, "override": None,
        }


def main(argv=None):
    ap = argparse.ArgumentParser(description="ASES Token Efficiency budget evaluator")
    ap.add_argument("--policy", required=True, help="budget policy JSON path")
    ap.add_argument("--usage", required=True, help="prepared usage input JSON path")
    ap.add_argument("--policy-ref", default=None, help="policy reference for traceability")
    ap.add_argument("--output", required=True, help="decision evidence output path")
    args = ap.parse_args(argv)

    record = run(args.policy, args.usage, args.output, policy_ref=args.policy_ref)
    print(json.dumps(record, indent=2))
    decision = record.get("decision")
    if decision == "UNAVAILABLE":
        return 2
    if decision == "BLOCK":
        return 1
    if decision in ("ALLOW", "WARN"):
        return 0
    return 3


if __name__ == "__main__":
    sys.exit(main())
