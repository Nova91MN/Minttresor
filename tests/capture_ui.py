"""Capture reproducible UI fixtures under a desktop/Xvfb (Pillow only for this tool).

No real vaults are created or opened; all screenshots use the fake test adapter.
Run from the project root: python3 tests/capture_ui.py --output /tmp/speicherort
"""
import argparse
from pathlib import Path
import sys
import tempfile
import threading
import tkinter as tk
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import ImageGrab
from minttresor.app import App
from minttresor.core import AuthenticationError, Store
from test_ui import FakeBackend, PASSWORD


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scale', type=float, default=1)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / 'state')
        store.set_default_path(Path(directory) / 'Tresore')
        backend = FakeBackend()
        root = tk.Tk()
        root.tk.call('tk', 'scaling', args.scale * 96 / 72)
        app = App(root, store=store, backend=backend)
        def shot(name):
            root.update()
            app.page.canvas.yview_moveto(0)
            root.update()
            ImageGrab.grab(bbox=(root.winfo_rootx(), root.winfo_rooty(),
                                root.winfo_rootx() + root.winfo_width(),
                                root.winfo_rooty() + root.winfo_height())).save(args.output / (name + '.png'))
        shot('willkommen')
        anna = store.register('Anna', PASSWORD, 1, backend)
        store.register('Thomas', PASSWORD, 1, backend)
        app.login(); shot('tresorauswahl')
        app.password_view('Anna'); shot('passwort')
        app.error(AuthenticationError(), 'open', app.login_password.entry); shot('passwort-fehler')
        backend.opened.add('Anna'); app.dashboard(anna); shot('tresor-geoeffnet')
        app.toggle_details(); shot('tresordetails')
        app.error(RuntimeError(), 'close'); shot('schliessen-fehler')
        backend.opened.clear(); app.dashboard(anna); shot('tresor-geschlossen')
        app.login(); app.register_view(); shot('einrichtung-name')
        app.wizard['name'] = 'Maria'; app.wizard_step(2); shot('einrichtung-passwort')
        app.wizard_step(3); shot('einrichtung-groesse')
        gate = threading.Event()
        app.work(lambda: gate.wait(5), lambda _: app.wizard_done(anna),
                 'Dein Tresor wird erstellt und verschlüsselt … Das kann einige Minuten dauern. Bitte warte.', 'create')
        shot('fortschritt')
        gate.set()
        while app.busy:
            root.update()
            time.sleep(.005)
        shot('einrichtung-fertig')
        app.settings(); shot('einstellungen')
        app.toggle_admin(); shot('administration')
        app.destroy()
    print(f'15 Ansichten gespeichert: {args.output}')


if __name__ == '__main__':
    main()
