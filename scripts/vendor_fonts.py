"""Vendor the Google Fonts used by Sky Score into fonts/ as same-origin assets.

Why: loading fonts from fonts.googleapis.com / fonts.gstatic.com transfers every
visitor's IP address to Google in the US on each page load. Self-hosting removes
a UK GDPR Chapter V transfer question entirely and deletes two rows from the
subprocessor table. Same pattern as the js/vendor/d3.v7.min.js vendoring on
2026-07-30.

Latin subset only. Browsers fall through to the next family in the CSS stack for
any glyph outside it, and a UK/NYC property site renders no Cyrillic or Greek.

VARIABLE FONTS, and why this script deduplicates by checksum
------------------------------------------------------------
Google's CSS emits a separate @font-face per requested weight, but for a variable
font every one of those rules points at the SAME woff2 file. A naive fetch of
`Geist:wght@300;400;500;700` therefore writes four byte-identical 29 KB files and
makes the browser download whichever it needs while three sit unused. The first
run of this script did exactly that: 371,488 bytes across 11 files, of which only
4 files and 132,216 bytes were distinct.

So: fetch, checksum, keep one file per distinct hash, and emit a single
@font-face per family declaring the weight RANGE. The variable axis then covers
every weight the pages ask for.
"""

import hashlib
import pathlib
import re
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "fonts"

# A browser UA is required: Google serves TTF to unrecognised agents, woff2 only
# to modern browsers.
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Sky Score runs TWO typographic systems, and the weight ranges below are the
# UNION of what every page asks for. Getting this wrong is silent: declare
# `font-weight: 400 600` on a variable font and a page requesting weight 300
# renders clamped at 400, with no console warning and no layout break to notice.
#
#   Inter + JetBrains Mono -> index.html (mono 300-700, sans 300-600),
#                             privacy.html, terms.html
#   Geist + Geist Mono     -> pricing.html, changes.html, api/index.html
#
# If a page starts using a weight outside these ranges, widen it here and
# regenerate rather than adding a second @font-face by hand.
SHEETS = (
    "https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;700&family=Geist+Mono:wght@400;500&display=swap",
    "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&display=swap",
)

LATIN_BLOCK = re.compile(r"/\*\s*latin\s*\*/\s*(@font-face\s*\{.*?\})", re.S)
FAMILY = re.compile(r"font-family:\s*'([^']+)'")
WEIGHT = re.compile(r"font-weight:\s*(\d+)")
SRC = re.compile(r"url\((https://fonts\.gstatic\.com/[^)]+\.woff2)\)")


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for stale in OUT.glob("*.woff2"):
        stale.unlink()

    # family -> {"weights": set, "digest": str, "data": bytes}
    families: dict[str, dict] = {}

    for sheet in SHEETS:
        css = get(sheet).decode("utf-8")
        for block in LATIN_BLOCK.findall(css):
            family = FAMILY.search(block).group(1)
            weight = int(WEIGHT.search(block).group(1))
            remote = SRC.search(block).group(1)

            entry = families.setdefault(family, {"weights": set(), "digest": None, "data": None})
            entry["weights"].add(weight)

            if entry["data"] is None:
                data = get(remote)
                entry["data"] = data
                entry["digest"] = hashlib.sha256(data).hexdigest()
            else:
                # Assert the variable-font assumption rather than trusting it. If a
                # family ever ships true per-weight files this must not silently
                # serve one weight for all of them.
                digest = hashlib.sha256(get(remote)).hexdigest()
                if digest != entry["digest"]:
                    raise SystemExit(
                        f"{family} weight {weight} differs from the first file fetched "
                        f"for this family. It is not a single variable font; this script "
                        f"needs a per-weight code path before it can be used again."
                    )

    rules: list[str] = []
    total = 0
    for family in sorted(families):
        entry = families[family]
        name = family.lower().replace(" ", "-") + ".woff2"
        (OUT / name).write_bytes(entry["data"])
        total += len(entry["data"])

        lo, hi = min(entry["weights"]), max(entry["weights"])
        span = f"{lo}" if lo == hi else f"{lo} {hi}"
        print(f"{name:24s} {len(entry['data']):>7,} bytes  weights {span}")

        rules.append(
            "@font-face {\n"
            f"  font-family: '{family}';\n"
            "  font-style: normal;\n"
            f"  font-weight: {span};\n"
            "  font-display: swap;\n"
            f"  src: url('/fonts/{name}') format('woff2');\n"
            "}\n"
        )

    header = (
        "/* Sky Score self-hosted fonts. GENERATED - do not hand-edit.\n"
        " *\n"
        " * Vendored from Google Fonts on 2026-08-05 so no visitor IP is transferred\n"
        " * to fonts.googleapis.com / fonts.gstatic.com. Latin subset only.\n"
        " *\n"
        " * These are VARIABLE fonts: one file per family covers the whole weight\n"
        " * range declared below. Do not split them back out per weight.\n"
        " *\n"
        " * Regenerate: python scripts/vendor_fonts.py   Deploy: make fonts-deploy\n"
        " */\n\n"
    )
    (OUT / "fonts.css").write_text(header + "\n".join(rules), encoding="utf-8", newline="\n")
    print(f"\n{len(families)} files, {total:,} bytes -> {OUT}")


if __name__ == "__main__":
    main()
