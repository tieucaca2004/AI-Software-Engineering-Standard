"""Usage aggregation workflow CLI (M4).

Reads ases-usage/1 evidence files, aggregates deterministically, persists an
ases-usage-aggregate/1 snapshot, and optionally writes the M3-prepared input.
"""
import argparse
import json
import sys

from . import aggregator as A


def main(argv=None):
    ap = argparse.ArgumentParser(description="ASES Token Efficiency usage aggregator")
    ap.add_argument("--usage-files", required=True, nargs="+", help="ases-usage/1 JSON evidence files")
    ap.add_argument("--scope", required=True, choices=["work-unit", "request"])
    ap.add_argument("--work-unit-id", default=None, help="required when scope=work-unit")
    ap.add_argument("--request-id", default=None, help="required when scope=request")
    ap.add_argument("--output", default=None, help="aggregate snapshot output path (default: evidence dir)")
    ap.add_argument("--m3-output", default=None, help="optional prepared M3 input output path")
    ap.add_argument("--evidence-dir", default=None, help="evidence directory override")
    args = ap.parse_args(argv)

    scope = {"scope": args.scope}
    if args.scope == "work-unit":
        scope["work_unit_id"] = args.work_unit_id
    else:
        scope["request_id"] = args.request_id

    records, read_invalid = A.read_usage_files(args.usage_files)
    snapshot = A.aggregate(records, scope)
    for inv in read_invalid:
        if inv not in snapshot["invalid_inputs"]:
            snapshot["invalid_inputs"].append(inv)

    if args.output is None:
        snapshot_ref = A.persist_snapshot(snapshot, evidence_dir=args.evidence_dir)
    else:
        snapshot_ref = A.persist_snapshot(snapshot, path=args.output)
    if args.m3_output:
        with open(args.m3_output, "w", encoding="utf-8") as f:
            json.dump(snapshot["m3_input"], f, indent=2)
    print(json.dumps({"snapshot_ref": snapshot_ref, "snapshot": snapshot}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
