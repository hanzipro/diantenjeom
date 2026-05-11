#!/usr/bin/env python3
"""Thin shim so `npm run build` works without installing the package."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diantenjeom.build import main

if __name__ == "__main__":
    main()
