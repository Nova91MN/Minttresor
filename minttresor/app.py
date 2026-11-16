#!/usr/bin/env python3
"""Speicherort: approachable desktop navigation over the existing secure backend."""
import fcntl
from pathlib import Path
import queue
import sqlite3
import threading
import webbrowser

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    raise SystemExit('Die Oberfläche fehlt. Bitte installieren: sudo apt install python3-tk')

if __package__ in (None, ''):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from minttresor.core import (AuthenticationError, SetupRequired, Store, UserError,
                                VaultOperationError, VeraCrypt, validate_name, validate_password)
    from minttresor.ui import COLORS, PasswordField, ScrollPage, configure_theme, icon
else:
    from .core import (AuthenticationError, SetupRequired, Store, UserError,
                       VaultOperationError, VeraCrypt, validate_name, validate_password)
    from .ui import COLORS, PasswordField, ScrollPage, configure_theme, icon


def friendly_error(error, operation):
    """Never display arbitrary exception text or process output."""
    if isinstance(error, AuthenticationError):
        return ('Das Passwort ist leider nicht richtig.',
                'Überprüfe deine Eingabe und versuche es erneut.')
    if isinstance(error, SetupRequired):
        return ('Die Einrichtung ist noch nicht vollständig.', str(error))
    if isinstance(error, PermissionError):
        return ('Du hast keine Berechtigung für diese Aktion.',
                'Bitte wende dich an die zuständige Person oder wähle einen anderen Ordner.')
    if operation == 'close':
        return ('Dein Tresor konnte nicht geschlossen werden.',
                'Er ist nicht als sicher geschlossen bestätigt. Speichere und schließe alle '
                'Dokumente und Ordnerfenster im Tresor. Versuche es danach erneut.')
    if isinstance(error, VaultOperationError):
        return ('Dein Tresor konnte nicht geöffnet werden.' if operation == 'open'
                else 'Dein Tresor konnte nicht erstellt werden.',
                'Bitte versuche es erneut. Falls das Problem bleibt, wende dich an die zuständige Person.')
    if isinstance(error, UserError):
        return ('Bitte überprüfe deine Angaben.', str(error))
    if operation == 'folder':
        return ('Der Dateimanager konnte nicht geöffnet werden.',
                'Versuche es erneut. Falls das Problem bleibt, wende dich an die zuständige Person.')
    return ('Das hat noch nicht geklappt.',
            'Bitte versuche es erneut. Prüfe, ob dein Laufwerk angeschlossen ist und genügend '
            'freien Platz hat. Falls das Problem bleibt, wende dich an die zuständige Person.')


