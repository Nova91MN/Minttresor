#!/usr/bin/env bash
# Run once by an administrator; guests never run this script.
set -euo pipefail
if [[ "$EUID" -ne 0 || $# -lt 1 ]]; then
  echo 'Einmalig als Administrator: sudo bash setup-guests.sh LINUX-BENUTZER [ZUSATZORDNER ...]'
  exit 1
fi
command -v visudo >/dev/null || { echo 'Bitte zuerst sudo installieren.'; exit 1; }
[[ -x /usr/bin/veracrypt ]] || { echo 'Bitte zuerst VeraCrypt unter /usr/bin/veracrypt installieren.'; exit 1; }
account_name="$1"
shift
account_uid="$(id -u -- "$account_name")"
[[ "$account_uid" -ge 1000 ]] || { echo 'Nur normale Linux-Benutzerkonten sind erlaubt.'; exit 1; }
source_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
install -d -o root -g root -m 755 /usr/local/libexec /etc/minttresor
install -o root -g root -m 755 "$source_dir/system/minttresor-helper" /usr/local/libexec/minttresor-helper
# An explicit numeric Linux UID is used, never an application username.
/usr/bin/python3 -I - "$account_uid" "$@" <<'PY'
import json, os, pathlib, pwd, sys, tempfile
uid = int(sys.argv[1])
account = pwd.getpwuid(uid)
roots = [pathlib.Path(account.pw_dir).resolve()] + [pathlib.Path(p).resolve(strict=True) for p in sys.argv[2:]]
if any(p == pathlib.Path('/') or not p.is_dir() for p in roots):
    raise SystemExit('Nur konkrete bestehende Speicherordner freigeben, niemals /.')
policy = pathlib.Path('/etc/minttresor') / f'{uid}.json'
fd, temporary = tempfile.mkstemp(dir=policy.parent)
with os.fdopen(fd, 'w') as stream:
    json.dump({'uid': uid, 'roots': [str(p) for p in roots]}, stream)
os.chmod(temporary, 0o644)
os.replace(temporary, policy)
PY
rules_file="$(mktemp)"
trap 'rm -f "$rules_file"' EXIT
# Empty quoted arguments forbid all CLI arguments. The helper validates stdin.
printf '# MintTresor: only its restricted broker, never general VeraCrypt access.\n#%s ALL=(root) NOPASSWD: /usr/local/libexec/minttresor-helper ""\n' "$account_uid" > "$rules_file"
visudo -cf "$rules_file"
install -o root -g root -m 440 "$rules_file" "/etc/sudoers.d/minttresor-$account_uid"
printf 'Gastzugang für %s eingerichtet. Öffnen und Schließen benötigen kein Adminpasswort mehr.\n' "$account_name"
printf 'Zusätzliche Laufwerke müssen mit diesem Skript ausdrücklich freigegeben werden.\n'
