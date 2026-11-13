"""Explicit CI/manual integration check; run as a dedicated enabled Linux account."""
import os
from pathlib import Path
import subprocess
import tempfile

from minttresor.core import Store, UserError, VeraCrypt

assert os.getuid() != 0
assert subprocess.run(['sudo', '-n', '/usr/bin/id'], capture_output=True).returncode != 0, 'Testkonto darf keine allgemeinen Root-Rechte haben'
with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
    store = Store(Path(directory) / 'state')
    store.set_default_path(Path(directory) / 'volumes')
    backend = VeraCrypt()
    user = store.register('Gast', 'Integration-test-only-9183', 1, backend)
    try:
        try:
            backend.open(user, 'Wrong-test-password')
        except UserError:
            pass
        else:
            raise AssertionError('Falsches Passwort wurde akzeptiert')
        backend.open(user, 'Integration-test-only-9183')
        document = Path(user['mount']) / 'Dokument.txt'
        document.write_text('Nur das Tresorpasswort benötigt.', encoding='utf-8')
        backend.close(user)
        assert not backend.mounted(user)
        backend.open(user, 'Integration-test-only-9183')
        assert document.read_text(encoding='utf-8') == 'Nur das Tresorpasswort benötigt.'
        backend.close(user)
        print('Gast-Roundtrip ohne Adminpasswort erfolgreich')
    finally:
        backend.close(user)
        store.db.close()
