"""Check the real installer in a disposable user directory, without sudo."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class Install(unittest.TestCase):
    def test_menu_name_internal_paths_and_existing_data_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            user_dir = Path(directory)
            existing = user_dir / '.local/share/minttresor/accounts.sqlite3'
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b'existing account data fixture')
            result = subprocess.run(['bash', str(PROJECT / 'install.sh')], cwd=PROJECT,
                                    env=dict(os.environ, HOME=directory),
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            desktop = (user_dir / '.local/share/applications/minttresor.desktop').read_text()
            self.assertIn('Name=Speicherort\n', desktop)
            self.assertIn('/.local/bin/minttresor"', desktop)
            self.assertTrue((user_dir / '.local/lib/minttresor/minttresor/ui.py').is_file())
            self.assertTrue(os.access(user_dir / '.local/bin/minttresor', os.X_OK))
            self.assertEqual(existing.read_bytes(), b'existing account data fixture')
