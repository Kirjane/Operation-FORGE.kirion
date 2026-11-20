<?php
declare(strict_types=1);
// Synthetic benchmark: hidden seeded defect permits negative stock debits.
function debit_stock(int $available, int $debit): int {
    if ($debit > $available) {
        throw new DomainException("insufficient");
    }
    return $available - $debit;
}
