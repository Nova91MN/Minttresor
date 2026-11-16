"""Small, dependency-free Tk components shared by Speicherort's screens."""
import math
import tkinter as tk
from tkinter import font, ttk


COLORS = {
    'background': '#f3f7f4', 'surface': '#ffffff', 'ink': '#213c30',
    'muted': '#52665b', 'accent': '#256b4d', 'hover': '#195338',
    'mint': '#e4f2e9', 'border': '#c5d3ca', 'focus': '#136545',
    'error': '#8f2e26', 'error_bg': '#fff0ed',
}


def configure_theme(root):
    fallback = font.nametofont('TkDefaultFont').actual('family')
    family = next((name for name in ('Noto Sans', 'DejaVu Sans', 'Liberation Sans')
                   if name in font.families(root)), fallback)
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont'):
        font.nametofont(name).configure(family=family, size=11)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=(family, 11), background=COLORS['background'],
                    foreground=COLORS['ink'])
    for prefix, color in (('', COLORS['background']), ('Card.', COLORS['surface']),
                          ('Mint.', COLORS['mint']), ('Error.', COLORS['error_bg'])):
        style.configure(prefix + 'TFrame', background=color)
        style.configure(prefix + 'TLabel', background=color)
    for prefix, size, weight, color in (
        ('Title.', 23, 'bold', COLORS['ink']),
        ('Heading.', 15, 'bold', COLORS['ink']),
        ('Brand.', 14, 'bold', COLORS['ink']),
        ('Muted.', 11, 'normal', COLORS['muted']),
        ('Small.', 10, 'normal', COLORS['muted']),
        ('Step.', 10, 'bold', COLORS['accent']),
    ):
        style.configure(prefix + 'TLabel', font=(family, size, weight), foreground=color)
        style.configure(prefix + 'Card.TLabel', font=(family, size, weight),
                        foreground=color, background=COLORS['surface'])
    style.configure('Error.TLabel', foreground=COLORS['error'])
    style.configure('ErrorTitle.TLabel', font=(family, 12, 'bold'),
                    foreground=COLORS['error'], background=COLORS['error_bg'])
    style.configure('TButton', padding=(18, 12), borderwidth=1,
                    background=COLORS['surface'], foreground=COLORS['ink'],
                    bordercolor=COLORS['border'], focuscolor=COLORS['focus'],
                    focusthickness=2)
    style.map('TButton', background=[('disabled', '#e7ece8'), ('active', COLORS['mint'])],
              foreground=[('disabled', '#5c6b62')],
              bordercolor=[('focus', COLORS['focus'])])
    style.configure('Primary.TButton', background=COLORS['accent'], foreground='white',
                    font=(family, 11, 'bold'), bordercolor=COLORS['accent'], focuscolor='white')
    style.map('Primary.TButton', background=[('disabled', '#d7e2da'),
                                            ('active', COLORS['hover'])],
              foreground=[('disabled', '#52665b'), ('!disabled', 'white')])
    style.configure('Quiet.TButton', background=COLORS['background'], padding=(12, 8))
    style.configure('User.TButton', anchor='w', padding=(18, 16),
                    font=(family, 12, 'bold'))
    style.configure('TEntry', padding=(10, 10), fieldbackground=COLORS['surface'],
                    bordercolor=COLORS['border'], insertcolor=COLORS['ink'])
    style.map('TEntry', bordercolor=[('focus', COLORS['focus'])])
    style.configure('TSpinbox', padding=(10, 10), fieldbackground=COLORS['surface'],
                    arrowsize=22)
    style.configure('TCheckbutton', padding=(0, 9), focuscolor=COLORS['focus'])
    style.configure('Card.TCheckbutton', background=COLORS['surface'])
    style.map('Card.TCheckbutton', background=[('active', COLORS['surface'])])
    style.configure('Horizontal.TProgressbar', background=COLORS['accent'],
                    troughcolor=COLORS['mint'], borderwidth=0)
    root.configure(background=COLORS['background'])


def icon(root, kind='lock', size=64):
    """Rasterize simple decorative symbols without emoji fonts or image libraries."""
    picture = tk.PhotoImage(master=root, width=size, height=size)
    for y in range(size):
        row = []
        for x in range(size):
            nx, ny = x / size, y / size
            color = COLORS['surface']
            if math.hypot(nx - .5, ny - .5) < .49:
                color = COLORS['mint']
            if kind == 'person':
                shape = math.hypot(nx - .5, ny - .34) < .115 or (
                    ((nx - .5) / .23) ** 2 + ((ny - .73) / .23) ** 2 < 1 and ny < .77)
            else:
                center = .56 if kind == 'open' else .5
                ring = .15 < math.hypot(nx - center, ny - .37) < .205 and ny < .45
                legs = .30 < nx < .36 and .36 < ny < .52
                shape = ring or legs or (.28 < nx < .72 and .45 < ny < .76)
            if shape:
                color = COLORS['accent']
            if kind != 'person' and .48 < nx < .52 and .55 < ny < .66:
                color = COLORS['surface']
            row.append(color)
        picture.put('{' + ' '.join(row) + '}', to=(0, y))
    return picture


