"""Durable ASES evidence storage with content-hash integrity.

Evidence is stored outside ephemeral temporary storage in a configurable evidence
directory (env ASES_EVIDENCE_DIR, default ~/.ases/evidence). Each persisted JSON gets a
`.sha256` sidecar so accidental corruption can be detected on retrieval.

The hash is an integrity check only — it is NOT proof of authenticity or protection
against a privileged attacker.
"""
import hashlib
import json
import os

EVIDENCE_DIR_ENV = "ASES_EVIDENCE_DIR"


def default_evidence_dir():
    env = os.environ.get(EVIDENCE_DIR_ENV)
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".ases", "evidence")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _safe_name(text):
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in text)


def persist_json(record, evidence_dir=None, kind="evidence", name=None):
    """Persist a JSON record durably; returns the stable file path. Writes a .sha256 sidecar."""
    evidence_dir = evidence_dir or default_evidence_dir()
    kind_dir = os.path.join(evidence_dir, kind)
    os.makedirs(kind_dir, exist_ok=True)

    if name is None:
        name = _safe_name(str(record.get("aggregate_id") or record.get("request_id") or "record"))
    else:
        name = _safe_name(name)

    payload = json.dumps(record, indent=2, sort_keys=True).encode("utf-8")
    digest = sha256_bytes(payload)
    path = os.path.join(kind_dir, name + ".json")

    # never overwrite unrelated evidence with different content
    if os.path.exists(path):
        with open(path, "rb") as f:
            existing = sha256_bytes(f.read())
        if existing != digest:
            path = os.path.join(kind_dir, name + "-" + digest[:8] + ".json")

    with open(path, "wb") as f:
        f.write(payload)
    with open(path + ".sha256", "w", encoding="utf-8") as f:
        f.write(digest)
    return path


def load_json(ref, validator=None):
    """Load + verify content hash (+ optional validate). Raises on missing/corrupt/invalid."""
    if not os.path.exists(ref):
        raise FileNotFoundError("evidence not found: %s" % ref)
    with open(ref, "rb") as f:
        data = f.read()
    sidecar = ref + ".sha256"
    if os.path.exists(sidecar):
        with open(sidecar, "r", encoding="utf-8") as f:
            expected = f.read().strip()
        actual = sha256_bytes(data)
        if expected != actual:
            raise ValueError("evidence hash mismatch (corrupted): %s" % ref)
    record = json.loads(data.decode("utf-8"))
    if validator is not None:
        validator(record)
    return record
