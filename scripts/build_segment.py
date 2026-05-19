#!/usr/bin/env python3
"""Build the Segment family — Diantenjeom Sans/Serif per-group faces.

Eight groups per style × 2 styles = 16 faces:
    Joiner / Curly / Dot {Anchored, Centered} / Bracket /
    Mark {Centered, Centered Rotated, Anchored}

Outputs:
    dist/fonts/diantenjeom-{sans,serif}-{group}.{otf,woff2}
    dist/diantenjeom-segment.css

Pair with `scripts/build_locale.py` (Locale family) — they write to
different CSS files and don't share family names.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diantenjeom.build import DIST, run_build
from diantenjeom.segment_variants import variants


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--sources",
        type=Path,
        default=ROOT / "sources",
        help="Directory containing Noto CJK source fonts.",
    )
    args = parser.parse_args()
    run_build(variants(args.sources), DIST / "diantenjeom-segment.css")


if __name__ == "__main__":
    main()
