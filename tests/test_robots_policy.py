"""robots.txt says what its own comment says, under both ways crawlers read it.

WHY THIS EXISTS (2026-10-09, website audit 2026-10-06 M14). The file's comment
welcomed AI assistants citing the API docs while its rules blocked /api/ for
GPTBot, ClaudeBot, anthropic-ai and CCBot. Fixing that found a second defect:
the * group listed `Allow: /` BEFORE `Disallow: /data/`, so any crawler that
takes the first matching line (the original 1994 rule, and Python's own
urllib.robotparser) read /data/ as allowed - the one thing the file exists to
block. Google takes the longest match and never saw it.

So every case is checked twice: by urllib.robotparser (first match) and by a
longest-match reading written here, the way Google documents it.
"""

import unittest
import urllib.robotparser
from pathlib import Path

ROBOTS = Path(__file__).resolve().parent.parent / 'robots.txt'
AI_AGENTS = ['GPTBot', 'anthropic-ai', 'ClaudeBot', 'CCBot']
GENERIC = 'Mozilla/5.0 (compatible; SomeCrawler/1.0)'


def groups(text):
    """{agent token (lower case): [(allow?, path prefix), ...]} in file order."""
    out, agents, in_rules = {}, [], False
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if ':' not in line:
            continue
        key, value = (s.strip() for s in line.split(':', 1))
        key = key.lower()
        if key == 'user-agent':
            if in_rules:
                agents, in_rules = [], False
            agents.append(value.lower())
            out.setdefault(value.lower(), [])
        elif key in ('allow', 'disallow'):
            in_rules = True
            for a in agents:
                out[a].append((key == 'allow', value))
    return out


def longest_match_allows(text, agent, path):
    """Google's reading: the agent's own group if one names it, else *; longest prefix wins, allow on a tie."""
    g = groups(text)
    rules = next((r for name, r in g.items() if name != '*' and name in agent.lower()), g.get('*', []))
    best = None
    for allow, prefix in rules:
        if prefix and path.startswith(prefix):
            if best is None or len(prefix) > len(best[1]) or (len(prefix) == len(best[1]) and allow):
                best = (allow, prefix)
    return True if best is None else best[0]


class RobotsPolicyTests(unittest.TestCase):
    def setUp(self):
        self.text = ROBOTS.read_text(encoding='utf-8')
        self.first = urllib.robotparser.RobotFileParser()
        self.first.parse(self.text.splitlines())

    def both(self, agent, path):
        return self.first.can_fetch(agent, path), longest_match_allows(self.text, agent, path)

    def test_data_is_blocked_for_every_crawler_under_both_readings(self):
        for agent in [GENERIC, *AI_AGENTS]:
            with self.subTest(agent=agent):
                self.assertEqual(self.both(agent, '/data/borough-extra.json'), (False, False))

    def test_ai_crawlers_may_read_the_api_docs_and_the_site(self):
        # The comment: "happy for our public methodology and API docs to be cited".
        for agent in AI_AGENTS:
            for path in ['/api/', '/', '/area/london/camden/', '/score-demo/api-docs.html']:
                with self.subTest(agent=agent, path=path):
                    self.assertEqual(self.both(agent, path), (True, True))

    def test_every_ai_group_is_named_in_the_file(self):
        # A crawler matching a named group ignores *, so a named group without
        # /data/ would quietly let that crawler in. Assert each group exists.
        named = set(groups(self.text))
        for agent in AI_AGENTS:
            self.assertIn(agent.lower(), named)

    def test_the_sitemap_is_declared(self):
        self.assertIn('Sitemap: https://skyscore.co.uk/sitemap.xml', self.text)


if __name__ == '__main__':
    unittest.main()
