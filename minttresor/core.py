"""Local accounts and a small, explicit VeraCrypt adapter."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import uuid


class UserError(Exception):
    pass


class AuthenticationError(UserError):
    """The local password check failed, independently of VeraCrypt."""


class SetupRequired(UserError):
    """The administrator must complete the existing restricted setup."""


class VaultOperationError(UserError):
    """An operation failed without a reliably identifiable cause."""


def validate_name(name):
    name = name.strip()
    if not re.fullmatch(r'[\w .-]{1,40}', name, flags=re.UNICODE):
        raise UserError('Wähle einen Namen mit 1 bis 40 Zeichen. Erlaubt sind Buchstaben, Zahlen, Leerzeichen, Punkt und Bindestrich.')
    return name


def validate_password(password):
    if len(password) < 12 or len(password.encode('utf-8')) > 128:
        raise UserError('Wähle ein Passwort mit mindestens 12 Zeichen. Falls dein Passwort sehr lang ist, verwende eine kürzere Wortfolge.')
    if any(c in password for c in '\r\n\x00'):
        raise UserError('Das Passwort darf keine Zeilenumbrüche oder Nullzeichen enthalten.')


def password_hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=131072, r=8, p=1, maxmem=256 * 1024 * 1024)


def managed_mount(volume):
    token = Path(volume).stem
    if not re.fullmatch(r'[0-9a-f]{32}', token):
        raise UserError('Ungültige MintTresor-Kennung.')
    return Path('/run/minttresor') / str(os.getuid()) / token


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory or Path.home() / '.local/share/minttresor')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        self.db = sqlite3.connect(self.directory / 'accounts.sqlite3')
        os.chmod(self.directory / 'accounts.sqlite3', 0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY COLLATE NOCASE, salt BLOB NOT NULL, digest BLOB NOT NULL, volume TEXT UNIQUE NOT NULL, mount TEXT UNIQUE NOT NULL, size INTEGER NOT NULL)')
        self.db.commit()

    def default_path(self):
        row = self.db.execute("SELECT value FROM settings WHERE key='path'").fetchone()
        return Path(row[0]) if row else Path.home() / 'Tresore'

    def set_default_path(self, path):
        path = Path(path).expanduser()
        if not path.is_absolute():
            raise UserError('Bitte einen vollständigen Ordnerpfad wählen.')
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not os.access(path, os.W_OK):
            raise UserError('In diesem Ordner können keine Dateien gespeichert werden.')
        self.db.execute("INSERT OR REPLACE INTO settings VALUES ('path', ?)", (str(path.resolve()),))
        self.db.commit()

    def names(self):
        return [r[0] for r in self.db.execute('SELECT name FROM users ORDER BY name')]

    def user(self, name):
        self.db.row_factory = sqlite3.Row
        row = self.db.execute('SELECT * FROM users WHERE name=?', (name,)).fetchone()
        if not row:
            return None
        user = dict(row)
        # Keep a still-open legacy location visible so upgrades cannot hide it.
        if not os.path.ismount(user['mount']):
            user['mount'] = str(managed_mount(user['volume']))
        return user

    def authenticate(self, name, password):
        row = self.user(name)
        salt = row['salt'] if row else bytes(16)
        digest = password_hash(password, salt)
        if not row or not hmac.compare_digest(row['digest'], digest):
            raise AuthenticationError('Das Passwort ist leider nicht richtig. Überprüfe deine Eingabe und versuche es erneut.')
        return row

    def register(self, name, password, size, backend):
        name = validate_name(name)
        validate_password(password)
        if self.user(name):
            raise UserError('Dieser Benutzername ist bereits vergeben.')
        if not isinstance(size, int) or not 1 <= size <= 32:
            raise UserError('Bitte eine Tresorgröße zwischen 1 und 32 GB wählen.')
        base = self.default_path()
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        if shutil.disk_usage(base).free < (size * 1024**3 + 256 * 1024**2):
            raise UserError('Zu wenig freier Speicher für diesen Tresor. Bitte eine kleinere Größe wählen.')
        token = uuid.uuid4().hex
        volume = base / (token + '.hc')
        mount = managed_mount(volume)
        # Reserve a unique filename; never overwrite an existing container.
        volume.touch(mode=0o600, exist_ok=False)
        try:
            backend.create(volume, password, size)
            salt = secrets.token_bytes(16)
            self.db.execute('INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)',
                            (name, salt, password_hash(password, salt), str(volume), str(mount), size))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            # Keep partially created volumes for explicit inspection/recovery.
            raise
        return self.user(name)


class VeraCrypt:
    def __init__(self):
        self.binary = shutil.which('veracrypt')

    def require(self):
        if not self.binary:
            raise SetupRequired('VeraCrypt fehlt noch. Bitte wende dich an die zuständige Person. Hinweise findest du in den Einstellungen.')

    def run(self, arguments, password=None):
        self.require()
        command = [self.binary, '--text', '--non-interactive'] + arguments
        try:
            result = subprocess.run(command, input=(password + '\n') if password is not None else '',
                                    text=True, encoding='utf-8', capture_output=True)
        except OSError as exc:
            raise UserError('VeraCrypt konnte nicht gestartet werden.') from exc
        if result.returncode:
            # Do not log subprocess output: keep secrets out of diagnostics.
            raise VaultOperationError('VeraCrypt konnte den Vorgang nicht abschließen.')

    def guest_operation(self, operation, user, password=''):
        helper = Path('/usr/local/libexec/minttresor-helper')
        if not helper.is_file() or not Path('/usr/bin/sudo').is_file():
            raise SetupRequired('Der Gastzugang ist noch nicht eingerichtet. Bitte wende dich an die zuständige Person. Hinweise findest du in den Einstellungen.')
        if Path(user['mount']) != managed_mount(user['volume']):
            raise UserError('Dieser Tresor ist noch mit einer älteren Version geöffnet. Bitte vor dem Update mit der bisherigen Version oder durch einen Administrator schließen.')
        request = json.dumps({'operation': operation, 'volume': user['volume'], 'password': password})
        try:
            result = subprocess.run(['/usr/bin/sudo', '-n', '--', str(helper)], input=request,
                                    text=True, encoding='utf-8', capture_output=True)
        except OSError as exc:
            raise UserError('Die lokale Gastfreigabe konnte nicht gestartet werden.') from exc
        if result.returncode:
            # Only recognize fixed helper messages. Never relay arbitrary stderr,
            # even from sudo: it can contain paths, process details or secrets.
            detail = result.stderr.strip()
            if 'sudo:' in detail or not detail or detail in (
                'Konto nicht freigegeben.', 'Kein freigegebenes Benutzerkonto.',
                'Die Gastfreigabe oder Tresordatei konnte nicht geprüft werden.',
                'Dieser Speicherort ist noch nicht durch den Administrator freigegeben.',
            ):
                raise SetupRequired('Die Freigabe für dein Linux-Konto oder diesen Speicherort konnte nicht bestätigt werden. Bitte wende dich an die zuständige Person.')
            raise VaultOperationError('Dein Tresor konnte nicht ' + ('geöffnet' if operation == 'open' else 'geschlossen') + ' werden.')

    def create(self, volume, password, size):
        # VeraCrypt refuses existing files without --force. Remove only our empty reservation.
        if volume.stat().st_size != 0:
            raise UserError('Die Tresordatei existiert bereits.')
        volume.unlink()
        self.run(['--create', str(volume), '--size=' + str(size * 1024**3),
                  '--volume-type=normal', '--encryption=AES', '--hash=SHA-512',
                  '--filesystem=FAT', '--pim=0', '--keyfiles=',
                  '--random-source=/dev/urandom', '--stdin'], password)
        os.chmod(volume, 0o600)

    def mounted(self, user):
        return os.path.ismount(user['mount'])

    def open(self, user, password):
        if self.mounted(user):
            return
        if not Path(user['volume']).is_file():
            raise UserError('Die Tresordatei fehlt. Bitte das Laufwerk mit dem gespeicherten Tresor anschließen.')
        self.guest_operation('open', user, password)
        if not self.mounted(user):
            raise VaultOperationError('Dein Tresor konnte nicht geöffnet werden.')

    def close(self, user):
        if self.mounted(user):
            self.guest_operation('close', user)
        if self.mounted(user):
            raise UserError('Der Tresor ist noch geöffnet. Bitte alle darin geöffneten Dokumente schließen.')

    def open_folder(self, user):
        if not self.mounted(user):
            raise UserError('Bitte den Tresor zuerst öffnen.')
        subprocess.Popen(['xdg-open', user['mount']], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
