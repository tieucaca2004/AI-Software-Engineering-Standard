"""Deterministic usage aggregation and conflict handling (M4).

Consumes normalized ases-usage/1 records (with evidence references), deduplicates by
request_id, handles partial→complete replacement, detects conflicting complete records,
and produces an ases-usage-aggregate/1 snapshot with three separate aggregate classes.

This module does NOT implement budget policy or decision logic (M3 owns that).
"""
import datetime
import json
import uuid

from . import snapshot as S

CORE = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
OPTIONAL = ("thinking_tokens", "total_cost_usd")


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 else None


def usage_signature(record):
    """Deterministic identity of a record's usage values + attribution (for comparison)."""
    return tuple([record.get("request_id"), record.get("work_unit_id"), record.get("provider_id")]
                 + [record.get(k) for k in CORE] + [record.get(k) for k in OPTIONAL])


def differing_fields(a, b):
    return [f for f in CORE + OPTIONAL if a.get(f) != b.get(f)]


def record_ref(record):
    return record.get("raw_ref") if isinstance(record.get("raw_ref"), str) else None


def validate_scope(scope):
    if not isinstance(scope, dict):
        raise ValueError("scope must be an object")
    if scope.get("scope") == "work-unit":
        if not scope.get("work_unit_id"):
            raise ValueError("work-unit scope requires work_unit_id")
    elif scope.get("scope") == "request":
        if not scope.get("request_id"):
            raise ValueError("request scope requires request_id")
    else:
        raise ValueError("scope.scope must be 'work-unit' or 'request'")
    return scope


def _in_scope(record, scope):
    if scope["scope"] == "work-unit":
        return record.get("work_unit_id") == scope.get("work_unit_id")
    return record.get("request_id") == scope.get("request_id")


def resolve_request(records):
    """Resolve one request_id group into (status, record, conflict_fields)."""
    completes = [r for r in records if r.get("completeness") == "complete"]

    if not completes:
        # no complete record -> partial/unavailable; choose a partial over unavailable
        chosen = next((r for r in records if r.get("completeness") == "partial"), records[0])
        return chosen.get("completeness"), chosen, []

    base_sig = usage_signature(completes[0])
    for c in completes[1:]:
        if usage_signature(c) != base_sig:
            return "conflicted", None, differing_fields(completes[0], c)

    # identical completes -> dedup (partials are replaced by the complete)
    return "complete", completes[0], []


