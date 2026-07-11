#!/usr/bin/env python3
"""Headless-Chrome ink measurement: CFF2 diantenjeom vs glyf Noto Sans TC.

Renders a minimal HTML page with Chrome --screenshot, then uses Pillow to
count dark pixels in the glyf-only vs dtjx+glyf rows.

Usage:
    python scripts/measure_cff2_glyf.py
"""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image  # type: ignore
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q",
                           "Pillow", "--break-system-packages"])
    from PIL import Image  # type: ignore

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
REPO   = Path(__file__).parent.parent
NOTO_TTF = Path("/tmp/noto-glyf/NotoSansTC-VF.ttf")
DTJX_WOFF2 = REPO / "dist/fonts/diantenjeom-sans-jis.woff2"

# Punctuation set to measure
PUNCT = list("「」（）、。！？…—『』〔〕【】")
SIZE  = 48  # px


def build_measure_html(char: str, weight: int = 400) -> str:
    """Return self-contained HTML that renders `char` in glyf vs dtjx."""
    noto_uri  = NOTO_TTF.as_uri()
    dtjx_uri  = DTJX_WOFF2.as_uri()
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
@font-face {{
  font-family: "NotoGlyf";
  src: url("{noto_uri}") format("truetype");
  font-weight: 100 900;
}}
@font-face {{
  font-family: "DtjxJIS";
  src: url("{dtjx_uri}") format("woff2");
  font-weight: 100 900;
  unicode-range: U+0000-FFFF;
}}
* {{ margin:0; padding:0; box-sizing:border-box; background:#fff; }}
body {{ width: {SIZE*2}px; }}
.row {{
  font-size: {SIZE}px;
  line-height: {SIZE}px;
  width: {SIZE}px;
  height: {SIZE}px;
  overflow: hidden;
  color: #000;
}}
.glyf {{ font-family: "NotoGlyf", sans-serif; font-weight: {weight}; }}
.dtjx {{ font-family: "DtjxJIS", "NotoGlyf", sans-serif; font-weight: {weight}; }}
</style>
</head>
<body>
<div class="row glyf">{char}</div>
<div class="row dtjx">{char}</div>
</body></html>"""


def screenshot_html(html: str, tmp_dir: str) -> Path:
    """Write html to a temp file, screenshot with Chrome, return PNG path."""
    html_file = Path(tmp_dir) / "measure.html"
    png_file  = Path(tmp_dir) / "shot.png"
    html_file.write_text(html, encoding="utf-8")

    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-extensions",
            f"--window-size={SIZE*2},{SIZE*2}",
            f"--screenshot={png_file}",
            html_file.as_uri(),
        ],
        capture_output=True,
        timeout=20,
    )
    return png_file


def count_dark(img: Image.Image, y0: int, y1: int, threshold: int = 128) -> int:
    """Count dark pixels in rows [y0, y1) of a grayscale image."""
    band = img.crop((0, y0, img.width, y1))
    pixels = list(band.getdata())
    return sum(1 for p in pixels if p < threshold)


def measure_char(char: str, weight: int = 400) -> dict:
    html = build_measure_html(char, weight)
    with tempfile.TemporaryDirectory() as tmp:
        png = screenshot_html(html, tmp)
        if not png.exists():
            return {"char": char, "glyf": 0, "dtjx": 0, "ratio": 0.0, "error": "no screenshot"}
        img = Image.open(png).convert("L")  # grayscale
        # Top half = glyf row, bottom half = dtjx row
        mid = img.height // 2
        glyf_dark = count_dark(img, 0, mid)
        dtjx_dark = count_dark(img, mid, img.height)
        ratio = dtjx_dark / glyf_dark if glyf_dark else 0.0
        return {
            "char": char,
            "cp": f"U+{ord(char):04X}",
            "glyf": glyf_dark,
            "dtjx": dtjx_dark,
            "ratio": ratio,
        }


def main() -> None:
    if not NOTO_TTF.exists():
        sys.exit(f"ERROR: glyf Noto not found at {NOTO_TTF}. Run:\n"
                 "  cd /tmp && gh release download Sans2.004 --repo notofonts/noto-cjk "
                 "--pattern '02_NotoSansCJK-TTF-VF.zip' -D /tmp/noto-glyf/\n"
                 "  cd /tmp/noto-glyf && unzip -j *.zip 'Variable/TTF/Subset/NotoSansTC-VF.ttf'")
    if not DTJX_WOFF2.exists():
        sys.exit(f"ERROR: diantenjeom woff2 not found at {DTJX_WOFF2}. Run build first.")

    print(f"glyf source: {NOTO_TTF}")
    print(f"dtjx source: {DTJX_WOFF2}")
    print(f"Chrome:      {CHROME}\n")

    results = []
    print(f"{'char':>5}  {'codepoint':>10}  {'glyf px':>8}  {'dtjx px':>8}  {'ratio':>7}  verdict")
    print("-" * 62)
    for ch in PUNCT:
        m = measure_char(ch)
        results.append(m)
        if "error" in m:
            print(f"  {ch}  {m.get('cp','?'):>10}  ERROR: {m['error']}")
            continue
        diff = abs(m["ratio"] - 1)
        verdict = ("≈ same" if diff < 0.05
                   else ("slightly thin" if m["ratio"] < 0.95
                         else ("THIN" if m["ratio"] < 0.85
                               else ("heavier" if m["ratio"] > 1.05 else "≈ same"))))
        print(f"  {ch}  {m['cp']:>10}  {m['glyf']:>8,}  {m['dtjx']:>8,}  {m['ratio']:>7.3f}  {verdict}")

    valid = [r for r in results if "error" not in r and r["glyf"] > 10]
    if not valid:
        print("\nERROR: No valid measurements. Check Chrome and font paths.")
        return

    avg = sum(r["ratio"] for r in valid) / len(valid)
    print(f"\nAverage ratio (dtjx/glyf): {avg:.3f}")

    if avg < 0.85:
        conclusion = "GO — CFF2 noticeably thinner; conversion to glyf recommended"
    elif avg < 0.95:
        conclusion = "MARGINAL — slight thinness (~5–15%), conversion beneficial but not urgent"
    else:
        conclusion = "NO-GO — difference negligible; defer conversion"
    print(f"Conclusion:                {conclusion}")

    out = REPO / "docs" / "cff2-glyf-ink.json"
    out.write_text(
        json.dumps({"avg_ratio": avg, "conclusion": conclusion,
                    "per_char": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nResults → {out}")


if __name__ == "__main__":
    main()
