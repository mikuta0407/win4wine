#!/usr/bin/env python3
"""Check scripts/box64-wine.sh with a stand-in Wine and Box64: the session's
and the prefix tools' lookups (wineserver beside wine, Wine's lib/ and share/
beside its bin/) find the wrappers, and the wrappers run Wine's programs
through box64 with WINELOADER, WINESERVER and BOX64_LD_LIBRARY_PATH."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/box64-wine.sh'
sys.path.insert(0, str(ROOT / 'session'))
from wineenv import environment, SHELLS


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)


class Box64WineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.install, self.libs, self.out = root / 'wine-install', root / 'x86_64-linux-gnu', root / 'box64-wine'
        for name in ('wine', 'wineserver'):
            # Wine's x86-64 programs, which the stand-in box64 runs as scripts.
            executable(self.install / 'bin' / name,
                       f'#!/bin/sh\necho "{name} $BOX64_RAN|$WINELOADER|$WINESERVER|$BOX64_LD_LIBRARY_PATH|$*"\n')
        for arch in ('i386-windows', 'x86_64-windows'):
            dll = self.install / 'lib/wine' / arch / 'win4wine-controls.dll'
            dll.parent.mkdir(parents=True)
            dll.write_text('')
        (self.install / 'share/wine').mkdir(parents=True)
        (self.install / 'share/wine/wine.inf').write_text('')
        (self.install / 'win4wine-patches').write_text('digest\n')
        self.libs.mkdir()
        self.box64 = root / 'box64/box64'
        executable(self.box64, '#!/bin/sh\nexport BOX64_RAN=yes\nexec "$@"\n')

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, *arguments, check=True):
        return subprocess.run([str(SCRIPT), *map(str, arguments)], capture_output=True, text=True, check=check)

    def test_wrappers(self):
        output = self.run_script(self.install, self.out, '--libs', self.libs, '--box64', self.box64).stdout
        self.assertIn('wine yes|', output)
        wine = self.out / 'bin/wine'
        # Files, not links: Path.resolve() in the session must stay on them.
        self.assertFalse(wine.is_symlink())
        self.assertEqual(wine.resolve(), wine)
        self.assertEqual(wine.resolve().with_name('wineserver'), self.out / 'bin/wineserver')
        # prefix/create.py, stage.py, reactos.py and win7.py: Wine's lib/ and share/ beside bin/.
        self.assertTrue((wine.parent.parent / 'lib/wine/x86_64-windows/win4wine-controls.dll').is_file())
        self.assertTrue((wine.parent.parent / 'share/wine/wine.inf').is_file())
        # scripts/setup.sh --wine-install compares the patches the Wine was built with.
        self.assertEqual((self.out / 'win4wine-patches').read_text(), 'digest\n')
        for name in ('wine', 'wineserver'):
            line = subprocess.run([str(self.out / 'bin' / name), 'a b', 'c'], capture_output=True, text=True,
                                  env=dict(os.environ, BOX64_LD_LIBRARY_PATH='/extra'), check=True).stdout
            self.assertEqual(line.strip(), f'{name} yes|{self.out}/bin/wine|{self.out}/bin/wineserver|'
                                           f'{self.libs}:/extra|a b c')

    def test_session_environment(self):
        self.run_script(self.install, self.out, '--box64', self.box64)
        prefix = Path(self.temp.name) / 'prefix'
        prefix.mkdir()
        env = environment({'PATH': '/usr/bin'}, {'wine': str(self.out / 'bin/wine'), 'prefix': str(prefix)},
                          SHELLS['xp'])
        self.assertEqual(env['PATH'].split(os.pathsep)[0], str(self.out / 'bin'))

    def test_refusals(self):
        self.out.mkdir()
        self.assertNotEqual(self.run_script(self.install, self.out, '--box64', self.box64, check=False).returncode, 0)
        self.assertNotEqual(self.run_script(self.libs, self.out / 'x', '--box64', self.box64,
                                            check=False).returncode, 0)


if __name__ == '__main__':
    unittest.main()
