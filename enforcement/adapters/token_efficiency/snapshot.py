"""ases-usage-aggregate/1 snapshot schema and validation."""
SNAPSHOT_SCHEMA = "ases-usage-aggregate/1"
SCOPES = ("work-unit", "request")
STATUSES = ("complete", "partial", "unavailable", "conflicted")
ALGORITHM_VERSION = "1"


class SnapshotError(ValueError):
    pass


def _check(cond, msg):
    if not cond:
        raise SnapshotError(msg)


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0


def validate_snapshot(obj):
    if not isinstance(obj, dict):
        raise SnapshotError("snapshot must be an object")
    _check(obj.get("schema") == SNAPSHOT_SCHEMA, "schema must be %r" % SNAPSHOT_SCHEMA)
    _check(isinstance(obj.get("aggregate_id"), str) and obj["aggregate_id"], "aggregate_id is required")
    _check(isinstance(obj.get("generated_utc"), str) and obj["generated_utc"], "generated_utc is required")
    _check(obj.get("scope") in SCOPES, "scope must be one of %r" % (SCOPES,))
    _check(isinstance(obj.get("work_unit_ids"), list), "work_unit_ids must be a list")
    _check(obj.get("algorithm_version") == ALGORITHM_VERSION, "algorithm_version must be %r" % ALGORITHM_VERSION)
    _check(obj.get("completeness_status") in STATUSES,
           "completeness_status must be one of %r" % (STATUSES,))

    inv = obj.get("request_inventory")
    _check(isinstance(inv, list), "request_inventory must be a list")
    for item in inv:
        _check(isinstance(item, dict), "request_inventory items must be objects")
        _check(isinstance(item.get("request_id"), str) and item["request_id"], "inventory request_id required")
        _check(isinstance(item.get("status"), str) and item["status"] in
               ("complete", "partial", "unavailable", "conflicted"), "inventory status invalid")

    ct = obj.get("complete_totals")
    _check(isinstance(ct, dict), "complete_totals must be an object")
    for k in ("total_input_tokens", "total_output_tokens", "total_tokens"):
        _check(k in ct and (ct[k] is None or _num(ct[k])), "%s must be a non-negative number or null" % k)
    _check("total_cost_usd" in ct and (ct["total_cost_usd"] is None or _num(ct["total_cost_usd"])),
           "total_cost_usd must be a non-negative number or null")
    _check(isinstance(ct.get("request_count"), int) and not isinstance(ct.get("request_count"), bool),
           "request_count must be an int")

    pt = obj.get("partial_unavailable_totals")
    _check(isinstance(pt, dict), "partial_unavailable_totals must be an object")

    conflicts = obj.get("conflicts")
    _check(isinstance(conflicts, list), "conflicts must be a list")
    for c in conflicts:
        _check(isinstance(c, dict) and c.get("request_id"), "conflict must have request_id")

    invalid = obj.get("invalid_inputs")
    _check(isinstance(invalid, list), "invalid_inputs must be a list")

    m3 = obj.get("m3_input")
    _check(isinstance(m3, dict), "m3_input must be an object")
    _check(m3.get("completeness") in ("complete", "partial", "unavailable"),
           "m3_input completeness invalid")
    return obj
