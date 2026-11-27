---
type: concept
domain: quality
status: ACTIVE
authority: knowledge
---
# Naming and Intent

Names encode domain meaning, authority, state, units, lifecycle, and side effects. Good naming reduces the amount of invisible context required to understand code and makes incorrect combinations easier to notice.

## Engineering guidance

The integrated Forge root [AGENTS.md semantic naming rule](../../../AGENTS.md#semantic-naming-and-readability) is the normative authority. This concept explains how to apply it, not a separate policy.

| Delivery-coded or vague name | Stable meaning |
| --- | --- |
| `Phase3Service.cs` | `SupplierSettlementService.cs` |
| `BM2Dashboard.tsx` | `CashReconciliationDashboard.tsx` |
| `R7Layout.tsx` | `ApplicationShell.tsx` |
| `C9Handler` | `EventBookingHandler` |
| `phase2Data` | `inventoryCountRecords` |
| `final-fix-v2` | `order-checkout` |

These are illustrative replacements only: inspect real behavior and ownership before choosing names. Prefer meaningful verbs (`calculateOutstandingBalance`), predicate names (`isShiftOpen`), plural collections (`paymentReceipts`) and units (`timeoutMs`, `amountInCentavos`) when ambiguity exists. C# types/methods normally use PascalCase and locals camelCase; Python uses snake_case; JS/TS uses camelCase for functions/variables and PascalCase for components/types. Match repository filename conventions. Common terms such as ID, URL, HTTP and SQL, short indices and coordinates are fine when clear.

Actual domain states (such as a payment settlement phase), `/api/v1`, ordered database migrations, established protocol versions, framework files such as `Program.cs` and historical evidence labels are not delivery-phase names. A test of a real business lifecycle may use that terminology; a permanent test named after a repair round may not. Do not use a digit-based blanket ban.

Inspect the existing vocabulary and callsites; prefer the canonical component instead of creating phase-suffixed clones. If implementations genuinely coexist (for example, offline and remote settlement), use their real responsibility and document why. Preserve public/serialized contracts and persisted identifiers; report legacy violations without expanding scope. Avoid ornamental abstractions, excessive abbreviations and names longer than necessary.

Before delivery, inspect new paths and identifiers in the actual diff. Reviewers distinguish material intent violations from subjective style; the canonical rule determines the disposition. This is an engineering judgment, not a regex-only exercise.

## Local neighborhood
- [[mesh/quality/Code Quality System]]
- [[mesh/quality/Readability]]
- [[mesh/quality/Reviewability]]
- [[mesh/quality/Maintainability]]
- [[mesh/quality/Stable Interface]]
