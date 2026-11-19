---
name: kirion-laravel-security
description: Use this skill for PHP/Laravel security hardening, cross-tenant IDOR prevention, object-level Policy/Gate authorization, mass-assignment defense, CSRF/Sanctum, and safe file upload validation.
---

# Kirion Laravel Security Specialization (`kirion-laravel-security`)

## 1. Versioned Official References
- Laravel Authorization (Policies & Gates): `https://laravel.com/docs/authorization`
- OWASP Top 10 / Broken Access Control & Injection: `https://owasp.org/Top10/`
- Laravel File Storage & Upload Validation: `https://laravel.com/docs/filesystem`

## 2. Concrete Workflow
1. Enforce tenant (`tenant_id`) and role (`requester`, `approver`, `stock_clerk`, `auditor`) checks at the backend enforcement layer on every route, queued job, and action.
2. Never trust client-supplied `tenant_id`, `role`, `status`, or `approved_by` fields in request payloads.
3. Validate uploaded files by server-inspected MIME magic bytes, strict extension allowlist, maximum byte size, and non-executable private storage path outside the public web root.
4. Escape all rendered output and bind all SQL parameters.

## 3. Canonical Example
```php
<?php
declare(strict_types=1);

namespace App\Security;

final class TenantPolicyGuard {
    public static function assertCanApprove(array $actor, array $po): void {
        if ((int)$actor['tenant_id'] !== (int)$po['tenant_id']) {
            throw new AccessDeniedException('Cross-tenant access denied (IDOR guard).', 403);
        }
        if ($actor['role'] !== 'approver') {
            throw new AccessDeniedException('Role is not authorized to approve purchase orders.', 403);
        }
        if ((int)$actor['user_id'] === (int)$po['requester_id']) {
            throw new AccessDeniedException('Segregation of duties: requester cannot self-approve.', 403);
        }
    }
}
```

## 4. Validation Commands
```bash
composer audit
php artisan test --filter=SecurityAndTenantIsolationTest
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Cross-Tenant IDOR):** Looking up a Purchase Order by `id` alone (`find($id)`) without verifying `tenant_id === $actor->tenant_id` → `P0`/`P1` defect.
- **Negative Case 2 (Mass Assignment Privilege Escalation):** Allowing request payload `{"status": "APPROVED", "tenant_id": 2}` to overwrite protected columns.
- **Negative Case 3 (Unsafe File Upload):** Saving uploaded filename directly to `public/uploads/$filename` allowing `.php` or path traversal `../`.

## 6. Tests & Qualification Evidence
- Verified in Benchmark A (cross-tenant A/B denial and role matrix) and Benchmark C (`LARAVEL-IDOR`, `LARAVEL-MASS-ASSIGNMENT`, `UNSAFE-FILE-UPLOAD`).
