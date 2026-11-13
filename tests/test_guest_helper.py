import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HELPER = Path(__file__).resolve().parents[1] / 'system/minttresor-helper'
loader = importlib.machinery.SourceFileLoader('guest_helper', str(HELPER))
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)
TOKEN = 'a' * 32


class GuestHelper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.volume = self.root / (TOKEN + '.hc')
        self.volume.write_bytes(b'\0' * 1024**2)
        self.account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, **values):
        return dict(operation='open', volume=str(self.volume), password='Test-pass-123', **values)

    def test_rejects_arbitrary_commands_paths_and_input(self):
        requests = [dict(operation='create', volume=str(self.volume)),
                    dict(operation='open', volume='/etc/shadow'),
                    dict(operation='open', volume=str(self.root / '..' / self.volume.name)),
                    dict(operation='close', volume='/other/' + self.volume.name),
                    self.request(arguments=['--force']), self.request(uid=0),
                    dict(operation='open', volume=str(self.volume), password='line\nbreak')]
        for request in requests:
            with self.subTest(request=request), self.assertRaises(helper.Rejected):
                helper.validate_request(request, [self.root])

    def test_accepts_only_known_container_in_allowed_directory(self):
        op, path, secret = helper.validate_request(self.request(), [self.root])
        self.assertEqual((op, path, secret), ('open', self.volume, 'Test-pass-123'))

    def test_rejects_symlink_and_hardlink_containers(self):
        linked = self.root / ('b' * 32 + '.hc')
        linked.symlink_to(self.volume)
        with self.assertRaises(OSError):
            helper.open_container(linked, os.getuid())
        linked.unlink()
        os.link(self.volume, linked)
        with self.assertRaises(helper.Rejected):
            helper.open_container(linked, os.getuid())

    def test_rejects_symlink_parent_and_other_owner(self):
        linked = self.root / 'link'
        linked.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            helper.open_container(linked / self.volume.name, os.getuid())
        with self.assertRaises(helper.Rejected):
            helper.open_container(self.volume, os.getuid() + 1)

    def test_descriptor_pins_validated_inode_after_rename(self):
        fd = helper.open_container(self.volume, os.getuid())
        try:
            original = os.fstat(fd).st_ino
            self.volume.rename(self.root / 'moved.hc')
            self.volume.write_text('replacement')
            self.assertEqual(Path(f'/proc/{os.getpid()}/fd/{fd}').stat().st_ino, original)
            self.assertNotEqual(self.volume.stat().st_ino, original)
        finally:
            os.close(fd)

    def test_mount_builds_fixed_restricted_command(self):
        runtime = self.root / 'runtime'
        runtime.mkdir()
        def invoke(args, password=''):
            self.assertEqual(args[0], '--mount')
            self.assertTrue(Path(args[1]).exists())
            self.assertNotEqual(args[1], str(self.volume))
            self.assertIn('--filesystem=vfat', args)
            self.assertIn(f'--fs-options=uid={os.getuid()},gid={os.getgid()},umask=077,nodev,nosuid,noexec', args)
            self.assertEqual(password, 'Test-pass-123')
        with patch.object(helper, 'runtime_directory', return_value=runtime), \
             patch.object(helper, 'root_owned'), patch.object(helper, 'invoke', side_effect=invoke), \
             patch.object(helper.os.path, 'ismount', side_effect=[False, True]):
            helper.handle(self.request(), self.account, [self.root])

    def test_close_targets_only_controlled_mount_and_never_forces(self):
        runtime = self.root / 'runtime'
        runtime.mkdir()
        with patch.object(helper, 'runtime_directory', return_value=runtime), \
             patch.object(helper, 'root_owned'), patch.object(helper, 'invoke') as invoke, \
             patch.object(helper.os.path, 'ismount', side_effect=[True, False]):
            helper.handle(dict(operation='close', volume=str(self.volume)), self.account, [self.root])
        invoke.assert_called_once_with(['--dismount', str(runtime / TOKEN)])

    def test_no_privileged_execution_with_password_in_environment(self):
        with patch.object(helper, 'root_owned'), patch.object(helper.subprocess, 'run') as run:
            run.return_value.returncode = 0
            helper.invoke(['--stdin'], 'secret-test-value')
        self.assertNotIn('secret-test-value', str(run.call_args.args))
        self.assertNotIn('secret-test-value', str(run.call_args.kwargs['env']))
        self.assertEqual(run.call_args.kwargs['env']['HOME'], '/root')
