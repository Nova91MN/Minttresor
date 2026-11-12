#!/usr/bin/env python3
"""German, local-only desktop interface."""
import fcntl
import queue
import threading
import webbrowser

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    raise SystemExit('Die Oberfläche fehlt. Bitte installieren: sudo apt install python3-tk')

if __package__ in (None, ''):
    # A file launch has no package context, including when started from another folder.
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from minttresor.core import Store, UserError, VeraCrypt
else:
    from .core import Store, UserError, VeraCrypt


class App:
    def __init__(self, root):
        self.root = root
        self.store = Store()
        self.lock = open(self.store.directory / 'app.lock', 'a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            messagebox.showinfo('MintTresor', 'MintTresor ist bereits geöffnet.')
            root.destroy()
            return
        self.backend = VeraCrypt()
        self.current = None
        self.busy = False
        self.events = queue.Queue()
        root.title('MintTresor · Deine Dateien. Sicher verwahrt.')
        root.geometry('780x740')
        root.minsize(760, 720)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Helvetica', 11), background='#f5f7f3', foreground='#203127')
        style.configure('TButton', background='#e3ece2')
        style.map('TButton', background=[('active', '#cddfcf')])
        style.configure('TButton', padding=(14, 10))
        style.configure('Title.TLabel', font=('Helvetica', 25, 'bold'))
        style.configure('Subtitle.TLabel', font=('Helvetica', 14, 'bold'))
        self.frame = ttk.Frame(root, padding=28)
        self.frame.pack(fill='both', expand=True)
        root.protocol('WM_DELETE_WINDOW', self.quit)
        self.login()
        root.after(100, self.poll)

    def clear(self, title, subtitle):
        for child in self.frame.winfo_children():
            child.destroy()
        ttk.Label(self.frame, text='MINTTRESOR', foreground='#23724a').pack(anchor='w')
        ttk.Label(self.frame, text=title, style='Title.TLabel').pack(anchor='w', pady=(12, 8))
        ttk.Label(self.frame, text=subtitle, wraplength=670).pack(anchor='w', pady=(0, 18))

    def field(self, label, value='', secret=False):
        ttk.Label(self.frame, text=label).pack(anchor='w', pady=(8, 4))
        var = tk.StringVar(value=value)
        entry = ttk.Entry(self.frame, textvariable=var, font=('Helvetica', 11), show='•' if secret else '')
        entry.pack(fill='x', ipady=6)
        return var, entry

    def button(self, label, command):
        ttk.Button(self.frame, text=label, command=command).pack(fill='x', pady=(10, 0))

    def status(self):
        self.status_text = tk.StringVar()
        ttk.Label(self.frame, textvariable=self.status_text, wraplength=670).pack(anchor='w', pady=12)
        self.progress = ttk.Progressbar(self.frame, mode='indeterminate')

    def work(self, action, success, text):
        if self.busy:
            return
        self.busy = True
        self.status_text.set(text)
        self.progress.pack(fill='x')
        self.progress.start()
        for widget in self.frame.winfo_children():
            if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Combobox, ttk.Spinbox)):
                widget.configure(state='disabled')
        def worker():
            try:
                self.events.put((True, action(), success))
            except Exception as exc:
                self.events.put((False, exc, success))
        threading.Thread(target=worker, daemon=False).start()

    def poll(self):
        try:
            ok, result, success = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.progress.stop()
            self.progress.pack_forget()
            self.status_text.set('')
            for widget in self.frame.winfo_children():
                if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Combobox, ttk.Spinbox)):
                    widget.configure(state='normal')
            if ok:
                success(result)
            else:
                messagebox.showerror('Das hat noch nicht geklappt', str(result) if isinstance(result, UserError) else
                                     'Der Vorgang konnte nicht abgeschlossen werden. Bitte Speicherplatz und Ordnerrechte prüfen.')
        self.root.after(100, self.poll)

    def login(self):
        self.current = None
        self.clear('Willkommen zu Hause.', 'Deine Dokumente bleiben auf diesem Computer. Öffne deinen persönlichen Tresor oder lege einen Benutzer an.')
        self.name, entry = self.field('Benutzername')
        names = self.store.names()
        if names:
            ttk.Label(self.frame, text='Vorhandene Benutzer: ' + ', '.join(names), wraplength=670).pack(anchor='w', pady=5)
        opened = [name for name in names if self.backend.mounted(self.store.user(name))]
        if opened:
            ttk.Label(self.frame, text='Noch geöffnet: ' + ', '.join(opened) + '. Bitte anmelden und sicher schließen.',
                      foreground='#9b4b0b', wraplength=670).pack(anchor='w', pady=5)
        self.password, _ = self.field('Passwort', secret=True)
        self.button('Anmelden und Tresor öffnen', self.sign_in)
        self.button('Neuen Benutzer anlegen', self.register_view)
        self.button('Einrichtung & Speicherort', self.settings)
        ttk.Label(self.frame, text='Zum Öffnen fragt Linux zusätzlich nach deiner Systemberechtigung.\nDas Systempasswort kann vom Tresorpasswort abweichen.', wraplength=670).pack(anchor='w', pady=15)
        self.status()
        entry.focus_set()

    def sign_in(self):
        try:
            user = self.store.authenticate(self.name.get().strip(), self.password.get())
        except (UserError, ValueError) as exc:
            messagebox.showerror('Anmeldung', str(exc))
            self.password.set('')
            return
        password = self.password.get()
        self.password.set('')
        def action():
            self.backend.open(user, password)
            return user
        self.work(action, self.dashboard, 'Tresor wird geöffnet … Bitte die Linux-Systemabfrage bestätigen.')

    def register_view(self):
        self.clear('Ein Platz nur für dich.', 'Benutzername und Passwort genügen. Jeder Benutzer erhält einen eigenen verschlüsselten Tresor.')
        name, _ = self.field('Benutzername')
        password, _ = self.field('Passwort · mindestens 12 Zeichen', secret=True)
        confirm, _ = self.field('Passwort wiederholen', secret=True)
        ttk.Label(self.frame, text='Tresorgröße in GB · 1 bis 32, später nicht automatisch erweiterbar').pack(anchor='w', pady=(12, 4))
        size = tk.StringVar(value='2')
        ttk.Spinbox(self.frame, from_=1, to=32, textvariable=size).pack(fill='x', ipady=5)
        ttk.Label(self.frame, text=f'Speicherort: {self.store.default_path()}\nPasswort gut aufbewahren: Es gibt keine Zurücksetzung. Einzeldateien maximal 4 GB.', wraplength=670).pack(anchor='w', pady=12)
        def submit():
            if password.get() != confirm.get():
                messagebox.showerror('Passwort', 'Die Passwörter stimmen nicht überein.')
                return
            try:
                amount = int(size.get())
            except ValueError:
                messagebox.showerror('Größe', 'Bitte eine ganze Zahl zwischen 1 und 32 eingeben.')
                return
            username, secret = name.get(), password.get()
            def action():
                store = Store(self.store.directory)
                try:
                    return store.register(username, secret, amount, self.backend)
                finally:
                    store.db.close()
            def done(_):
                messagebox.showinfo('Alles bereit', 'Dein Tresor ist angelegt. Du kannst dich jetzt anmelden.')
                self.login()
            password.set('')
            confirm.set('')
            self.work(action, done, 'Tresor wird verschlüsselt angelegt. Das kann einige Minuten dauern. Bitte warten …')
        self.button('Benutzer und Tresor anlegen', submit)
        self.button('Zurück', self.login)
        self.status()

    def settings(self):
        self.clear('Einmal einrichten. Loslegen.', '1. VeraCrypt installieren. 2. Speicherort wählen. 3. Benutzer anlegen.')
        ttk.Label(self.frame, text=('✓ VeraCrypt ist vorhanden.' if self.backend.binary else 'VeraCrypt ist noch nicht installiert.'), style='Subtitle.TLabel').pack(anchor='w', pady=8)
        self.button('Offizielle VeraCrypt-Downloadseite öffnen', lambda: webbrowser.open('https://veracrypt.io/en/Downloads.html'))
        ttk.Label(self.frame, text='Für Linux Mint die passende Ubuntu-Version von VeraCrypt installieren.\nNach der Installation MintTresor neu starten. Keine Online-Registrierung nötig.', wraplength=670).pack(anchor='w', pady=12)
        path, _ = self.field('Standardordner für neue Tresore', str(self.store.default_path()))
        def browse():
            chosen = filedialog.askdirectory(title='Speicherort für Tresore wählen')
            if chosen:
                path.set(chosen)
        self.button('Ordner auswählen …', browse)
        def save():
            try:
                self.store.set_default_path(path.get())
            except (OSError, UserError) as exc:
                messagebox.showerror('Speicherort', str(exc))
                return
            self.login()
        self.button('Speichern und zurück', save)
        self.button('Zurück ohne Änderung', self.login)
        ttk.Label(self.frame, text='Vorhandene Tresore bleiben an ihrem bisherigen Speicherort.\nKonten gelten innerhalb deines Linux-Benutzers. Für getrennte Arbeitsplätze bitte eigene Linux-Konten verwenden.', wraplength=670).pack(anchor='w', pady=16)

    def dashboard(self, user):
        self.current = user
        self.clear(f'Hallo, {user["name"]}.', 'Dein Tresor ist geöffnet. Hier kannst du Dokumente, Tabellen, Bilder und andere Dateien speichern.')
        ttk.Label(self.frame, text='● Geöffnet · zum Arbeiten bereit', foreground='#23724a', style='Subtitle.TLabel').pack(anchor='w', pady=16)
        ttk.Label(self.frame, text='1. Öffne deinen Ordner.\n2. Bearbeite Dateien mit LibreOffice oder anderen Programmen.\n3. Speichere und schließe alle Dokumente. Schließe danach den Tresor.', wraplength=670, justify='left').pack(anchor='w', pady=12)
        self.button('Meinen Ordner öffnen', self.folder)
        self.button('Tresor schließen und abmelden', self.logout)
        ttk.Label(self.frame, text=f'Tresorgröße: {user["size"]} GB\nVerschlüsselte Datei: {user["volume"]}\n\nBackup: Erst den Tresor schließen, dann die .hc-Datei auf ein anderes Laufwerk kopieren. Die Kontodaten ebenfalls sichern (siehe README).', wraplength=670).pack(anchor='w', pady=20)
        self.status()

    def folder(self):
        try:
            self.backend.open_folder(self.current)
        except UserError as exc:
            messagebox.showerror('Ordner öffnen', str(exc))

    def logout(self, exit_after=False):
        user = self.current
        self.work(lambda: self.backend.close(user), lambda _: self.root.destroy() if exit_after else self.login(),
                  'Tresor wird sicher geschlossen …')

    def quit(self):
        if self.busy:
            messagebox.showinfo('Bitte kurz warten', 'Ein Vorgang läuft. Bitte warte, bis er abgeschlossen ist.')
            return
        if self.current:
            self.logout(exit_after=True)
        else:
            opened = [name for name in self.store.names() if self.backend.mounted(self.store.user(name))]
            if opened:
                messagebox.showinfo('Tresor noch geöffnet',
                    'Bitte zuerst anmelden und die geöffneten Tresore schließen: ' + ', '.join(opened))
                return
            self.root.destroy()


def main():
    try:
        root = tk.Tk()
    except tk.TclError:
        raise SystemExit('MintTresor konnte kein Fenster öffnen. Bitte in der grafischen '
                         'Linux-Sitzung starten und prüfen, ob Tkinter installiert ist.')
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
