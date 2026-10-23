"""No tracked file names a Windows user folder (audit 2026-10-22 M-5).

The repo is public, and a path like C:\\Users\\<name>\\... publishes the account name and the machine's layout.
About 30 lines carried one, eight of them added in a single week, because a working note copied from a terminal
keeps the path it was run from. Docs and comments write %USERPROFILE% (cmd and prose), ~ (Git Bash, unquoted)
or $env:USERPROFILE (PowerShell) instead; code takes the home folder from the system (os.path.expanduser).
Any user name is caught, not one, so the gate does not depend on whose machine this runs on. Public and Default
are Windows' shared folders, not a person's.
"""
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# git grep -E syntax: a drive letter, Users, then a folder name; and Git Bash's /c/Users/<name> form.
PATTERN = r'[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9._-]+|/[a-z]/Users/[A-Za-z0-9._-]+'
SHARED = re.compile(r'[\\/]Users[\\/]+(Public|Default)\b', re.I)


class NoUserPathTests(unittest.TestCase):
    def test_no_tracked_file_names_a_user_folder(self):
        out = subprocess.run(['git', 'grep', '-n', '-I', '-E', PATTERN, '--', '.'],  # noqa: S603, S607  (git, fixed arguments)
                             cwd=REPO, capture_output=True, text=True)
        self.assertIn(out.returncode, (0, 1), out.stderr)  # 1 is "no match"; anything else is git failing
        hits = [line for line in out.stdout.splitlines() if not SHARED.search(line)]
        self.assertEqual(hits, [], f'{len(hits)} line(s) name a user folder; write %USERPROFILE%, ~ or $env:USERPROFILE:\n'
                         + '\n'.join(h[:160] for h in hits[:20]))


if __name__ == '__main__':
    unittest.main()
