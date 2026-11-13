import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from minttresor.core import Store, UserError, VeraCrypt, managed_mount


class FakeBackend:
    def create(self, volume, password, size):
        volume.write_bytes(b'fake test container')


class Accounts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'data')
        self.store.set_default_path(Path(self.tmp.name) / 'volumes')

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def register(self, name='Anna', password='Ein-langes-Passwort-123'):
        return self.store.register(name, password, 1, FakeBackend())

    def test_account_round_trip_and_case_insensitive_login(self):
        self.register()
        self.assertEqual(self.store.authenticate('anna', 'Ein-langes-Passwort-123')['name'], 'Anna')
        with self.assertRaises(UserError):
            self.store.authenticate('Anna', 'falsch')
        with self.assertRaises(UserError):
            self.store.authenticate('Unbekannt', 'falsch')

    def test_duplicate_does_not_create_another_volume(self):
        self.register()
        with self.assertRaises(UserError):
            self.register('ANNA')
        self.assertEqual(len(list(self.store.default_path().glob('*.hc'))), 1)

    def test_password_not_stored_and_unique_salts(self):
        a = self.register('Anna')
        b = self.register('Ben')
        self.assertNotEqual(a['salt'], b['salt'])
        self.assertNotEqual(a['digest'], b['digest'])
        self.assertNotIn(b'Ein-langes-Passwort-123', (self.store.directory / 'accounts.sqlite3').read_bytes())
        self.assertEqual((self.store.directory.stat().st_mode & 0o777), 0o700)
        self.assertEqual(((self.store.directory / 'accounts.sqlite3').stat().st_mode & 0o777), 0o600)

    def test_invalid_credentials(self):
        for name, password in [('../Anna', 'Long-password-123'), ('Anna', 'short'),
                               ('Anna', 'Long\npassword-123'), ('Anna', 'Long\x00password-123')]:
            with self.subTest(name=name, password=password):
                with self.assertRaises(UserError):
                    self.register(name, password)
        self.assertEqual(self.store.names(), [])

    def test_path_change_only_applies_to_new_users(self):
        a = self.register()
        new = Path(self.tmp.name) / 'new'
        self.store.set_default_path(new)
        b = self.register('Ben')
        self.assertNotEqual(Path(a['volume']).parent, Path(b['volume']).parent)
        self.assertEqual(Path(b['volume']).parent, new)

    def test_creation_failure_does_not_register_account(self):
        backend = FakeBackend()
        def fail(*args):
            raise UserError('test error')
        backend.create = fail
        with self.assertRaises(UserError):
            self.store.register('Anna', 'Long-password-123', 1, backend)
        self.assertEqual(self.store.names(), [])

    def test_low_disk_space_and_invalid_size(self):
        with patch('minttresor.core.shutil.disk_usage') as usage:
            usage.return_value.free = 10
            with self.assertRaises(UserError):
                self.register()
        with self.assertRaises(UserError):
            self.store.register('Anna', 'Long-password-123', 0, FakeBackend())


class Adapter(unittest.TestCase):
    def setUp(self):
        self.backend = VeraCrypt()
        self.backend.binary = '/usr/bin/veracrypt'

    @patch('minttresor.core.subprocess.run')
    def test_password_sent_only_through_stdin(self, run):
        run.return_value = subprocess.CompletedProcess([], 0)
        self.backend.run(['--stdin'], 'secret-test-value')
        args, kwargs = run.call_args
        self.assertNotIn('secret-test-value', ' '.join(args[0]))
        self.assertEqual(kwargs['input'], 'secret-test-value\n')
        self.assertNotIn('shell', kwargs)

    @patch('minttresor.core.subprocess.run')
    def test_error_does_not_include_sensitive_output(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, '', 'secret-test-value')
        with self.assertRaises(UserError) as error:
            self.backend.run(['--stdin'], 'secret-test-value')
        self.assertNotIn('secret-test-value', str(error.exception))

    @patch('minttresor.core.subprocess.run')
    @patch('minttresor.core.os.path.ismount', return_value=True)
    def test_busy_unmount_never_forces(self, mounted, run):
        run.return_value = subprocess.CompletedProcess([], 1, '', 'busy')
        volume = '/test/' + 'a' * 32 + '.hc'
        with patch('minttresor.core.Path.is_file', return_value=True):
            with self.assertRaises(UserError):
                self.backend.close({'volume': volume, 'mount': str(managed_mount(volume))})
        command = run.call_args.args[0]
        self.assertEqual(command, ['/usr/bin/sudo', '-n', '--', '/usr/local/libexec/minttresor-helper'])
        request = __import__('json').loads(run.call_args.kwargs['input'])
        self.assertEqual(request['operation'], 'close')
        self.assertNotIn('--force', str(run.call_args))

    def test_missing_backend_clear_error(self):
        self.backend.binary = None
        with self.assertRaises(UserError):
            self.backend.require()

    def test_refuses_opening_unmounted_folder(self):
        with patch('minttresor.core.os.path.ismount', return_value=False):
            with self.assertRaises(UserError):
                self.backend.open_folder({'mount': '/missing'})

    @patch('minttresor.core.Path.is_file', return_value=False)
    @patch('minttresor.core.subprocess.run')
    def test_missing_guest_setup_never_prompts(self, run, exists):
        with self.assertRaisesRegex(UserError, 'Gastzugang'):
            self.backend.guest_operation('open', {'volume': '/a.hc', 'mount': '/a'})
        run.assert_not_called()

    @patch('minttresor.core.Path.is_file', return_value=True)
    @patch('minttresor.core.subprocess.run')
    def test_guest_open_has_no_arbitrary_arguments_or_password_in_argv(self, run, exists):
        import json
        run.return_value = subprocess.CompletedProcess([], 0)
        volume = '/test/' + 'b' * 32 + '.hc'
        self.backend.guest_operation('open', {'volume': volume, 'mount': str(managed_mount(volume))}, 'secret-test-value')
        self.assertEqual(run.call_args.args[0], ['/usr/bin/sudo', '-n', '--', '/usr/local/libexec/minttresor-helper'])
        request = json.loads(run.call_args.kwargs['input'])
        self.assertEqual(request, {'operation': 'open', 'volume': volume, 'password': 'secret-test-value'})
        self.assertNotIn('secret-test-value', str(run.call_args.args))

    def test_existing_accounts_use_controlled_runtime_mounts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            try:
                volume = '/test/' + 'c' * 32 + '.hc'
                store.db.execute('INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)',
                                 ('old', b'salt', b'digest', volume, '/old/user/writable/path', 1))
                store.db.commit()
                self.assertEqual(store.user('old')['mount'], str(managed_mount(volume)))
            finally:
                store.db.close()


if __name__ == '__main__':
    unittest.main()
