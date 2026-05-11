"""Fetch pinned Noto CJK Variable Font sources into ./sources/.

Reads `sources/sources.lock.json`, downloads each file from the pinned
notofonts/noto-cjk release tag, and verifies SHA-256.

Modes:
    (default)            verify checksums; fail if any file's hash mismatches
                         or the lockfile has null hashes
    --write-checksums    download, compute hashes, and write them back into
                         the lockfile (use after bumping `tag`)
    --force              re-download even if local file already matches
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES_DIR = ROOT / "sources"
LOCK_PATH = SOURCES_DIR / "sources.lock.json"

CHUNK = 1 << 16


@dataclass
class Entry:
    tag: str            # upstream release tag
    path: str           # path inside upstream repo
    sha256: str | None  # expected hash, or None on first run

    @property
    def local_name(self) -> str:
        return Path(self.path).name


def load_lock() -> tuple[dict, list[Entry]]:
    data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    entries = [Entry(f["tag"], f["path"], f.get("sha256")) for f in data["files"]]
    return data, entries


def save_lock(data: dict, entries: list[Entry]) -> None:
    # Preserve original key order and only update sha256 fields.
    by_path = {e.path: e.sha256 for e in entries}
    for f in data["files"]:
        f["sha256"] = by_path[f["path"]]
    LOCK_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "diantenjeom-fetch"})
    with urllib.request.urlopen(req) as resp, tmp.open("wb") as out:
        while True:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(dest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-checksums",
        action="store_true",
        help="Record sha256 hashes back into the lockfile (use after bumping tag).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when local file already matches the expected hash.",
    )
    args = parser.parse_args()

    data, entries = load_lock()
    url_template = data["base_url"]
    tags = sorted({e.tag for e in entries})
    print(f"noto-cjk @ {', '.join(tags)}")

    failed: list[str] = []
    for e in entries:
        dest = SOURCES_DIR / e.local_name
        url = url_template.format(tag=e.tag) + e.path

        need_download = args.force or not dest.exists()
        if not need_download and e.sha256 is not None:
            need_download = sha256_file(dest) != e.sha256

        if need_download:
            print(f"  ↓ {e.local_name}")
            try:
                download(url, dest)
            except Exception as exc:
                print(f"    failed: {exc}", file=sys.stderr)
                failed.append(e.local_name)
                continue
        else:
            print(f"  ✓ {e.local_name} (cached)")

        actual = sha256_file(dest)
        if args.write_checksums:
            e.sha256 = actual
        elif e.sha256 is None:
            print(
                f"    no checksum recorded for {e.local_name}; "
                "re-run with --write-checksums to populate sources.lock.json",
                file=sys.stderr,
            )
            failed.append(e.local_name)
        elif actual != e.sha256:
            print(
                f"    sha256 mismatch for {e.local_name}\n"
                f"      expected {e.sha256}\n"
                f"      actual   {actual}",
                file=sys.stderr,
            )
            failed.append(e.local_name)

    if args.write_checksums:
        save_lock(data, entries)
        print(f"wrote {LOCK_PATH.relative_to(ROOT)}")

    if failed:
        raise SystemExit(f"{len(failed)} file(s) failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
