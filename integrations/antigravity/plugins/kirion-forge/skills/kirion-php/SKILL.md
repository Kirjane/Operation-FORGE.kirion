---
name: kirion-php
description: Use this skill for modern PHP 8.4/8.5 engineering, strict typing, immutable value objects, exact integer minor-unit monetary arithmetic, and Composer lockfile verification.
---

# Kirion PHP Specialization (`kirion-php`)

## 1. Versioned Official References
- PHP 8.4 / 8.5 Language & Type System Reference: `https://www.php.net/manual/en/language.types.php`
- Composer 2.10 Lockfile & Platform Verification: `https://getcomposer.org/doc/04-schema.md`
- PSR-12 Extended Coding Style: `https://www.php-fig.org/psr/psr-12/`

## 2. Concrete Workflow
1. Add `declare(strict_types=1);` to every new PHP domain, action, value-object, and service file.
2. Declare explicit parameter types, property types, and return types; use backed `enum` types for lifecycle states and `readonly` classes for value objects and DTOs.
3. Represent money in exact integer minor units (e.g., centavos/cents as `int`) or arbitrary-precision decimal strings (`bcmath`), never `float`.
4. Verify Composer integrity without mutating `composer.lock` unless dependency updates are explicitly authorized.

## 3. Canonical Example
```php
<?php
declare(strict_types=1);

namespace Kirion\Procurement\Domain;

enum OrderState: string {
    case Draft = 'DRAFT';
    case Approved = 'APPROVED';
    case PartiallyReceived = 'PARTIALLY_RECEIVED';
    case Closed = 'CLOSED';
}

final readonly class MoneyMinor {
    public function __construct(public int $amountMinor, public string $currency = 'PHP') {
        if ($this->currency === '') {
            throw new \InvalidArgumentException('Currency code is required.');
        }
    }
    public function add(self $other): self {
        if ($this->currency !== $other->currency) {
            throw new \DomainException('Cannot add mismatched currencies.');
        }
        return new self($this->amountMinor + $other->amountMinor, $this->currency);
    }
}
```

## 4. Validation Commands
```bash
php --version
composer --version
composer validate --strict
composer check-platform-reqs
php -l src/
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Float Money):** Using `float` (`19.99 * 3`) for invoice or ledger totals causes IEEE-754 rounding drift → rejected by `Antigravity-Nox` (`P1`).
- **Negative Case 2 (Unpinned Lockfile Mutation):** Running `composer update` instead of `composer install --no-interaction --prefer-dist` mutates `composer.lock` outside scope → rejected by ownership guard.
- **Negative Case 3 (Prompt-Injected Composer Scripts):** Executing untrusted `post-install-cmd` scripts without inspecting `composer.json` first → denied by `Antigravity-Aegis`.

## 6. Tests & Qualification Evidence
- Verified in Benchmark A (`benchmarks/php_procurement_inventory/`) and Benchmark C (`BOTH-INCORRECT-ROUNDING`, `PHP-SQL-INJECTION`) with `E5` runtime execution on `PHP 8.4.25`.
