<?php
declare(strict_types=1);
require __DIR__ . '/../src/Stock.php';
function expect_exception(int $stock, int $debit): void {
    try { debit_stock($stock, $debit); }
    catch (DomainException $expected) { return; }
    throw new RuntimeException("hidden negative-oracle rejected: invalid debit accepted");
}
expect_exception(10, -1);
expect_exception(0, -2147483647);
expect_exception(1, 2);
if (debit_stock(4, 4) !== 0) { throw new RuntimeException("total sale mismatch"); }
echo "hidden PASS\n";
