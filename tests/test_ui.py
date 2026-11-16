"""Exercise real Tk navigation with a real isolated account DB and a fake disk adapter.

The adapter never mounts or encrypts files. Real VeraCrypt coverage lives in
``guest_roundtrip.py``; these tests verify UI state, threading and recovery.
"""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from minttresor.app import App, friendly_error, main
from minttresor.core import AuthenticationError, Store, UserError, VaultOperationError
from minttresor.ui import configure_theme


PASSWORD = 'UI-test-fixture-only-7239'


class FakeBackend:
    binary = '/usr/bin/veracrypt'

    def __init__(self):
        self.opened = set()
        self.calls = []
        self.close_error = False
        self.create_error = False
        self.open_error = False
        self.gate = None

    def create(self, volume, password, size):
        self.calls.append(('create', threading.get_ident()))
        if self.create_error:
            raise UserError('Für diesen Tresor ist nicht genug Speicherplatz frei.')
        volume.write_bytes(b'GUI test fixture, not an encrypted vault')

    def mounted(self, user):
        return user['name'] in self.opened

    def open(self, user, password):
        self.calls.append(('open', threading.get_ident()))
        if self.gate:
            self.gate.wait(timeout=5)
        if self.open_error:
            raise VaultOperationError('operation failed')
        self.opened.add(user['name'])

    def close(self, user):
        self.calls.append(('close', threading.get_ident()))
        if self.close_error:
            raise UserError('busy')
        self.opened.discard(user['name'])

    def open_folder(self, user):
        self.calls.append(('folder', threading.get_ident()))
        if not self.mounted(user):
            raise UserError('Bitte den Tresor zuerst öffnen.')


class ErrorMessages(unittest.TestCase):
    def test_startup_database_errors_use_a_safe_message_and_error_status(self):
        with patch('minttresor.app.tk.Tk') as constructor, \
             patch('minttresor.app.App', side_effect=PermissionError(PASSWORD)), \
             patch('minttresor.app.messagebox.showerror') as dialog:
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 1)
        self.assertNotIn(PASSWORD, str(dialog.call_args))
        constructor.return_value.destroy.assert_called_once()

    def test_wrong_password_is_distinct_from_an_open_failure(self):
        title, _ = friendly_error(AuthenticationError(), 'open')
        self.assertIn('Passwort', title)
        title, hint = friendly_error(VaultOperationError('raw engine text'), 'open')
        self.assertNotIn('Passwort', title)
        self.assertNotIn('raw engine text', title + hint)

    def test_arbitrary_exception_details_are_never_shown(self):
        for operation in ('open', 'close', 'create', 'folder', 'settings'):
            with self.subTest(operation=operation):
                message = ' '.join(friendly_error(RuntimeError(PASSWORD), operation))
                self.assertNotIn(PASSWORD, message)
        self.assertIn('Berechtigung', friendly_error(PermissionError(PASSWORD), 'settings')[0])


