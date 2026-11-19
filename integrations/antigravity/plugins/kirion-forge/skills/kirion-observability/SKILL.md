---
name: kirion-observability
description: Use this skill for structured JSON logging, secret/PII redaction, correlation run IDs, health endpoints, and tamper-evident audit trails.
---

# Kirion Observability & Redaction Specialization (`kirion-observability`)

## 1. Versioned Official References
- OpenTelemetry Logs & Trace Context Specification: `https://opentelemetry.io/docs/specs/otel/`
- OWASP Logging Cheat Sheet: `https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html`

## 2. Concrete Workflow
1. Propagate `run_id`, `mission_id`, and `correlation_id` across every orchestrator stage, HTTP request, and background job.
2. Pass all command outputs, logs, and evidence artifacts through deterministic secret redaction before writing to disk or uploading to GitHub.
3. Redact token prefixes (`ghp_`, `gho_`, `github_pat_`, `sk-`, `Bearer `, `ANTIGRAVITY_CSRF_TOKEN`, connection string passwords) and verify `redacted: true` in every `EvidenceEnvelope`.

## 3. Canonical Example
```python
import re

SECRET_PATTERNS = [
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{8,})\b"),
    re.compile(r"\b(github_pat_[A-Za-z0-9_]{8,})\b"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE),
]

def redact_text(text: str) -> str:
    out = text
    for pat in SECRET_PATTERNS:
        out = pat.sub("[REDACTED_SECRET]", out)
    return out
```

## 4. Validation Commands
```bash
python -m unittest discover -s integrations/antigravity/tests -v
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Unredacted Env Dump):** Running `env` or `printenv` and storing raw token values in an evidence artifact (`SECRET-EXFIL`).
- **Negative Case 2 (Silent Failure Swallowing):** Catching exceptions without recording the failure signature in the journal or audit log.

## 6. Tests & Qualification Evidence
- Verified in F10 Evidence Engine and Benchmark E (`SECRET-EXFIL` denial and redaction verification).
