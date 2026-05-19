#!/usr/bin/env python3
"""Build the Locale family — Diantenjeom Sans/Serif {JP / Centered / SC}.

Outputs:
    dist/fonts/diantenjeom-{sans,serif}.{otf,woff2}
    dist/fonts/diantenjeom-{sans,serif}-centered.{otf,woff2}
    dist/fonts/diantenjeom-{sans,serif}-sc.{otf,woff2}
    dist/diantenjeom.css

Pair with `scripts/build_segment.py` (per-group split family) — they
write to different CSS files and don't collide on family names.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diantenjeom.build import DIST, run_build
from diantenjeom.locale_variants import variants


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--sources",
        type=Path,
        default=ROOT / "sources",
        help="Directory containing Noto CJK source fonts.",
    )
    args = parser.parse_args()
    run_build(variants(args.sources), DIST / "diantenjeom.css")


if __name__ == "__main__":
    main()
