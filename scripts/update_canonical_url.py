"""
Replace user-facing references to the CloudFront distribution URL
(d1oe4ftwutjpf.cloudfront.net) with the canonical custom domain
(skyscore.co.uk) across the repo.

Selective on purpose: infrastructure references (script docstrings
hardcoding the distribution, NHS User-Agent header, e2e test config,
template.yaml CORS_ORIGIN) keep the CloudFront URL because they
genuinely identify the AWS resource. User-facing docs, OG meta tags,
JSON-LD schema, demo-page footer links, etc. switch to the canonical
domain.

Run from repo root:
    python scripts/update_canonical_url.py
"""

import re
from pathlib import Path

OLD = 'd1oe4ftwutjpf.cloudfront.net'
NEW = 'skyscore.co.uk'

# Files where every occurrence is user-facing — full replace.
USER_FACING = [
    'README.md',
    'ROADMAP.md',
    'METHODOLOGY.md',
    'PROJECT_DOCUMENTATION.md',
    'CHANGELOG.md',
    'OUTREACH_LOG.md',
    'community-posts.md',
    'index.html',
    'score-demo/index.html',
    'score-demo/openapi.yaml',
    'score-demo/status.html',
]

# Files where only specific user-facing strings should change. Keep
# the rest pointed at the CloudFront URL (infrastructure / scripts).
SELECTIVE = {
    # Signup Lambda's "docs" URL in the success response is user-facing.
    'backend/lambdas/signup/app.py': [
        # Replace any cloudfront URL inside the response body.
        (re.compile(rf"'docs': 'https://{OLD}/"),
         f"'docs': 'https://{NEW}/"),
    ],
}

# Files we deliberately leave alone (infrastructure, deploy artefacts).
SKIP = {
    '.claude/settings.local.json',
    'backend/lambdas/nhs/app.py',           # User-Agent header (metadata)
    'backend/template.yaml',                # CORS_ORIGIN — needs separate care
    'package.json',
    'playwright.config.js',                 # E2E baseURL — fine to keep
    'scripts/attach_custom_domain.py',       # Documents the distribution
    'scripts/install_cloudfront_index_rewrite.py',  # Documents the distribution
    'AUDIT_REPORT.md',                       # Historical reference
    'HACKATHON_SUBMISSION.md',               # Historical reference
    'CLAUDE.md',                             # Session instructions — needs care
}


def replace_full(path: Path):
    text = path.read_text(encoding='utf-8')
    if OLD not in text:
        return 0
    count = text.count(OLD)
    new_text = text.replace(OLD, NEW)
    path.write_text(new_text, encoding='utf-8', newline='\n')
    return count


def replace_selective(path: Path, patterns):
    text = path.read_text(encoding='utf-8')
    total = 0
    for pat, repl in patterns:
        new_text, n = pat.subn(repl, text)
        if n:
            total += n
            text = new_text
    if total:
        path.write_text(text, encoding='utf-8', newline='\n')
    return total


def main():
    root = Path('.').resolve()
    total_replaced = 0
    files_touched = 0

    for rel in USER_FACING:
        path = root / rel
        if not path.exists():
            print(f'  SKIP (missing): {rel}')
            continue
        n = replace_full(path)
        if n:
            files_touched += 1
            total_replaced += n
            print(f'  {rel}: {n} replacements')

    for rel, patterns in SELECTIVE.items():
        path = root / rel
        if not path.exists():
            continue
        n = replace_selective(path, patterns)
        if n:
            files_touched += 1
            total_replaced += n
            print(f'  {rel}: {n} selective replacements')

    print(f'\nDone. {total_replaced} replacements across {files_touched} files.')
    print(f'Skipped (kept CloudFront URL): {", ".join(sorted(SKIP))}')


if __name__ == '__main__':
    main()
