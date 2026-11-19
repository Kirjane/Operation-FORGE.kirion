---
name: kirion-api
description: Use this skill for REST/HTTP API contract design, strict request schema validation, status-code semantics, pagination, Problem Details error envelopes, and backward compatibility.
---

# Kirion API Engineering Specialization (`kirion-api`)

## 1. Versioned Official References
- RFC 9457 Problem Details for HTTP APIs: `https://www.rfc-editor.org/rfc/rfc9457`
- RFC 9110 HTTP Semantics: `https://www.rfc-editor.org/rfc/rfc9110`

## 2. Concrete Workflow
1. Version API routes explicitly (`/api/v1/...`) and validate content types, required fields, numeric scales, and enum values before invoking domain logic.
2. Return precise HTTP status codes: `200 OK` / `201 Created` for success, `400`/`422` for validation failure, `401` for unauthenticated, `403` for role or cross-tenant denial, `404` for missing resource within tenant, `409 Conflict` for invalid state transition or concurrency conflict.
3. Enforce bounded pagination (`limit <= 100`) on all collection endpoints.

## 3. Canonical Example
```json
{
  "type": "https://kirion-forge.local/problems/invalid-state-transition",
  "title": "Invalid State Transition",
  "status": 409,
  "detail": "Payment PAY-1002 is already REVERSED and cannot be reversed again.",
  "instance": "/api/v1/payments/PAY-1002/reverse"
}
```

## 4. Validation Commands
```bash
python -m unittest discover -s integrations/antigravity/tests -v
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (200 OK on Error):** Returning HTTP `200` with `{"error": "access denied"}` instead of HTTP `403`.
- **Negative Case 2 (Stack Trace Leakage):** Emitting raw SQL queries, file paths, or exception stack traces in production HTTP error responses.

## 6. Tests & Qualification Evidence
- Verified in Benchmark A and Benchmark B over real HTTP sockets with positive and negative status-code assertions.