def request_totals(record):
    """Additive totals for a single complete record (thinking/cache not double-counted)."""
    vals = {k: _num(record.get(k)) for k in CORE}
    total_input = None
    if all(vals[k] is not None for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")):
        total_input = vals["input_tokens"] + vals["cache_creation_input_tokens"] + vals["cache_read_input_tokens"]
    total_output = vals["output_tokens"]
    total_tokens = (total_input + total_output) if (total_input is not None and total_output is not None) else None
    return {"total_input_tokens": total_input, "total_output_tokens": total_output, "total_tokens": total_tokens}


def aggregate(records, scope, aggregate_id=None):
    """Aggregate scoped (record, ref) pairs into an ases-usage-aggregate/1 snapshot."""
    validate_scope(scope)
    records = list(records)

    invalid_inputs = []
    valid = []
    for item in records:
        rec, ref = (item if isinstance(item, tuple) else (item, None))
        try:
            if not isinstance(rec, dict) or rec.get("schema") != "ases-usage/1":
                raise ValueError("not an ases-usage/1 record")
            # validate via the accepted validator (imported lazily to avoid cycle)
            from agent_provider_contract import validation as uv
            uv.validate_usage(rec)
            valid.append((rec, ref))
        except Exception as exc:  # noqa: BLE001 - preserve explicit diagnostic
            invalid_inputs.append({"ref": ref, "error": str(exc)})

    scoped = [(r, f) for (r, f) in valid if _in_scope(r, scope)]

    # group by request_id
    groups = {}
    for rec, ref in scoped:
        rid = rec.get("request_id")
        groups.setdefault(rid, []).append((rec, ref))

    resolved = {}
    conflicts = []
    request_inventory = []
    for rid, group in groups.items():
        recs = [r for (r, _f) in group]
        refs = [f for (_r, f) in group if f]
        status, record, diff_fields = resolve_request(recs)
        resolved[rid] = {"status": status, "record": record, "refs": refs}
        request_inventory.append({
            "request_id": rid,
            "work_unit_id": recs[0].get("work_unit_id"),
            "provider_id": recs[0].get("provider_id"),
            "status": status,
            "refs": refs,
        })
        if status == "conflicted":
            conflicts.append({
                "request_id": rid,
                "work_unit_id": recs[0].get("work_unit_id"),
                "differing_fields": diff_fields,
                "refs": refs,
            })

    # three aggregate classes
    complete_totals = {"total_input_tokens": 0, "total_output_tokens": 0, "total_tokens": 0,
                       "total_cost_usd": None, "request_count": 0}
    partial_unavailable_totals = {"total_input_tokens": 0, "total_output_tokens": 0, "total_tokens": 0,
                                  "total_cost_usd": None, "request_count": 0}

    cost_sum = None
    for rid, res in resolved.items():
        if res["status"] == "complete" and res["record"] is not None:
            t = request_totals(res["record"])
            complete_totals["total_input_tokens"] += t["total_input_tokens"]
            complete_totals["total_output_tokens"] += t["total_output_tokens"]
            complete_totals["total_tokens"] += t["total_tokens"]
            complete_totals["request_count"] += 1
            c = _num(res["record"].get("total_cost_usd"))
            if c is not None:
                cost_sum = (cost_sum or 0.0) + c
        elif res["status"] in ("partial", "unavailable") and res["record"] is not None:
            t = request_totals(res["record"])
            partial_unavailable_totals["total_input_tokens"] += (t["total_input_tokens"] or 0)
            partial_unavailable_totals["total_output_tokens"] += (t["total_output_tokens"] or 0)
            partial_unavailable_totals["total_tokens"] += (t["total_tokens"] or 0)
            partial_unavailable_totals["request_count"] += 1
    complete_totals["total_cost_usd"] = cost_sum

    # completeness status + M3 input (never claim complete with any incompleteness/conflict)
    if conflicts:
        completeness_status = "conflicted"
    elif invalid_inputs:
        completeness_status = "partial"
    elif not groups:
        completeness_status = "unavailable"
    elif any(res["status"] != "complete" for res in resolved.values()):
        completeness_status = "partial"
    else:
        completeness_status = "complete"

    m3_completeness = {"complete": "complete", "partial": "partial",
                       "unavailable": "unavailable", "conflicted": "partial"}[completeness_status]
    m3_input = {
        "scope": scope["scope"],
        "work_unit_id": scope.get("work_unit_id"),
        "completeness": m3_completeness,
        "total_tokens": complete_totals["total_tokens"] if completeness_status == "complete" else None,
        "total_cost_usd": complete_totals["total_cost_usd"] if completeness_status == "complete" else None,
        "evidence_refs": sorted({r for res in resolved.values() for r in res["refs"] if r}),
    }

    work_unit_ids = sorted({_r.get("work_unit_id") for (_r, _f) in scoped if _r.get("work_unit_id")})

    return {
        "schema": S.SNAPSHOT_SCHEMA,
        "aggregate_id": aggregate_id or str(uuid.uuid4()),
        "generated_utc": _utcnow(),
        "scope": scope["scope"],
        "work_unit_ids": work_unit_ids,
        "algorithm_version": S.ALGORITHM_VERSION,
        "request_inventory": request_inventory,
        "complete_totals": complete_totals,
        "partial_unavailable_totals": partial_unavailable_totals,
        "conflicts": conflicts,
        "invalid_inputs": invalid_inputs,
        "completeness_status": completeness_status,
        "m3_input": m3_input,
    }


def read_usage_files(paths):
    """Read a list of ases-usage/1 JSON files -> (records, invalid) where records are (record, path)."""
    records = []
    invalid = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            records.append((data, p))
        except Exception as exc:  # noqa: BLE001
            invalid.append({"ref": p, "error": str(exc)})
    return records, invalid


def persist_snapshot(snapshot, path=None, evidence_dir=None):
    """Persist a snapshot durably (with .sha256 sidecar); `path=None` uses the evidence dir."""
    from . import evidence
    if path is None:
        return evidence.persist_json(snapshot, evidence_dir=evidence_dir, kind="aggregate")
    payload = json.dumps(snapshot, indent=2, sort_keys=True).encode("utf-8")
    with open(path, "wb") as f:
        f.write(payload)
    with open(path + ".sha256", "w", encoding="utf-8") as f:
        f.write(evidence.sha256_bytes(payload))
    return path
