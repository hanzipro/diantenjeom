#!/usr/bin/env python3
"""Pair-squeeze regression check.

Drives `demo/squeeze-matrix.html` with headless Chrome across every shipped
variant × style × writing-mode (KV horizontal excluded — KV is vertical-only),
measuring whether each punctuation pair gets squeezed by `text-spacing-trim`.

This is a *characterisation* (snapshot) test: it records which pairs squeeze
(and by how much, in em) into `tests/squeeze-snapshot.json`. Pairs absent from
the snapshot are the negative cases (they must NOT squeeze). Re-running compares
against the snapshot and fails on any drift; `--update` rewrites the snapshot
after a human has eyeballed the result.

Chrome-only by design (simpler than Playwright, no extra deps). The probe page
is browser-agnostic, so the same HTML can later be opened in Safari/Firefox —
or driven by Playwright — without changes.

    python scripts/check_squeeze.py            # check against snapshot
    python scripts/check_squeeze.py --update   # regenerate snapshot
"""

from __future__ import annotations

import argparse
import functools
import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
SNAPSHOT = ROOT / "tests" / "squeeze-snapshot.json"

# 14 configs: jis/moe/gb in both directions, kv vertical-only.
CONFIGS: list[tuple[str, str, str]] = [
    (v, s, d)
    for v in ("jis", "moe", "gb", "kv")
    for s in ("sans", "serif")
    for d in ("h", "v")
    if not (v == "kv" and d == "h")
]

RESULT_RE = re.compile(r'<pre id="RESULT">(.*?)</pre>', re.DOTALL)


def find_chrome() -> str:
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ]
    for c in candidates:
        if "/" in c:
            if Path(c).exists():
                return c
        elif shutil.which(c):
            return c
    raise SystemExit("Chrome not found; set CHROME=/path/to/chrome")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs):  # silence per-request logging
        pass


def sync_demo() -> None:
    """Mirror dist/ CSS + fonts into demo/ so the probe page tests the freshly
    built output, not a stale `pnpm sync:demo` copy. No-op if dist/ is absent."""
    css = ROOT / "dist" / "diantenjeom.css"
    fonts = ROOT / "dist" / "fonts"
    if css.exists():
        shutil.copy(css, DEMO / "diantenjeom.css")
    if fonts.exists():
        dst = DEMO / "fonts"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(fonts, dst)
        print("synced demo/ from dist/")


def start_server() -> tuple[ThreadingHTTPServer, int]:
    handler = functools.partial(QuietHandler, directory=str(DEMO))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def run_config(chrome: str, port: int, variant: str, style: str, dir_: str) -> dict:
    url = (
        f"http://127.0.0.1:{port}/squeeze-matrix.html"
        f"?variant={variant}&style={style}&dir={dir_}"
    )
    out = subprocess.run(
        [
            chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--virtual-time-budget=15000",
            "--run-all-compositor-stages-before-draw",
            "--dump-dom", url,
        ],
        capture_output=True, text=True, timeout=120,
    ).stdout
    m = RESULT_RE.search(out)
    if not m:
        raise SystemExit(f"no RESULT for {variant}/{style}/{dir_} (page did not finish?)")
    return json.loads(html.unescape(m.group(1)))


def collect(chrome: str, port: int) -> dict:
    snapshot: dict[str, dict] = {}
    for variant, style, dir_ in CONFIGS:
        key = f"{variant}/{style}/{dir_}"
        res = run_config(chrome, port, variant, style, dir_)
        meta, squeeze = res["meta"], res["squeeze"]
        loaded = "" if meta["font_loaded"] else "  ⚠️ FONT NOT LOADED"
        print(f"  {key:16s} squeezed {meta['pairs_squeezed']:3d}"
              f" / {meta['pairs_tested']:4d}{loaded}")
        snapshot[key] = {
            "font_loaded": meta["font_loaded"],
            "pairs_tested": meta["pairs_tested"],
            "pairs_squeezed": meta["pairs_squeezed"],
            "squeeze": dict(sorted(squeeze.items())),
        }
    return snapshot


def diff(old: dict, new: dict) -> int:
    problems = 0
    for key in sorted(set(old) | set(new)):
        if key not in old:
            print(f"❌ {key}: new config not in snapshot")
            problems += 1
            continue
        if key not in new:
            print(f"❌ {key}: config missing from this run")
            problems += 1
            continue
        o, n = old[key]["squeeze"], new[key]["squeeze"]
        added = sorted(set(n) - set(o))
        removed = sorted(set(o) - set(n))
        changed = sorted(p for p in set(o) & set(n) if o[p] != n[p])
        if old[key]["font_loaded"] != new[key]["font_loaded"]:
            print(f"❌ {key}: font_loaded {old[key]['font_loaded']} → {new[key]['font_loaded']}")
            problems += 1
        if added:
            print(f"❌ {key}: now squeezes (was not): {' '.join(added)}")
            problems += len(added)
        if removed:
            print(f"❌ {key}: no longer squeezes: {' '.join(removed)}")
            problems += len(removed)
        for p in changed:
            print(f"❌ {key}: '{p}' amount {o[p]} → {n[p]}")
            problems += 1
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update", action="store_true", help="rewrite the snapshot")
    args = ap.parse_args()

    chrome = find_chrome()
    sync_demo()
    httpd, port = start_server()
    try:
        print(f"Running {len(CONFIGS)} configs via {chrome}")
        current = collect(chrome, port)
    finally:
        httpd.shutdown()

    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)

    if args.update:
        SNAPSHOT.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print(f"\nwrote {SNAPSHOT.relative_to(ROOT)} ({len(current)} configs)")
        return

    if not SNAPSHOT.exists():
        raise SystemExit("no snapshot yet — run with --update first")
    old = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    problems = diff(old, current)
    if problems:
        print(f"\n{problems} difference(s) from snapshot.")
        sys.exit(1)
    print("\n✅ matches snapshot")


if __name__ == "__main__":
    main()
