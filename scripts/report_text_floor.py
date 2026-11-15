"""No text under 8 pt in a street report, chart labels included (audit M-6, 2026-11-13).

The rule was Bill's for the three-page build (2026-11-12) and was checked by hand; four chart labels sat within
0.25 pt of the floor with nothing to notice if one went under. One holder for the measure: scripts/
address_noise_report.mjs refuses a report that breaks it (as it refuses a fourth page), and
tests/test_report_text_floor.py holds the published sample to it.

Measured per character with pdfium (`FPDFText_GetFontSize`), which reports CSS px for Chrome's PDFs: the 18 pt title
reads 24.0, so x0.75 for points (docs/lessons/front-page-and-site.md). `body_size()` gives the commonest size, so a
caller can prove the unit is still right before trusting a floor.

    python scripts/report_text_floor.py <report.pdf>    # exit 1 and the runs under 8 pt; 0 otherwise
"""
import sys
from collections import Counter
from pathlib import Path

PX_TO_PT = 0.75
FLOOR_PT = 8.0
SLACK_PT = 0.05  # rounding in the PDF's own sizes, never a loosened rule


def char_sizes(pdf_path):
    """[(page number from 1, size in pt, character)] for every printed (non-space) character."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    out = []
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        for i in range(len(doc)):
            tp = doc[i].get_textpage()
            for c in range(tp.count_chars()):
                ch = chr(raw.FPDFText_GetUnicode(tp, c))
                if ch.strip():
                    out.append((i + 1, raw.FPDFText_GetFontSize(tp, c) * PX_TO_PT, ch))
    finally:
        doc.close()
    return out


def runs_under(sizes, floor=FLOOR_PT):
    """Each run of consecutive characters under the floor, as (page, smallest pt, text)."""
    runs, cur = [], None
    for page, size, ch in sizes:
        if size < floor - SLACK_PT:
            if cur and cur[0] == page:
                cur = (page, min(cur[1], size), cur[2] + ch)
            else:
                if cur:
                    runs.append(cur)
                cur = (page, size, ch)
        elif cur:
            runs.append(cur)
            cur = None
    if cur:
        runs.append(cur)
    return runs


def body_size(sizes):
    """The commonest size in pt, to 0.05: the body text's, if the unit is still right."""
    return Counter(round(s * 20) / 20 for _, s, _ in sizes).most_common(1)[0][0]


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    sizes = char_sizes(Path(argv[1]))
    if not sizes:
        print(f'no text read from {argv[1]}: cannot check the 8 pt floor')
        return 1
    runs = runs_under(sizes)
    smallest = min(s for _, s, _ in sizes)
    if runs:
        shown = '; '.join(f'p{p} {s:.2f} pt "{t[:40]}"' for p, s, t in runs[:8])
        print(f'{len(runs)} run(s) under {FLOOR_PT:g} pt: {shown}')
        return 1
    print(f'nothing under {FLOOR_PT:g} pt (smallest {smallest:.2f} pt, body {body_size(sizes):g} pt)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
