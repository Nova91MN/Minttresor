"""Exercise each launch path in a fresh process and isolated local account directory."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
APP = PROJECT / 'minttresor' / 'app.py'

# Close after the GUI has actually entered its event loop. Before the fix,
# app.py returned without ever constructing a window and produced no marker.
WINDOW_PROBE = '''
import runpy
import sys
import tkinter as tk
original_tk = tk.Tk

def tracked_tk(*args, **kwargs):
    root = original_tk(*args, **kwargs)
    def inspect():
        root.update_idletasks()
        if root.winfo_viewable() and root.title().startswith('MintTresor') and root.winfo_children():
            print('MINTTRESOR_WINDOW_OPENED', flush=True)
        root.destroy()
    root.after(150, inspect)
    return root

tk.Tk = tracked_tk
if sys.argv[1] == 'script':
    # Match Python's sys.path for a direct file launch; the project root is absent.
    from pathlib import Path
    sys.path[0] = str(Path(sys.argv[2]).parent)
    runpy.run_path(sys.argv[2], run_name='__main__')
else:
    runpy.run_module(sys.argv[2], run_name='__main__', alter_sys=True)
'''


class Startup(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('DISPLAY'), 'GUI tests require Xvfb or a desktop')
    def test_all_launch_paths_open_window(self):
        for mode, target in [('script', str(APP)), ('module', 'minttresor.app'),
                             ('module', 'minttresor')]:
            with self.subTest(mode=mode, target=target), tempfile.TemporaryDirectory() as directory:
                env = dict(os.environ, HOME=directory)
                env.pop('PYTHONPATH', None)
                if mode == 'module':
                    env['PYTHONPATH'] = str(PROJECT)
                result = subprocess.run([sys.executable, '-c', WINDOW_PROBE, mode, target],
                                        cwd=directory, env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('MINTTRESOR_WINDOW_OPENED', result.stdout)

    def test_missing_display_reports_startup_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, HOME=directory, DISPLAY='')
            env.pop('PYTHONPATH', None)
            result = subprocess.run([sys.executable, str(APP)], cwd=directory, env=env,
                                    capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('grafischen Linux-Sitzung', result.stderr)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
