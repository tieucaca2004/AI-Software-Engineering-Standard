#!/usr/bin/env python3
"""ASES task identity: validation, canonicalization and SHA-256 identity hash.

Implements the frozen Identity Contract (docs/IDENTITY_CONTRACT.md):

- exactly nine identity fields;
- schema_version = 3 is validation-only and is not hashed;
- risk_level and planned_task_id are not part of the identity record;
- strings are NFC-normalized;
- acceptance_criteria is an ordered list (no de-duplication);
- depends_on is an ordered list (NFC first, then de-duplication keeping first occurrence);
- required_capabilities, required_roles and execution_constraints are unordered sets
  (sort + de-duplicate after NFC);
- canonical JSON uses RFC 8785 JCS key ordering for the fixed ASCII keys, UTF-8, no
  insignificant whitespace and no trailing newline;
- validation failures fail closed as INVALID_CANONICAL_TASK.

Standard library only.
"""
import argparse
import hashlib
import json
import sys
import unicodedata

SCHEMA_VERSION = 3

IDENTITY_FIELDS = (
    "title",
    "description",
    "acceptance_criteria",
    "required_capabilities",
    "required_roles",
    "scope",
    "expected_output",
    "execution_constraints",
    "depends_on",
)

STRING_FIELDS = ("title", "description", "scope", "expected_output")
ORDERED_NO_DEDUP = ("acceptance_criteria",)
ORDERED_DEDUP = ("depends_on",)
SET_FIELDS = ("required_capabilities", "required_roles", "execution_constraints")

RECORD_KEYS = frozenset(IDENTITY_FIELDS) | {"schema_version"}


class IdentityError(ValueError):
    """Raised for an invalid task-identity record (fail closed)."""


def canonical_json(obj):
    """RFC 8785 JCS-compatible canonical JSON for the fixed ASCII-key objects used here."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_string(value, where):
    if not isinstance(value, str):
        raise IdentityError("INVALID_CANONICAL_TASK: %s must be a string" % where)
    return unicodedata.normalize("NFC", value)


def _normalize_string_list(value, where):
    if not isinstance(value, list):
        raise IdentityError("INVALID_CANONICAL_TASK: %s must be an array of strings" % where)
    out = []
    for index, item in enumerate(value):
        out.append(_normalize_string(item, "%s[%d]" % (where, index)))
    return out


def _dedup_keep_first(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _normalize_ordered(value, where, dedup):
    items = _normalize_string_list(value, where)
    return _dedup_keep_first(items) if dedup else items


def _normalize_set(value, where):
    items = _normalize_string_list(value, where)
    return sorted(set(items))


def compute_identity_hash(record):
    """Validate an identity record and return its lowercase 64-hex SHA-256 hash."""
    if not isinstance(record, dict):
        raise IdentityError("INVALID_CANONICAL_TASK: identity record must be an object")
    keys = set(record.keys())
    if keys != set(RECORD_KEYS):
        raise IdentityError("INVALID_CANONICAL_TASK: identity record must contain schema_version "
                            "and exactly the nine identity fields")
    if record["schema_version"] != SCHEMA_VERSION:
        raise IdentityError("INVALID_SCHEMA_VERSION: unsupported schema_version %r" %
                            record["schema_version"])

    normalized = {}
    for field in STRING_FIELDS:
        normalized[field] = _normalize_string(record[field], field)
    for field in ORDERED_NO_DEDUP:
        normalized[field] = _normalize_ordered(record[field], field, dedup=False)
    for field in ORDERED_DEDUP:
        normalized[field] = _normalize_ordered(record[field], field, dedup=True)
    for field in SET_FIELDS:
        normalized[field] = _normalize_set(record[field], field)

    payload = {field: normalized[field] for field in IDENTITY_FIELDS}
    canonical = canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_record(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = handle.read()
    if data.startswith("\ufeff"):
        data = data[1:]
    return json.loads(data)


def _cmd_hash(args):
    record = load_record(args.identity)
    print(compute_identity_hash(record))
    return 0


def _cmd_validate(args):
    try:
        record = load_record(args.identity)
        digest = compute_identity_hash(record)
    except (OSError, ValueError) as exc:
        print("INVALID_CANONICAL_TASK: %s" % exc, file=sys.stderr)
        return 1
    print("VALID %s" % digest)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="ases_identity.py",
                                     description="ASES task identity hash (read-only)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("hash", help="print the identity hash")
    p.add_argument("identity", help="path to a task-identity JSON record")
    p.set_defaults(func=_cmd_hash)
    p = sub.add_parser("validate", help="validate a record and print its hash")
    p.add_argument("identity", help="path to a task-identity JSON record")
    p.set_defaults(func=_cmd_validate)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print("INVALID_CANONICAL_TASK: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
