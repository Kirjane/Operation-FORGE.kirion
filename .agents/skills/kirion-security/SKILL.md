---
name: kirion-security
description: Review trust boundaries, role/tenant authorization, secrets, sensitive data, concurrency, replay, retained-data changes and recovery with negative tests.
---

# Security boundaries
Identify actor, resource owner, trust entrypoint, backend authorization, storage, data retention and irreversible operations. Hidden UI is not access control; do not remove hidden MFA/audit middleware while simplifying navigation.
Test unauthorized role/office/tenant/supplier/ID access, path traversal, replay, idempotency, race/TOCTOU, secret exposure, tamper, failure/rollback and migration effects as applicable. Record real negative results, not projected proof.
For HIGH-protected/CRITICAL work honor current project's nonauthor pre-integration review and exact-source clearance. Do not grant permissions or make production mutations to ease testing. Report confirmed violations with smallest safe correction.
