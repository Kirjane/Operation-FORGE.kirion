"""Local demonstration runner for synthetic R2-B cases only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .verifier import evaluate_fixture, InvalidClaim

HERE = Path(__file__).resolve().parent
NAMES = (
    "r2a-red-cafe", "r2a-green-cafe", "r2a-red-talibon",
    "r2a-green-talibon", "r2a-red-retail", "r2a-green-retail",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic-only Forge R2-B claim evaluator")
    parser.add_argument("--fixture", choices=NAMES, help="One synthetic fixture; default all six")
    parser.add_argument("--mode", choices=("synthetic", "live"), default="synthetic")
    args = parser.parse_args()
    for name in ([args.fixture] if args.fixture else NAMES):
        source = HERE / "fixtures" / (name + ".json")
        case = json.loads(source.read_text(encoding="utf-8"))
        try:
            result = evaluate_fixture(case, mode=args.mode)
        except InvalidClaim as exc:
            print(json.dumps({"fixture": name, "error": "INVALID_CLAIM", "detail": str(exc)}))
            return 2
        print(json.dumps({"fixture": name, **result.as_dict()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
