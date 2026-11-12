#!/usr/bin/env bash
set -euo pipefail
if [[ "${EUID}" -eq 0 ]]; then
  echo 'Bitte als normaler Benutzer starten: bash install.sh (ohne sudo).'
  exit 1
fi
if ! /usr/bin/python3 -c 'import tkinter' 2>/dev/null; then
  echo 'Die Oberfläche benötigt python3-tk. Linux fragt nach deinem Systempasswort.'
  sudo apt-get update
  sudo apt-get install -y python3-tk
fi
command -v pkexec >/dev/null || { echo 'Bitte zuerst installieren: sudo apt install policykit-1'; exit 1; }
app_dir="$HOME/.local/lib/minttresor"
mkdir -p "$app_dir" "$HOME/.local/bin" "$HOME/.local/share/applications"
cp -R "$(dirname "$0")/minttresor" "$app_dir/"
cat > "$HOME/.local/bin/minttresor" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$HOME/.local/lib/minttresor"
exec /usr/bin/python3 -m minttresor "$@"
LAUNCH
chmod +x "$HOME/.local/bin/minttresor"
# Desktop Exec has its own quoting rules; escape path metacharacters explicitly.
/usr/bin/python3 - <<'PY'
from pathlib import Path
path = str(Path.home() / '.local/bin/minttresor')
for char in ('\\', '"', '`', '$'):
    path = path.replace(char, '\\' + char)
path = path.replace('%', '%%')
(Path.home() / '.local/share/applications/minttresor.desktop').write_text(
    '[Desktop Entry]\nType=Application\nName=MintTresor\nComment=Persönliche verschlüsselte Dateiablage\n'
    f'Exec="{path}"\nIcon=folder-locked\nTerminal=false\nCategories=Utility;Security;\n', encoding='utf-8')
PY
printf 'MintTresor ist installiert. Starte es über das Anwendungsmenü.\n'
if ! command -v veracrypt >/dev/null; then
  printf 'VeraCrypt fehlt noch: https://veracrypt.io/en/Downloads.html\n'
fi