@unittest.skipUnless(os.environ.get('DISPLAY'), 'GUI tests require Xvfb or a desktop')
class Screens(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'state')
        self.store.set_default_path(Path(self.tmp.name) / 'volumes')
        self.backend = FakeBackend()
        self.anna = self.store.register('Anna', PASSWORD, 1, self.backend)
        self.backend.calls.clear()
        self.root = tk.Tk()
        self.callback_errors = []
        self.root.report_callback_exception = lambda *args: self.callback_errors.append(args)
        self.app = App(self.root, store=self.store, backend=self.backend)
        self.root.update()
        self.root.focus_force()

    def tearDown(self):
        if self.backend.gate:
            self.backend.gate.set()
        if self.app.busy:
            self.wait()
        if not self.app.closed:
            self.app.destroy()
        self.tmp.cleanup()
        self.assertEqual(self.callback_errors, [])

    def wait(self):
        deadline = time.monotonic() + 8
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.005)
        self.root.update()
        self.assertFalse(self.app.busy, 'Operation failed to finish')
        self.assertEqual(self.callback_errors, [])

    def texts(self):
        result = []
        for widget in self.app.descendants(self.root):
            try:
                result.append(str(widget.cget('text')))
            except tk.TclError:
                pass
        return '\n'.join(result)

    def button(self, text):
        for widget in self.app.descendants(self.root):
            if isinstance(widget, ttk.Button) and widget.cget('text') == text:
                return widget
        self.fail('Missing button: ' + text)

    def open_anna(self):
        self.app.password_view('Anna')
        self.app.password.set(PASSWORD)
        self.app.sign_in()
        self.wait()

    def test_card_selection_password_focus_and_enter_to_open(self):
        self.assertIn('Wähle deinen Tresor', self.texts())
        cards = [w for w in self.app.descendants(self.root)
                 if isinstance(w, ttk.Button) and w.cget('style') == 'User.TButton']
        self.assertEqual(len(cards), 1)
        cards[0].invoke()
        self.root.update()
        self.assertIs(self.root.focus_get(), self.app.login_password.entry)
        self.app.password.set(PASSWORD)
        self.root.event_generate('<Return>')
        self.wait()
        self.assertTrue(self.backend.mounted(self.anna))
        self.assertIn('Meine Dateien öffnen', self.texts())
        self.assertEqual(self.app.password.get(), '')
        self.assertNotEqual(self.backend.calls[0][1], threading.get_ident())

    def test_wrong_password_and_technical_failure_can_be_retried(self):
        self.app.password_view('Anna')
        self.app.password.set('wrong')
        self.app.sign_in()
        self.wait()
        self.assertIn('Das Passwort ist leider nicht richtig.', self.texts())
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.app.password.get(), '')
        self.backend.open_error = True
        self.app.password.set(PASSWORD)
        self.app.sign_in()
        self.wait()
        self.assertIn('Dein Tresor konnte nicht geöffnet werden.', self.texts())
        self.assertFalse(self.backend.mounted(self.anna))
        self.backend.open_error = False
        self.app.password.set(PASSWORD)
        self.app.sign_in()
        self.wait()
        self.assertTrue(self.backend.mounted(self.anna))

    def test_work_stays_responsive_blocks_double_clicks_navigation_and_quit(self):
        self.backend.gate = threading.Event()
        self.app.password_view('Anna')
        self.app.password.set(PASSWORD)
        self.app.sign_in()
        self.assertTrue(self.app.busy)
        self.assertTrue(self.app.settings_button.instate(['disabled']))
        self.assertTrue(self.app.login_password.toggle.instate(['disabled']))
        self.app.sign_in()
        self.app.login()
        self.app.settings()
        self.app.quit()
        self.assertFalse(self.app.closed)
        heartbeat = []
        self.root.after(5, lambda: heartbeat.append(True))
        deadline = time.monotonic() + 2
        while not heartbeat and time.monotonic() < deadline:
            self.root.update()
        self.assertEqual(heartbeat, [True])
        self.assertTrue(self.app.busy)
        self.backend.gate.set()
        self.wait()
        self.assertEqual([call[0] for call in self.backend.calls], ['open'])
        self.assertFalse(self.app.settings_button.instate(['disabled']))

    def test_password_visibility_blur_escape_and_navigation(self):
        self.app.password_view('Anna')
        self.root.update()
        field = self.app.login_password
        field.value.set(PASSWORD)
        field.toggle.invoke()
        self.assertEqual(field.entry.cget('show'), '')
        self.assertIsNotNone(field.timer)
        callback_script = self.root.tk.call('after', 'info', field.timer)[0]
        self.root.tk.eval(callback_script)
        self.assertEqual(field.entry.cget('show'), '•')
        field.toggle.invoke()
        self.root.event_generate('<Escape>')
        self.assertEqual(field.entry.cget('show'), '•')
        field.toggle.invoke()
        self.app.settings_button.focus_set()
        self.root.update()
        self.assertEqual(field.entry.cget('show'), '•')
        field.toggle.invoke()
        self.app.login()
        self.assertEqual(field.value.get(), '')
        self.assertIsNone(field.timer)

    def test_failed_close_and_failed_window_close_keep_session_open(self):
        self.open_anna()
        self.backend.close_error = True
        self.app.logout()
        self.wait()
        self.assertTrue(self.backend.mounted(self.anna))
        self.assertIn('nicht als sicher geschlossen bestätigt', self.texts())
        with patch('minttresor.app.messagebox.askokcancel', return_value=True):
            self.app.quit()
            self.wait()
        self.assertFalse(self.app.closed)
        self.assertTrue(self.backend.mounted(self.anna))
        self.backend.close_error = False
        self.app.logout()
        self.wait()
        self.assertFalse(self.backend.mounted(self.anna))
        self.assertIn('Dein Tresor ist geschlossen', self.texts())
        self.button('Tresor öffnen').invoke()
        self.assertIn('Gib dein Passwort ein', self.texts())

    def test_window_close_can_be_cancelled_or_safely_complete(self):
        self.open_anna()
        with patch('minttresor.app.messagebox.askokcancel', return_value=False):
            self.app.quit()
        self.assertTrue(self.backend.mounted(self.anna))
        with patch('minttresor.app.messagebox.askokcancel', return_value=True):
            self.app.quit()
            deadline = time.monotonic() + 5
            while not self.app.closed and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.005)
        self.assertTrue(self.app.closed)
        self.assertFalse(self.backend.mounted(self.anna))

    def test_previously_open_vault_blocks_exit_without_authentication(self):
        self.backend.opened.add('Anna')
        self.app.login()
        self.assertIn('Noch geöffnet', self.texts())
        with patch('minttresor.app.messagebox.showinfo') as info:
            self.app.quit()
        info.assert_called_once()
        self.assertFalse(self.app.closed)
        self.assertTrue(self.backend.mounted(self.anna))

    def fill_wizard(self, name='Ben'):
        self.app.register_view()
        self.app.wizard_name.set(name)
        self.app.wizard_name_next()
        self.app.new_password.value.set(PASSWORD)
        self.app.confirm_password.value.set(PASSWORD)
        self.app.wizard_password_next()

    def test_wizard_validates_then_creates_without_overwriting_existing_vault(self):
        existing = Path(self.anna['volume']).read_bytes()
        self.app.register_view()
        self.app.wizard_name.set('ANNA')
        self.app.wizard_name_next()
        self.assertEqual(self.app.wizard['step'], 1)
        self.fill_wizard()
        self.app.wizard_size.set('0')
        self.app.create_vault()
        self.assertFalse(self.app.busy)
        self.app.wizard_size.set('1')
        self.app.create_vault()
        self.app.create_vault()
        self.wait()
        self.assertEqual(self.store.names(), ['Anna', 'Ben'])
        self.assertEqual(Path(self.anna['volume']).read_bytes(), existing)
        self.assertEqual([c[0] for c in self.backend.calls], ['create'])
        self.assertIsNone(self.app.wizard_secret)
        self.assertIn('Dein Tresor ist bereit!', self.texts())
        self.button('Jetzt Dateien öffnen').invoke()
        self.app.password.set(PASSWORD)
        self.app.sign_in()
        self.wait()
        self.assertEqual([c[0] for c in self.backend.calls], ['create', 'open', 'folder'])
        self.assertTrue(self.backend.mounted(self.store.user('Ben')))

    def test_wizard_mismatch_back_cancel_and_failed_creation(self):
        self.app.register_view()
        self.app.wizard_name.set('Ben')
        self.app.wizard_name_next()
        self.app.new_password.value.set(PASSWORD)
        self.app.confirm_password.value.set('mismatch')
        self.app.wizard_password_next()
        self.assertEqual(self.app.wizard['step'], 2)
        self.app.confirm_password.value.set(PASSWORD)
        self.app.wizard_password_next()
        self.app.wizard_back_password()
        self.assertIsNone(self.app.wizard_secret)
        self.assertEqual(self.app.new_password.value.get(), '')
        self.app.cancel_wizard()
        self.assertIsNone(self.app.wizard)
        self.fill_wizard()
        self.backend.create_error = True
        self.app.create_vault()
        self.wait()
        self.assertEqual(self.store.names(), ['Anna'])
        self.assertEqual(self.app.wizard['step'], 2)
        self.assertIsNone(self.app.wizard_secret)
        self.assertEqual(self.app.new_password.value.get(), '')
        self.assertIn('nicht genug Speicherplatz', self.texts())

    def test_settings_preserve_existing_paths_and_open_session(self):
        self.open_anna()
        old_volume = self.anna['volume']
        self.app.settings()
        self.assertFalse(self.app.admin_panel.winfo_manager())
        self.app.toggle_admin()
        self.assertEqual(self.app.admin_panel.winfo_manager(), 'pack')
        new_path = Path(self.tmp.name) / 'new vaults'
        self.app.settings_path.set(str(new_path))
        self.app.save_settings()
        self.wait()
        self.assertEqual(self.store.default_path(), new_path)
        self.assertEqual(self.store.user('Anna')['volume'], old_volume)
        self.assertTrue(self.backend.mounted(self.anna))
        self.assertIn('Meine Dateien öffnen', self.texts())

    def test_tab_and_space_navigate_and_activate_controls(self):
        self.app.password_view('Anna')
        self.root.update()
        entry = self.app.login_password.entry
        toggle = self.app.login_password.toggle
        entry.focus_force()
        self.root.event_generate('<Tab>')
        self.root.update()
        self.assertIs(self.root.focus_get(), toggle)
        self.root.event_generate('<space>')
        self.root.event_generate('<KeyRelease-space>')
        self.root.update()
        self.assertTrue(self.app.login_password.visible.get())
        self.root.event_generate('<Tab>')
        self.root.update()
        self.assertEqual(self.root.focus_get(), self.button('Tresor öffnen'))

    def test_all_screens_scroll_at_small_size_and_scaled_dpi(self):
        for scale in (1, 1.25, 1.5, 2):
            self.root.tk.call('tk', 'scaling', scale * 96 / 72)
            self.app.scale = scale
            self.app.page.scale = scale
            configure_theme(self.root)
            self.root.geometry('640x480')
            views = [self.app.login, lambda: self.app.password_view('Anna'),
                     lambda: self.app.dashboard(self.anna), self.app.register_view,
                     lambda: self.app.wizard_step(2), lambda: self.app.wizard_step(3),
                     lambda: self.app.wizard_done(self.anna), self.app.settings]
            for view in views:
                view()
                self.root.update()
                buttons = [w for w in self.app.descendants(self.app.frame)
                           if isinstance(w, ttk.Button) and w.winfo_ismapped()]
                self.assertTrue(buttons)
                last = buttons[-1]
                last.focus_force()
                self.root.update()
                canvas = self.app.page.canvas
                self.assertGreaterEqual(last.winfo_rooty(), canvas.winfo_rooty() - 1)
                self.assertLessEqual(last.winfo_rooty() + last.winfo_height(),
                                     canvas.winfo_rooty() + canvas.winfo_height() + 1)
                self.assertLessEqual(last.winfo_width(), canvas.winfo_width())
                self.assertGreaterEqual(float(canvas.cget('scrollregion').split()[3]),
                                        self.app.frame.winfo_height())
        self.assertEqual(self.callback_errors, [])

    def test_long_names_and_buttons_wrap_inside_a_narrow_page(self):
        self.store.register('W' * 40, PASSWORD, 1, self.backend)
        self.root.geometry('540x480')
        self.app.login()
        self.root.update()
        for widget in self.app.descendants(self.app.frame):
            if isinstance(widget, ttk.Button):
                self.assertLessEqual(widget.winfo_reqwidth(), widget.winfo_width())

    def test_worker_failures_do_not_print_secrets(self):
        self.app.password_view('Anna')
        stream = io.StringIO()
        def fail():
            raise RuntimeError(PASSWORD)
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            self.app.work(fail, lambda _: None, 'Bitte warten …', 'open')
            self.wait()
        self.assertNotIn(PASSWORD, stream.getvalue())
        self.assertNotIn(PASSWORD, self.texts())


if __name__ == '__main__':
    unittest.main()
