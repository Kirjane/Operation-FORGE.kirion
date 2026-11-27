<?php
declare(strict_types=1);
require __DIR__ . '/../src/Stock.php';
function must_be(bool $condition): void {
    if (!$condition) { throw new RuntimeException("public oracle failed"); }
}
must_be(debit_stock(10, 2) === 8);
must_be(debit_stock(10, 0) === 10);
try { debit_stock(2, 3); throw new RuntimeException("oversell accepted"); }
catch (DomainException $expected) { /* correct */ }
echo "public PASS\n";