class App:
    def __init__(self, root, store=None, backend=None):
        self.root = root
        self.store = store if store is not None else Store()
        self.lock = open(self.store.directory / 'app.lock', 'a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            messagebox.showinfo('Speicherort', 'Speicherort ist bereits geöffnet.', parent=root)
            self.lock.close()
            self.store.db.close()
            root.destroy()
            return
        self.backend = backend if backend is not None else VeraCrypt()
        self.current = None
        self.busy = False
        self.closed = False
        self.events = queue.Queue()
        self.worker = None
        self.operation = None
        self.disabled = []
        self.password_fields = []
        self.wizard = None
        self.open_after_login = False
        self.enter_action = None
        self.poll_id = None
        self.idle_ids = set()
        self.scale = max(1, float(root.tk.call('tk', 'scaling')) / (96 / 72))
        configure_theme(root)
        root.title('Speicherort')
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        width = min(self.px(920), screen_w - 48)
        height = min(self.px(720), screen_h - 90)
        root.geometry(f'{width}x{height}')
        root.minsize(min(self.px(520), screen_w - 48), min(self.px(440), screen_h - 90))
        self.images = {kind: icon(root, kind, self.px(56)) for kind in ('person', 'lock', 'open')}
        header = ttk.Frame(root, padding=(self.px(22), self.px(12)))
        header.pack(fill='x')
        ttk.Label(header, text='Speicherort', style='Brand.TLabel').pack(side='left')
        self.settings_button = ttk.Button(header, text='Einstellungen', command=self.settings,
                                         style='Quiet.TButton')
        self.settings_button.pack(side='right')
        self.back_button = ttk.Button(header, text='Tresorauswahl', command=self.login,
                                     style='Quiet.TButton')
        ttk.Separator(root).pack(fill='x')
        footer = ttk.Frame(root, padding=(self.px(24), self.px(10)))
        footer.pack(side='bottom', fill='x')
        ttk.Label(footer, text='Deine Dateien bleiben auf deinem Computer.',
                  style='Small.TLabel').pack(anchor='w')
        self.page = ScrollPage(root, self.scale)
        self.frame = self.page.body
        root.protocol('WM_DELETE_WINDOW', self.quit)
        root.bind('<Return>', self.on_enter)
        root.bind('<KP_Enter>', self.on_enter)
        root.bind('<Escape>', self.on_escape)
        root.bind('<FocusIn>', lambda event: self.page.reveal(event.widget), add='+')
        root.bind('<FocusOut>', self.on_blur, add='+')
        root.bind('<MouseWheel>', self.on_wheel, add='+')
        root.bind('<Button-4>', self.on_wheel, add='+')
        root.bind('<Button-5>', self.on_wheel, add='+')
        self.login()
        self.poll_id = root.after(60, self.poll)

    def px(self, value):
        return round(value * self.scale)

    def on_enter(self, event=None):
        if self.busy:
            return 'break'
        focused = self.root.focus_get()
        if isinstance(focused, (ttk.Button, ttk.Checkbutton)):
            focused.invoke()
            return 'break'
        if self.enter_action:
            self.enter_action()
        return 'break'

    def on_escape(self, event=None):
        for field in self.password_fields:
            field.hide()
        return 'break'

    def on_blur(self, event=None):
        if self.closed:
            return
        def check():
            if not self.closed and self.root.focus_displayof() is None:
                self.on_escape()
        self.later(check)

    def later(self, callback):
        def run():
            self.idle_ids.discard(token)
            if not self.closed:
                callback()
        token = self.root.after_idle(run)
        self.idle_ids.add(token)

    def cancel_idle(self):
        for token in self.idle_ids:
            self.root.after_cancel(token)
        self.idle_ids.clear()

    def on_wheel(self, event):
        if getattr(event, 'num', None) in (4, 5):
            amount = -1 if event.num == 4 else 1
        else:
            amount = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        self.page.canvas.yview_scroll(amount * 3, 'units')

    def clear(self, title, subtitle, step=None):
        if self.busy:
            return False
        self.cancel_idle()
        for field in self.password_fields:
            field.clear()
        self.password_fields.clear()
        self.enter_action = None
        self.page.clear()
        self.back_button.pack_forget()
        if self.current and not self.backend.mounted(self.current):
            self.back_button.pack(side='right', padx=(0, self.px(8)))
        if step:
            self.label(step, 'Step.TLabel', pady=(0, 10))
        self.label(title, 'Title.TLabel', pady=(0, 8))
        self.label(subtitle, 'Muted.TLabel', pady=(0, 22))
        self.feedback = ttk.Frame(self.frame, style='Error.TFrame', padding=self.px(16))
        self.feedback_title = self.page.label(self.feedback, style='ErrorTitle.TLabel', inset=32)
        self.feedback_title.pack(anchor='w')
        self.feedback_body = self.page.label(self.feedback, style='Error.TLabel', inset=32)
        self.feedback_body.pack(anchor='w', pady=(6, 0))
        self.busy_panel = ttk.Frame(self.frame, style='Mint.TFrame', padding=self.px(18))
        self.busy_label = self.page.label(self.busy_panel, style='Mint.TLabel', inset=36)
        self.busy_label.pack(anchor='w', pady=(0, 10))
        self.progress = ttk.Progressbar(self.busy_panel, mode='indeterminate', takefocus=False)
        self.progress.pack(fill='x')
        self.content_anchor = ttk.Frame(self.frame)
        self.content_anchor.pack(fill='x')
        return True

    def label(self, text, style='TLabel', parent=None, pady=(0, 10), inset=0):
        label = self.page.label(parent or self.frame, text, style, inset=inset)
        label.pack(anchor='w', fill='x', pady=tuple(self.px(v) for v in pady))
        return label

    def card(self):
        outer = tk.Frame(self.frame, background=COLORS['border'], borderwidth=0)
        outer.pack(fill='x', pady=(0, self.px(16)))
        inner = ttk.Frame(outer, style='Card.TFrame', padding=self.px(22))
        inner.pack(fill='both', expand=True, padx=1, pady=1)
        return inner

    def button(self, label, command, parent=None, primary=False, quiet=False):
        button = ttk.Button(parent or self.frame, text=label, command=command,
                            style='Primary.TButton' if primary else 'Quiet.TButton' if quiet else 'TButton')
        button.pack(fill='x', pady=(self.px(8), 0))
        if primary:
            self.enter_action = command
        return button

    def field(self, label, value='', parent=None):
        parent = parent or self.frame
        self.label(label, 'Card.TLabel', parent=parent, pady=(8, 5), inset=44)
        var = tk.StringVar(value=value)
        entry = ttk.Entry(parent, textvariable=var)
        entry.pack(fill='x', pady=(0, self.px(8)))
        return var, entry

    def password_field(self, parent, label='Dein Passwort'):
        field = PasswordField(parent, label, self.scale)
        self.password_fields.append(field)
        return field

    def focus(self, widget):
        def set_focus():
            if not self.closed and widget.winfo_exists():
                widget.focus_set()
                self.page.reveal(widget)
        self.later(set_focus)

    def error(self, exc, operation='validation', focus=None):
        title, body = friendly_error(exc, operation)
        self.feedback_title.configure(text=title)
        self.feedback_body.configure(text=body)
        self.feedback.pack(fill='x', pady=(0, self.px(16)), before=self.busy_panel
                           if self.busy_panel.winfo_manager() else self.content_anchor)
        self.root.bell()
        self.focus(focus or self.feedback_title)

    def dismiss_error(self):
        self.feedback.pack_forget()

    def descendants(self, parent):
        for child in parent.winfo_children():
            yield child
            yield from self.descendants(child)

    def work(self, action, success, text, operation, failure=None):
        if self.busy:
            return
        self.busy = True
        self.operation = operation
        self.dismiss_error()
        for field in self.password_fields:
            field.hide()
        self.busy_label.configure(text=text)
        # Put feedback above the page contents, so it remains visible while working.
        self.busy_panel.pack(fill='x', pady=(0, self.px(16)),
                             before=self.content_anchor)
        self.progress.start(14)
        self.page.canvas.yview_moveto(0)
        self.disabled = []
        for widget in self.descendants(self.root):
            if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Spinbox, ttk.Checkbutton, ttk.Combobox)):
                self.disabled.append((widget, widget.state()))
                widget.state(['disabled'])

        def worker():
            try:
                result = action()
            except Exception as exc:
                # Tracebacks retain worker frames (and their password arguments).
                exc.__traceback__ = None
                exc.__context__ = None
                exc.__cause__ = None
                self.events.put((False, exc, failure))
            else:
                self.events.put((True, result, success))
        self.worker = threading.Thread(target=worker, daemon=False, name='speicherort-operation')
        self.worker.start()

    def poll(self):
        if self.closed:
            return
        try:
            ok, result, callback = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            operation = self.operation
            self.busy = False
            self.operation = None
            self.worker = None
            self.progress.stop()
            self.busy_panel.pack_forget()
            for widget, state in self.disabled:
                if widget.winfo_exists():
                    widget.state(['!disabled'])
                    widget.state(state)
            self.disabled.clear()
            if ok:
                callback(result)
            elif callback:
                callback(result)
            else:
                self.error(result, operation)
        if not self.closed:
            self.poll_id = self.root.after(60, self.poll)

    def login(self):
        if self.busy:
            return
        if self.current and self.backend.mounted(self.current):
            self.dashboard(self.current)
            return
        self.current = None
        self.open_after_login = False
        self.wipe_wizard_secret()
        self.wizard = None
        self.clear('Willkommen bei Speicherort', 'Deine Dateien. Sicher und einfach.')
        names = self.store.names()
        if names:
            self.label('Wähle deinen Tresor', 'Heading.TLabel', pady=(0, 12))
            first = None
            for name in names:
                user = self.store.user(name)
                opened = self.backend.mounted(user)
                caption = name
                caption += '\n' + ('Noch geöffnet · Zum sicheren Schließen anmelden' if opened
                                   else 'Tresor auswählen  →')
                button = ttk.Button(self.frame, text=caption, image=self.images['person'],
                                    compound='left', style='User.TButton',
                                    command=lambda selected=name: self.password_view(selected))
                button.pack(fill='x', pady=(0, self.px(10)))
                first = first or button
            ttk.Separator(self.frame).pack(fill='x', pady=self.px(14))
            self.button('Neuen Tresor erstellen', self.register_view, quiet=True)
            self.focus(first)
        else:
            card = self.card()
            ttk.Label(card, image=self.images['lock'], style='Card.TLabel').pack(anchor='w', pady=(0, 14))
            self.label('Ein sicherer Platz für deine Dateien', 'Heading.Card.TLabel', parent=card, inset=44)
            self.label('Erstelle deinen ersten Tresor. Danach brauchst du nur deinen Namen '
                       'auszuwählen und dein Passwort einzugeben.', 'Muted.Card.TLabel', parent=card, inset=44)
            button = self.button('Neuen Tresor erstellen', self.register_view, parent=card, primary=True)
            self.focus(button)
        self.label('Dein Passwort schützt deine persönlichen Dateien.', 'Small.TLabel', pady=(18, 20))

    def password_view(self, name):
        if self.busy:
            return
        self.wizard = None
        self.selected_name = name
        self.clear(f'Hallo, {name}!', 'Gib dein Passwort ein, um deine Dateien zu öffnen.')
        self.button('← Zurück zur Tresorauswahl', self.login, quiet=True)
        card = self.card()
        self.login_password = self.password_field(card)
        self.password = self.login_password.value
        self.button('Tresor öffnen', self.sign_in, parent=card, primary=True)
        self.label('Mit der Eingabetaste öffnest du deinen Tresor.', 'Small.TLabel', pady=(2, 18))
        self.focus(self.login_password.entry)

    def sign_in(self):
        if self.busy:
            return
        password = self.password.get()
        if not password:
            self.error(UserError('Gib bitte dein Passwort ein.'), focus=self.login_password.entry)
            return
        name = self.selected_name
        self.login_password.clear()

        def action():
            store = Store(self.store.directory)
            try:
                user = store.authenticate(name, password)
                self.backend.open(user, password)
                return user
            finally:
                store.db.close()

        def failed(exc):
            self.error(exc, 'open', focus=self.login_password.entry)

        def done(user):
            open_files = self.open_after_login
            self.open_after_login = False
            self.dashboard(user)
            if open_files:
                self.folder()
        self.work(action, done, 'Tresor wird geöffnet … Bitte einen Moment warten.', 'open', failed)

    def dashboard(self, user):
        if self.busy:
            return
        self.wizard = None
        self.current = user
        opened = self.backend.mounted(user)
        self.clear(f'Hallo, {user["name"]}!', 'Hier ist dein persönlicher Platz für deine Dateien.')
        card = self.card()
        ttk.Label(card, image=self.images['open' if opened else 'lock'],
                  style='Card.TLabel').pack(anchor='w', pady=(0, self.px(14)))
        self.label('Dein Tresor ist ' + ('geöffnet' if opened else 'geschlossen'),
                   'Heading.Card.TLabel', parent=card, inset=44)
        self.label('Du kannst jetzt auf deine Dateien zugreifen.' if opened
                   else 'Deine Dateien sind sicher verschlossen.',
                   'Muted.Card.TLabel', parent=card, inset=44)
        if opened:
            button = self.button('Meine Dateien öffnen', self.folder, parent=card, primary=True)
            self.button('Tresor sicher schließen', self.logout, parent=card)
            self.label('Wenn du fertig bist, speichere und schließe deine Dokumente und '
                       'Ordnerfenster. Schließe danach deinen Tresor, damit deine Dateien '
                       'wieder geschützt sind.', 'Muted.TLabel', pady=(6, 18))
        else:
            button = self.button('Tresor öffnen', lambda: self.password_view(user['name']),
                                 parent=card, primary=True)
            self.button('Anderen Tresor wählen', self.login, quiet=True)
        self.details_shown = False
        self.details_button = self.button('Hinweise und Tresordetails anzeigen', self.toggle_details, quiet=True)
        self.details = ttk.Frame(self.frame, padding=self.px(16))
        self.label(f'Größe: {user["size"]} GB\nGespeicherte Tresordatei: {user["volume"]}\n\n'
                   'Datensicherung: Schließe zuerst den Tresor. Sichere danach die Tresordatei '
                   'und die lokalen Kontodaten auf einem anderen Laufwerk. Eine Anleitung '
                   'findest du in der README.', 'Small.TLabel', parent=self.details, inset=32)
        self.focus(button)

    def toggle_details(self):
        if self.busy:
            return
        self.details_shown = not self.details_shown
        if self.details_shown:
            self.details.pack(fill='x', pady=(8, 18))
        else:
            self.details.pack_forget()
        self.details_button.configure(text='Hinweise und Tresordetails ' +
                                      ('verbergen' if self.details_shown else 'anzeigen'))

    def folder(self):
        if self.busy or not self.current:
            return
        self.work(lambda: self.backend.open_folder(self.current),
                  lambda _: self.folder_done(), 'Deine Dateien werden geöffnet …', 'folder')

    def folder_done(self):
        self.label('Der Dateimanager wurde gestartet. Du kannst jetzt mit deinen Dateien arbeiten.',
                   'Step.TLabel', pady=(8, 16))

    def logout(self, exit_after=False):
        if self.busy or not self.current:
            return
        user = self.current
        def done(_):
            if exit_after:
                self.finish_quit()
            else:
                self.dashboard(user)
        self.work(lambda: self.backend.close(user), done,
                  'Tresor wird geschlossen … Deine Dateien werden sicher verschlossen.', 'close')

    def register_view(self):
        if self.busy:
            return
        self.wizard = {'name': '', 'size': '2', 'step': 1}
        self.wizard_step(1)

    def wizard_step(self, step):
        if self.busy:
            return
        self.wizard['step'] = step
        titles = {1: ('Wie möchtest du deinen Tresor nennen?', 'Zum Beispiel dein Vorname. So findest du deinen Tresor später wieder.'),
                  2: ('Lege ein sicheres Passwort fest', 'Nur wer dein Passwort kennt, kann deinen Tresor öffnen.'),
                  3: ('Platz für deine Dateien', 'Wähle, wie viel Platz dein neuer Tresor haben soll.')}
        self.clear(*titles[step], step=f'Schritt {step} von 4 · ' + {1: 'Name', 2: 'Passwort', 3: 'Einrichtung'}[step])
        card = self.card()
        if step == 1:
            self.wizard_name, entry = self.field('Name deines Tresors', self.wizard['name'], parent=card)
            self.label('1 bis 40 Zeichen. Buchstaben, Zahlen, Leerzeichen, Punkt und Bindestrich sind möglich.',
                       'Small.Card.TLabel', parent=card, inset=44)
            self.button('Weiter zum Passwort', self.wizard_name_next, parent=card, primary=True)
            self.button('Abbrechen', self.cancel_wizard, quiet=True)
            self.focus(entry)
        elif step == 2:
            self.new_password = self.password_field(card, 'Passwort · mindestens 12 Zeichen')
            self.confirm_password = self.password_field(card, 'Passwort wiederholen')
            self.label('Tipp: Mehrere Wörter ergeben ein langes, gut merkbares Passwort. '
                       'Verwende mindestens 12 Zeichen.', 'Small.Card.TLabel', parent=card, inset=44)
            self.label('Bewahre dein Passwort sicher auf. Wenn du es vergisst, können wir '
                       'deine Dateien nicht wiederherstellen.', 'Card.TLabel', parent=card, inset=44)
            self.button('Weiter zur Einrichtung', self.wizard_password_next, parent=card, primary=True)
            self.button('← Zurück zum Namen', self.wizard_back_name, quiet=True)
            self.button('Abbrechen', self.cancel_wizard, quiet=True)
            self.focus(self.new_password.entry)
        else:
            self.label(f'Tresor für {self.wizard["name"]}', 'Heading.Card.TLabel', parent=card, inset=44)
            self.label('Größe in GB', 'Card.TLabel', parent=card, pady=(8, 5), inset=44)
            self.wizard_size = tk.StringVar(value=self.wizard['size'])
            size = ttk.Spinbox(card, from_=1, to=32, textvariable=self.wizard_size)
            size.pack(fill='x', pady=(0, 12))
            self.label('2 GB reichen für viele Dokumente. Möglich sind 1 bis 32 GB. '
                       'Die Größe lässt sich später nicht automatisch vergrößern. '
                       'Einzelne Dateien müssen kleiner als 4 GB sein.', 'Small.Card.TLabel', parent=card, inset=44)
            self.label(f'Speicherort für deinen Tresor:\n{self.store.default_path()}',
                       'Muted.Card.TLabel', parent=card, inset=44)
            self.label('Das Anlegen kann einige Minuten dauern. Lass Speicherort dabei geöffnet.',
                       'Card.TLabel', parent=card, inset=44)
            self.button('Tresor erstellen', self.create_vault, parent=card, primary=True)
            self.button('← Zurück zum Passwort', self.wizard_back_password, quiet=True)
            self.button('Abbrechen', self.cancel_wizard, quiet=True)
            self.focus(size)

    def wizard_name_next(self):
        if self.busy:
            return
        try:
            name = validate_name(self.wizard_name.get())
            if self.store.user(name):
                raise UserError('Diesen Namen gibt es schon. Wähle bitte einen anderen Namen.')
        except UserError as exc:
            self.error(exc)
            return
        self.wizard['name'] = name
        self.wizard_step(2)

    def wizard_password_next(self):
        if self.busy:
            return
        secret = self.new_password.value.get()
        try:
            validate_password(secret)
            if secret != self.confirm_password.value.get():
                raise UserError('Die Passwörter stimmen nicht überein. Gib beide noch einmal ein.')
        except UserError as exc:
            self.error(exc, focus=self.new_password.entry)
            return
        # Held only for the next step; never persisted or placed in callbacks/widgets.
        self.wizard_secret = secret
        self.wizard_step(3)

    def wizard_back_name(self):
        self.wipe_wizard_secret()
        self.wizard_step(1)

    def wizard_back_password(self):
        self.wizard['size'] = self.wizard_size.get()
        self.wipe_wizard_secret()
        self.wizard_step(2)

    def wipe_wizard_secret(self):
        self.wizard_secret = None

    def cancel_wizard(self):
        if self.busy:
            return
        self.wipe_wizard_secret()
        self.wizard = None
        self.login()

    def create_vault(self):
        if self.busy:
            return
        try:
            amount = int(self.wizard_size.get())
            if not 1 <= amount <= 32:
                raise ValueError()
        except ValueError:
            self.error(UserError('Bitte gib eine ganze Zahl zwischen 1 und 32 ein.'))
            return
        secret, name = self.wizard_secret, self.wizard['name']
        self.wizard['size'] = str(amount)
        self.wipe_wizard_secret()
        def action():
            store = Store(self.store.directory)
            try:
                return store.register(name, secret, amount, self.backend)
            finally:
                store.db.close()
        def failed(exc):
            # A failed creation never reuses a retained password or reserves a second
            # file on double click. Ask for it afresh before another attempt.
            self.wizard_step(2)
            self.error(exc, 'create', focus=self.new_password.entry)
        self.work(action, self.wizard_done, 'Dein Tresor wird erstellt und verschlüsselt … '
                  'Das kann einige Minuten dauern. Bitte warte.', 'create', failed)

    def wizard_done(self, user):
        self.wizard = None
        self.current = user
        self.wipe_wizard_secret()
        self.clear('Dein Tresor ist bereit!', 'Deine Dateien haben jetzt einen sicheren Platz.',
                   step='Schritt 4 von 4 · Fertig')
        card = self.card()
        ttk.Label(card, image=self.images['lock'], style='Card.TLabel').pack(anchor='w', pady=(0, 14))
        self.label(f'Dein Tresor „{user["name"]}“ wurde erstellt.', 'Heading.Card.TLabel', parent=card, inset=44)
        self.label('Zum Öffnen gibst du dein Passwort ein. Danach kannst du deine Dateien '
                   'im Dateimanager ablegen.', 'Muted.Card.TLabel', parent=card, inset=44)
        self.open_after_login = True
        button = self.button('Jetzt Dateien öffnen', lambda: self.password_view(user['name']),
                             parent=card, primary=True)
        self.button('Zur Tresorauswahl', self.login, quiet=True)
        self.focus(button)

    def settings(self):
        if self.busy:
            return
        if self.wizard:
            # Do not silently discard a partly completed setup through the header.
            messagebox.showinfo('Speicherort', 'Beende zuerst die Einrichtung oder wähle „Abbrechen“.', parent=self.root)
            return
        self.open_after_login = False
        self.clear('Einstellungen', 'Hier findest du den Speicherort und Hilfe zur ersten Einrichtung.')
        card = self.card()
        self.label('Speicherort für neue Tresore', 'Heading.Card.TLabel', parent=card, inset=44)
        self.label('Bestehende Tresore bleiben an ihrem bisherigen Platz. '
                   'Diese Einstellung gilt nur für neue Tresore in deinem Linux-Konto.',
                   'Muted.Card.TLabel', parent=card, inset=44)
        self.settings_path, entry = self.field('Ordner', str(self.store.default_path()), parent=card)
        self.button('Ordner auswählen …', self.browse, parent=card)
        self.button('Speichern', self.save_settings, parent=card, primary=True)
        self.admin_button = self.button('Einrichtung durch Administratoren anzeigen', self.toggle_admin, quiet=True)
        self.admin_panel = ttk.Frame(self.frame, padding=self.px(16))
        self.admin_visible = False
        self.label('Einmalige Einrichtung · Administrator erforderlich', 'Heading.TLabel', parent=self.admin_panel, inset=32)
        self.label('VeraCrypt ist installiert.' if self.backend.binary else 'VeraCrypt ist noch nicht installiert.',
                   'TLabel', parent=self.admin_panel, inset=32)
        self.label('Ein Administrator installiert VeraCrypt und führt im Projektordner einmalig '
                   '„sudo bash setup-guests.sh LINUX-BENUTZER“ aus. Zusätzliche Speicherordner '
                   'auf externen Laufwerken müssen dabei ausdrücklich freigegeben werden. '
                   'Danach benötigen Benutzer nur ihr Tresorpasswort. Das Speichern eines '
                   'Ordners hier erteilt keine Systemfreigabe.', 'Muted.TLabel', parent=self.admin_panel, inset=32)
        self.button('VeraCrypt-Downloadseite öffnen', self.download_veracrypt, parent=self.admin_panel)
        self.label('Nach der Installation Speicherort neu starten. Weitere Hinweise zu '
                   'Installation, Freigaben und Sicherungen stehen in der README.',
                   'Small.TLabel', parent=self.admin_panel, inset=32)
        self.settings_back = self.button('← Zurück', self.settings_return, quiet=True)
        self.focus(entry)

    def browse(self):
        if not self.busy:
            chosen = filedialog.askdirectory(title='Speicherort · Ordner für neue Tresore', parent=self.root)
            if chosen:
                self.settings_path.set(chosen)

    def save_settings(self):
        if self.busy:
            return
        path = self.settings_path.get()
        def action():
            store = Store(self.store.directory)
            try:
                store.set_default_path(path)
            finally:
                store.db.close()
        def done(_):
            self.settings_return()
            self.label('Der Speicherort für neue Tresore wurde gespeichert.', 'Step.TLabel', pady=(12, 20))
        self.work(action, done, 'Speicherort wird gespeichert …', 'settings')

    def toggle_admin(self):
        if self.busy:
            return
        self.admin_visible = not self.admin_visible
        if self.admin_visible:
            self.admin_panel.pack(fill='x', before=self.settings_back)
        else:
            self.admin_panel.pack_forget()
        self.admin_button.configure(text='Einrichtung durch Administratoren ' +
                                    ('verbergen' if self.admin_visible else 'anzeigen'))

    def settings_return(self):
        if self.current:
            self.dashboard(self.current)
        else:
            self.login()

    def download_veracrypt(self):
        if not webbrowser.open('https://veracrypt.io/en/Downloads.html'):
            self.error(UserError('Die Seite konnte nicht geöffnet werden. Bitte wende dich an die zuständige Person.'))

    def quit(self):
        if self.busy:
            self.root.bell()
            return
        if self.wizard and not messagebox.askokcancel('Speicherort',
                'Einrichtung abbrechen und Speicherort beenden?', parent=self.root):
            return
        if self.current and self.backend.mounted(self.current):
            if messagebox.askokcancel('Speicherort · Tresor sicher schließen',
                    'Speichere und schließe zuerst deine Dokumente und Ordnerfenster im Tresor. '
                    'Danach wird dein Tresor sicher geschlossen und Speicherort beendet.', parent=self.root):
                self.logout(exit_after=True)
            return
        self.finish_quit()

    def finish_quit(self):
        opened = [name for name in self.store.names() if self.backend.mounted(self.store.user(name))]
        if opened:
            messagebox.showinfo('Speicherort · Tresor noch geöffnet',
                                'Bitte zuerst diese Tresore auswählen, anmelden und sicher schließen:\n' +
                                ', '.join(opened), parent=self.root)
            self.current = None
            self.login()
            return
        self.destroy()

    def destroy(self):
        self.closed = True
        self.cancel_idle()
        self.wipe_wizard_secret()
        for field in self.password_fields:
            field.clear()
        if self.poll_id:
            self.root.after_cancel(self.poll_id)
        self.store.db.close()
        self.lock.close()
        self.root.destroy()


def main():
    try:
        root = tk.Tk()
    except tk.TclError:
        raise SystemExit('Speicherort konnte kein Fenster öffnen. Bitte in der grafischen '
                         'Linux-Sitzung starten und prüfen, ob Tkinter installiert ist.')
    try:
        App(root)
    except (OSError, sqlite3.Error, UserError):
        messagebox.showerror('Speicherort konnte nicht starten',
                             'Die lokalen Kontodaten konnten nicht geöffnet werden. '
                             'Bitte prüfe den freien Speicherplatz und wende dich an die '
                             'zuständige Person. Deine Tresordateien werden nicht verändert.', parent=root)
        root.destroy()
        raise SystemExit(1)
    root.mainloop()


if __name__ == '__main__':
    main()