class ScrollPage:
    """A centered, responsive page; focused controls are scrolled into view."""
    def __init__(self, parent, scale=1):
        self.scale = scale
        self.wraps = []
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(self.frame, background=COLORS['background'],
                                highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self.frame, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window(0, 0, anchor='nw', window=self.body)
        self.canvas.bind('<Configure>', self.resize)
        self.body.bind('<Configure>', self.region)

    def region(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def resize(self, event):
        margin = int(24 * self.scale)
        width = max(100, min(int(720 * self.scale), event.width - 2 * margin))
        self.canvas.coords(self.window, max(margin, (event.width - width) // 2), int(26 * self.scale))
        self.canvas.itemconfigure(self.window, width=width)
        style = ttk.Style(self.frame)
        style.configure('TButton', wraplength=max(80, width - int(90 * self.scale)))
        style.configure('User.TButton', wraplength=max(80, width - int(120 * self.scale)),
                        justify='left')
        for label, inset in self.wraps:
            if label.winfo_exists():
                label.configure(wraplength=max(80, width - int(inset * self.scale)))
        self.region()

    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.wraps.clear()
        self.canvas.yview_moveto(0)

    def label(self, parent, text='', style='TLabel', inset=0, **kwargs):
        label = ttk.Label(parent, text=text, style=style, wraplength=600,
                          justify='left', **kwargs)
        self.wraps.append((label, inset))
        return label

    def reveal(self, widget):
        ancestor = widget
        while ancestor is not None and ancestor is not self.body:
            ancestor = getattr(ancestor, 'master', None)
        if ancestor is None:
            return
        self.canvas.update_idletasks()
        top = widget.winfo_rooty() - self.body.winfo_rooty() + int(26 * self.scale)
        bottom = top + widget.winfo_height()
        visible_top = self.canvas.canvasy(0)
        height = self.canvas.winfo_height()
        total = max(1, self.body.winfo_height() + int(26 * self.scale))
        if top < visible_top:
            self.canvas.yview_moveto(max(0, top - 12) / total)
        elif bottom > visible_top + height:
            self.canvas.yview_moveto((bottom - height + 16) / total)


class PasswordField:
    """Explicit visibility, automatically hidden on blur, timeout and navigation."""
    def __init__(self, parent, label, scale=1):
        self.frame = ttk.Frame(parent, style='Card.TFrame')
        self.frame.pack(fill='x', pady=(8, 0))
        ttk.Label(self.frame, text=label, style='Card.TLabel').pack(anchor='w', pady=(0, 5))
        self.value = tk.StringVar()
        self.entry = ttk.Entry(self.frame, textvariable=self.value, show='•')
        self.entry.pack(fill='x')
        self.visible = tk.BooleanVar(value=False)
        self.toggle = ttk.Checkbutton(self.frame, text='Passwort anzeigen',
                                      variable=self.visible, command=self.change,
                                      style='Card.TCheckbutton')
        self.toggle.pack(anchor='w')
        self.timer = None
        self.blur_timer = None
        self.entry.bind('<FocusOut>', self.blur)
        self.toggle.bind('<FocusOut>', self.blur)
        self.frame.bind('<Destroy>', self.destroyed)

    def blur(self, event=None):
        if self.blur_timer:
            self.frame.after_cancel(self.blur_timer)
        self.blur_timer = self.frame.after_idle(self.hide_if_outside)

    def hide_if_outside(self):
        self.blur_timer = None
        if self.frame.winfo_exists() and self.frame.focus_get() not in (self.entry, self.toggle):
            self.hide()

    def change(self):
        if self.visible.get():
            self.entry.configure(show='')
            self.toggle.configure(text='Passwort verbergen')
            if self.timer:
                self.frame.after_cancel(self.timer)
            self.timer = self.frame.after(10000, self.hide)
        else:
            self.hide()

    def hide(self):
        if self.timer:
            self.frame.after_cancel(self.timer)
            self.timer = None
        self.visible.set(False)
        self.entry.configure(show='•')
        self.toggle.configure(text='Passwort anzeigen')

    def clear(self):
        self.hide()
        self.value.set('')

    def destroyed(self, event):
        if event.widget is self.frame:
            if self.blur_timer:
                self.frame.after_cancel(self.blur_timer)
                self.blur_timer = None
            if self.timer:
                self.frame.after_cancel(self.timer)
                self.timer = None
            self.value.set('')
