"""Claude CLI Adapter for the ASES Agent Provider Contract.

Translates ases-exec-request/1 into a `claude -p` invocation, manages the process
lifecycle (timeout/interruption), and normalizes the outcome into ases-exec-result/1.

This adapter does NOT grant authorization and does NOT prove authorization
authenticity; ASES Core remains the governance authority and performs post-execution
delta/scope verification.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_provider_contract import validation as v  # noqa: E402

PROVIDER_ID = "claude-cli"
ADAPTER_VERSION = "1.0.0"


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class ClaudeCliAdapter:
    def __init__(self, config=None):
        self.config = config or {}
        self.executable = self.config.get("executable", "claude")
        self.timeout_seconds = self.config.get("timeout_seconds", 600)
        self.last_usage = None
        self.last_usage_ref = None

    # ---- discovery ----
    def is_available(self):
        return shutil.which(self.executable) is not None

    def _resolve(self):
        """Resolve the executable to a full path (Windows: .cmd/.exe, not .ps1)."""
        return shutil.which(self.executable) or self.executable

    def version(self):
        if not self.is_available():
            return None
        proc = subprocess.run([self._resolve(), "--version"], capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else None

    def identity(self):
        return {
            "schema": v.PROVIDER_SCHEMA,
            "provider_id": PROVIDER_ID,
            "provider_version": self.version() or "unknown",
            "adapter_version": ADAPTER_VERSION,
            "capabilities": ["non-interactive", "structured-output", "tool-gating", "session-id"],
        }

    # ---- command construction (no subprocess) ----
    def build_command(self, request):
        cfg = request.get("config", {})
        cmd = [self._resolve(), "-p", "--output-format", "json"]
        if cfg.get("model"):
            cmd += ["--model", cfg["model"]]
        if cfg.get("permission_mode"):
            cmd += ["--permission-mode", cfg["permission_mode"]]
        if cfg.get("allowed_tools"):
            cmd += ["--allowedTools"] + list(cfg["allowed_tools"])
        if cfg.get("disallowed_tools"):
            cmd += ["--disallowedTools"] + list(cfg["disallowed_tools"])
        cmd.append(request["instructions"])
        return cmd

    # ---- result construction ----
    def _result(self, request, status, exit_code, started, completed, reason, mechanism,
                output_ref=None, output_state="none", evidence_ref=None, evidence_state="unavailable",
                errors=None, terminated_utc=None, duration=None):
        return {
            "schema": v.RESULT_SCHEMA,
            "request_id": request.get("request_id"),
            "work_unit_id": request.get("work_unit_id"),
            "provider_id": PROVIDER_ID,
            "status": status,
            "exit_code": exit_code,
            "signal": None,
            "started_utc": started,
            "completed_utc": completed,
            "terminated_utc": terminated_utc,
            "termination_reason": reason,
            "termination_mechanism": mechanism,
            "duration_seconds": duration,
            "output_ref": output_ref,
            "output_state": output_state,
            "evidence_ref": evidence_ref,
            "evidence_state": evidence_state,
            "errors": errors or [],
        }

    def _write_output(self, out, err):
        if not out and not err:
            return None
        fd, path = tempfile.mkstemp(prefix="claude-out-", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as f:
            if out:
                f.write("=== stdout ===\n" + out + "\n")
            if err:
                f.write("=== stderr ===\n" + err + "\n")
        return path

    # ---- usage parsing / normalization ----
    @staticmethod
    def _parse_json(text):
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _extract_usage(parsed):
        if isinstance(parsed, dict):
            u = parsed.get("usage")
            if isinstance(u, dict):
                return u
        return None

    @staticmethod
    def _coerce_int(value):
        """Return a non-negative int, or None for anything else (never fabricate)."""
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    @staticmethod
    def _coerce_number(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    def normalize_usage(self, request, provider_output, captured_utc=None, raw_ref=None):
        """Normalize provider JSON output into an ases-usage/1 record (or None)."""
        request_id = request.get("request_id") if isinstance(request, dict) else None
        work_unit_id = request.get("work_unit_id") if isinstance(request, dict) else None
        if not request_id or not work_unit_id:
            return None  # attribution unavailable -> do not fabricate usage evidence

        parsed = self._parse_json(provider_output)
        usage = self._extract_usage(parsed)
        total_cost = parsed.get("total_cost_usd") if parsed is not None else None

        input_tokens = output_tokens = cache_creation = cache_read = thinking = None
        if usage is not None:
            input_tokens = self._coerce_int(usage.get("input_tokens"))
            output_tokens = self._coerce_int(usage.get("output_tokens"))
            cache_creation = self._coerce_int(usage.get("cache_creation_input_tokens"))
            cache_read = self._coerce_int(usage.get("cache_read_input_tokens"))
            details = usage.get("output_tokens_details")
            if isinstance(details, dict):
                thinking = self._coerce_int(details.get("thinking_tokens"))

        core = [input_tokens, output_tokens, cache_creation, cache_read]
        non_null = [x for x in core if x is not None]
        if len(non_null) == 4:
            completeness = "complete"
            source = "provider-reported"
        elif len(non_null) > 0:
            completeness = "partial"
            source = "provider-reported"
        else:
            completeness = "unavailable"
            source = "unavailable"
            thinking = None
            total_cost = None  # do not report optional metrics when no core usage

        record = {
            "schema": v.USAGE_SCHEMA,
            "request_id": request_id,
            "work_unit_id": work_unit_id,
            "provider_id": PROVIDER_ID,
            "source": source,
            "completeness": completeness,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation,
            "cache_read_input_tokens": cache_read,
            "thinking_tokens": thinking,
            "total_cost_usd": self._coerce_number(total_cost),
            "captured_utc": captured_utc or _utcnow(),
            "raw_ref": raw_ref,
        }
        v.validate_usage(record)
        return record

    def persist_usage(self, record):
        if record is None:
            return None
        from token_efficiency import evidence
        return evidence.persist_json(record, kind="usage", name=record.get("request_id") or None)

    def _collect_usage(self, request, out, captured_utc, raw_ref):
        record = self.normalize_usage(request, out, captured_utc=captured_utc, raw_ref=raw_ref)
        self.last_usage = record
        self.last_usage_ref = self.persist_usage(record)
        return record

    # ---- execution lifecycle ----
    def execute(self, request):
        try:
            v.validate_request(request)
        except v.ValidationError as exc:
            return self._result(
                request, "FAILED", None, None, None, "start-failed", None,
                errors=[{"scope": "provider", "category": "invalid-request", "message": str(exc)},
                        {"scope": "evidence", "category": "unavailable", "message": "no process created"}])


        cmd = self.build_command(request)
        wd = request.get("working_directory") or os.getcwd()
        t0 = datetime.datetime.now(datetime.timezone.utc)

        try:
            proc = subprocess.Popen(cmd, cwd=wd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    errors="replace")
        except (FileNotFoundError, OSError) as exc:
            return self._result(
                request, "FAILED", None, None, None, "start-failed", None,
                errors=[{"scope": "provider", "category": "start-failed", "message": str(exc)},
                        {"scope": "evidence", "category": "unavailable", "message": "no process created"}])

        started = _utcnow()
        try:
            out, err = proc.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            terminated = _utcnow()
            output_ref = self._write_output(out, err)
            self._collect_usage(request, out, terminated, output_ref)
            evidence_ref = output_ref
            evidence_state = "partial" if output_ref else "unavailable"
            errs = [{"scope": "termination", "category": "timeout", "message": "timeout after %ss" % self.timeout_seconds}]
            if not output_ref:
                errs.append({"scope": "evidence", "category": "no-output", "message": "no output/evidence captured"})
            return self._result(
                request, "TIMED_OUT", None, started, None, "timeout", "Popen.kill",
                output_ref=output_ref, output_state="partial" if output_ref else "none",
                evidence_ref=evidence_ref, evidence_state=evidence_state,
                errors=errs, terminated_utc=terminated)
        except KeyboardInterrupt:
            proc.terminate()
            out, err = proc.communicate()
            terminated = _utcnow()
            output_ref = self._write_output(out, err)
            self._collect_usage(request, out, terminated, output_ref)
            evidence_ref = output_ref
            evidence_state = "partial" if output_ref else "unavailable"
            errs = [{"scope": "termination", "category": "interrupted", "message": "interrupted"}]
            if not output_ref:
                errs.append({"scope": "evidence", "category": "no-output", "message": "no output/evidence captured"})
            return self._result(
                request, "INTERRUPTED", None, started, None, "interrupted", "Popen.terminate",
                output_ref=output_ref, output_state="partial" if output_ref else "none",
                evidence_ref=evidence_ref, evidence_state=evidence_state,
                errors=errs, terminated_utc=terminated)

        completed = _utcnow()
        duration = round((datetime.datetime.now(datetime.timezone.utc) - t0).total_seconds(), 3)
        exit_code = proc.returncode
        status = "SUCCEEDED" if exit_code == 0 else "FAILED"
        output_ref = self._write_output(out, err)
        self._collect_usage(request, out, completed, output_ref)
        errors = [] if exit_code == 0 else [{"scope": "provider", "category": "non-zero-exit",
                                             "message": (err or out).strip()[:500]}]
        if output_ref:
            output_state = "complete"
            evidence_ref = output_ref
            evidence_state = "complete"
        else:
            output_state = "none"
            evidence_ref = None
            evidence_state = "unavailable"
            errors.append({"scope": "evidence", "category": "no-output", "message": "no output/evidence captured"})
        return self._result(
            request, status, exit_code, started, completed, "none", None,
            output_ref=output_ref, output_state=output_state,
            evidence_ref=evidence_ref, evidence_state=evidence_state,
            errors=errors, duration=duration)
