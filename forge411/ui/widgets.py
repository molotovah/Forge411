"""Composants d'interface réutilisables."""

import io
import logging
import queue
import re
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Callable, Optional

from . import theme as T

try:
    from PIL import Image, ImageDraw, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False


# ═══════════════════════════════════════════════════════════════════════════
# Exécution en arrière-plan
# ═══════════════════════════════════════════════════════════════════════════

class UI:
    """File d'appels vers le thread Tk (les threads n'y touchent jamais directement)."""

    _q: "queue.Queue[tuple]" = queue.Queue()
    _root: Optional[tk.Misc] = None

    @classmethod
    def install(cls, root: tk.Misc):
        cls._root = root
        cls._pump()

    @classmethod
    def _pump(cls):
        try:
            while True:
                fn, args = cls._q.get_nowait()
                try:
                    fn(*args)
                except Exception:  # une erreur d'affichage ne doit pas tuer la boucle
                    logging.exception("Erreur dans un rappel d'interface")
        except queue.Empty:
            pass
        if cls._root is not None:
            cls._root.after(40, cls._pump)

    @classmethod
    def call(cls, fn: Callable, *args):
        cls._q.put((fn, args))


def run_bg(fn: Callable, on_ok: Callable = None, on_err: Callable = None):
    """Exécute fn() dans un thread ; callbacks appelés dans le thread Tk."""
    def target():
        try:
            res = fn()
        except Exception as e:
            logging.warning("Tâche de fond : %r", e, exc_info=not on_err)
            if on_err:
                UI.call(on_err, e)
            return
        if on_ok:
            UI.call(on_ok, res)
    threading.Thread(target=target, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════
# Boutons
# ═══════════════════════════════════════════════════════════════════════════

class Btn(tk.Label):
    STYLES = {
        "primary": (T.ACCENT, T.ON_ACCENT, T.ACCENT_HOVER),
        "secondary": (T.SURFACE2, T.TEXT, T.HOVER),
        "ghost": (None, T.MUTED, T.SURFACE2),
        "danger": (T.ERROR_SOFT, T.ERROR, T.ERROR_HOVER),
        "success": (T.SUCCESS, T.ON_ACCENT, T.SUCCESS_HOVER),
    }

    def __init__(self, parent, text: str, command: Callable = None, kind: str = "secondary",
                 small: bool = False, width: int = None, **kw):
        self.kind = kind
        bg, fg, hover = self.STYLES[kind]
        self._parent_bg = parent.cget("bg") if "bg" in parent.keys() else T.BG
        self._bg = bg or self._parent_bg
        self._fg, self._hover = fg, hover
        self.command = command
        self.enabled = True
        pad = (10, 4) if small else (16, 8)
        super().__init__(parent, text=text, bg=self._bg, fg=fg, cursor="hand2",
                         font=T.F_SMALL_B if small else T.F_UI_B,
                         padx=pad[0], pady=pad[1], width=width or 0, **kw)
        self.bind("<Enter>", lambda e: self.enabled and self.configure(bg=self._hover))
        self.bind("<Leave>", lambda e: self.configure(bg=self._bg if self.enabled else T.SURFACE))
        self.bind("<ButtonRelease-1>", self._click)

    def _click(self, e):
        if not self.enabled or not self.command:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        if 0 <= e.x <= w and 0 <= e.y <= h:
            self.configure(bg=self._bg)       # sinon le survol reste affiché si une fenêtre s'ouvre par-dessus
            self.command()

    def set_enabled(self, on: bool):
        self.enabled = on
        self.configure(bg=self._bg if on else T.SURFACE, fg=self._fg if on else T.FAINT,
                       cursor="hand2" if on else "arrow")

    def set_text(self, text: str):
        self.configure(text=text)


# ═══════════════════════════════════════════════════════════════════════════
# Conteneurs
# ═══════════════════════════════════════════════════════════════════════════

class Card(tk.Frame):
    def __init__(self, parent, padding: int = 16, bg: str = T.SURFACE, **kw):
        super().__init__(parent, bg=bg, highlightbackground=T.BORDER,
                         highlightthickness=1, **kw)
        self.body = tk.Frame(self, bg=bg)
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)


class ScrollFrame(tk.Frame):
    """Cadre défilant verticalement ; la molette agit seulement au survol."""

    def __init__(self, parent, bg: str = T.BG, **kw):
        super().__init__(parent, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.bind_all("<MouseWheel>", self._wheel, add="+")

    def _on_scroll(self, lo, hi):
        if float(lo) <= 0 and float(hi) >= 1:
            self.vsb.pack_forget()
        elif not self.vsb.winfo_ismapped():
            self.vsb.pack(side="right", fill="y")
        self.vsb.set(lo, hi)

    def _wheel(self, e):
        w = e.widget
        if not isinstance(w, tk.Misc) or isinstance(w, (tk.Text, tk.Listbox)):
            return
        try:
            path = str(w)
        except Exception:
            return
        if path.startswith(str(self.canvas)) and self.vsb.winfo_ismapped():
            self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units")

    def to_top(self):
        self.canvas.yview_moveto(0)


class TextArea(tk.Frame):
    def __init__(self, parent, height: int = 20, mono: bool = True, readonly: bool = False, **kw):
        super().__init__(parent, bg=T.SURFACE2, highlightbackground=T.BORDER, highlightthickness=1)
        self.text = tk.Text(self, height=height, bg=T.SURFACE2, fg=T.TEXT, insertbackground=T.TEXT,
                            selectbackground=T.ACCENT, selectforeground=T.ON_ACCENT,
                            relief="flat", bd=0, padx=12, pady=10, wrap="none" if mono else "word",
                            font=T.F_MONO if mono else T.F_UI, undo=True, **kw)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=vsb.set)
        if mono:
            hsb = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
            self.text.configure(xscrollcommand=hsb.set)
            hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.readonly = readonly
        if readonly:
            self.text.configure(state="disabled")

    def get(self) -> str:
        return self.text.get("1.0", "end-1c")

    def set(self, value: str):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.edit_reset()
        self.text.edit_modified(False)
        if self.readonly:
            self.text.configure(state="disabled")


# ═══════════════════════════════════════════════════════════════════════════
# Petits éléments
# ═══════════════════════════════════════════════════════════════════════════

def label(parent, text="", fg=T.TEXT, font=T.F_UI, bg=None, **kw) -> tk.Label:
    return tk.Label(parent, text=text, fg=fg, font=font,
                    bg=bg or parent.cget("bg"), anchor="w", justify="left", **kw)


def wrap_check(parent, var, text: str, command=None, bg: str = None) -> tk.Frame:
    """Case à cocher dont le libellé passe à la ligne (le texte d'un ttk.Checkbutton serait coupé par la fenêtre).
    Un clic sur le libellé coche aussi la case."""
    bg = bg or T.SURFACE
    row = tk.Frame(parent, bg=bg)
    cb = ttk.Checkbutton(row, variable=var, style="Card.TCheckbutton", command=command)
    cb.pack(side="left", anchor="n")
    lbl = autowrap(label(row, text, bg=bg, cursor="hand2"))
    lbl.pack(side="left", fill="x", expand=True)
    lbl.bind("<Button-1>", lambda e: cb.invoke())
    row.check = cb
    return row


def wrap_name(lbl: tk.Label, text: str) -> tk.Label:
    """Nom de release sans espaces (Film.2024.1080p…) replié sur la largeur disponible, coupé après les points,
    tirets ou crochets : un Label Tk ne replie qu'aux espaces."""
    from tkinter import font as tkfont
    f = tkfont.Font(font=lbl.cget("font"))
    parts = re.findall(r"[^.\-\]]+[.\-\]]?|[.\-\]]", text)

    def flow(e=None):
        width = max(lbl.winfo_width() - 4, 60)
        lines, cur = [], ""
        for p in parts:
            if cur and f.measure(cur + p) > width:
                lines.append(cur)
                cur = p
            else:
                cur += p
        lines.append(cur)
        new = "\n".join(lines)
        if lbl.cget("text") != new:
            lbl.configure(text=new)
    lbl.configure(text=text, anchor="w", justify="left")
    lbl.bind("<Configure>", flow, add="+")
    return lbl


def style_tree(widget):
    """Thème des tableaux (ttk.Treeview) : lignes aérées, en-têtes discrets, sélection à la couleur d'accent."""
    s = ttk.Style(widget)
    s.configure("Treeview", background=T.SURFACE, fieldbackground=T.SURFACE, foreground=T.TEXT,
                rowheight=T.px(widget, 28), bordercolor=T.BORDER, borderwidth=0, font=T.F_UI)
    s.configure("Treeview.Heading", background=T.SURFACE2, foreground=T.MUTED, relief="flat", font=T.F_SMALL_B,
                padding=(8, 6))
    s.map("Treeview.Heading", background=[("active", T.HOVER)])
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])     # sans la bordure claire du thème
    s.map("Treeview", background=[("selected", T.ACCENT_SOFT)], foreground=[("selected", T.TEXT)])


def autowrap(lbl: tk.Label) -> tk.Label:
    """Le texte se replie sur la largeur réellement disponible."""
    lbl.bind("<Configure>", lambda e: lbl.configure(wraplength=max(e.width - 4, 40)))
    return lbl


def badge(parent, text: str, tone: str = "accent") -> tk.Label:
    colors = {"accent": (T.ACCENT_SOFT, T.ACCENT_HOVER), "success": (T.SUCCESS_SOFT, T.SUCCESS),
              "warning": (T.WARNING_SOFT, T.WARNING), "error": (T.ERROR_SOFT, T.ERROR),
              "muted": (T.SURFACE2, T.MUTED)}
    bg, fg = colors[tone]
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=T.F_SMALL_B, padx=8, pady=2)


class IssueList(tk.Frame):
    """Liste d'erreurs / avertissements / validations avec pictogrammes."""

    ICONS = {"error": ("✕", T.ERROR), "warning": ("!", T.WARNING), "ok": ("✓", T.SUCCESS),
             "info": ("i", T.ACCENT)}

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=parent.cget("bg"), **kw)

    def show(self, items: list[tuple[str, str]], wrap: int = 760):
        for w in self.winfo_children():
            w.destroy()
        for tone, msg in items:
            icon, color = self.ICONS[tone]
            row = tk.Frame(self, bg=self.cget("bg"))
            row.pack(fill="x", pady=2)
            tk.Label(row, text=icon, fg=color, bg=self.cget("bg"), font=T.F_UI_B,
                     width=2).pack(side="left", anchor="n")
            tk.Label(row, text=msg, fg=T.TEXT if tone != "ok" else T.MUTED, bg=self.cget("bg"),
                     font=T.F_UI, wraplength=wrap, justify="left", anchor="w").pack(
                side="left", fill="x", expand=True)


class Tooltip:
    """Bulle d'aide affichée au survol d'un widget."""

    _all = set()

    @classmethod
    def hide_all(cls):
        for t in list(cls._all):
            t._hide()

    def __init__(self, widget: tk.Misc, text: str, wrap: int = 340):
        self.widget, self.text, self.wrap = widget, text, wrap
        self.tip = None
        self._after = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _=None):
        self._cancel()
        self._after = self.widget.after(350, self._show)

    def _cancel(self):
        if self._after:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self):
        if self.tip or not self.text or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        frame = tk.Frame(tw, bg=T.BORDER)
        frame.pack()
        tk.Label(frame, text=self.text, bg=T.SURFACE2, fg=T.TEXT, font=T.F_SMALL, justify="left",
                 wraplength=self.wrap, padx=10, pady=7).pack(padx=1, pady=1)
        tw.update_idletasks()
        sw = self.widget.winfo_screenwidth()
        x = min(x, sw - tw.winfo_width() - 8)
        tw.wm_geometry(f"+{x}+{y}")
        Tooltip._all.add(self)

    def _hide(self, _=None):
        self._cancel()
        Tooltip._all.discard(self)
        if self.tip:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


def help_icon(parent, text: str) -> tk.Label:
    """Petit « ? » rond qui affiche une aide au survol."""
    lbl = tk.Label(parent, text="?", bg=T.SURFACE2, fg=T.MUTED, font=T.F_SMALL_B, width=2, cursor="question_arrow")
    Tooltip(lbl, text)
    return lbl


def link(parent, text: str, url: str, small: bool = True) -> tk.Label:
    lbl = tk.Label(parent, text=text + "  ↗", fg=T.ACCENT, bg=parent.cget("bg"), cursor="hand2",
                   font=T.F_SMALL_B if small else T.F_UI_B, anchor="w")
    lbl.bind("<Button-1>", lambda e: webbrowser.open(url))
    lbl.bind("<Enter>", lambda e: lbl.configure(fg=T.ACCENT_HOVER))
    lbl.bind("<Leave>", lambda e: lbl.configure(fg=T.ACCENT))
    Tooltip(lbl, url)
    return lbl


class Field(tk.Frame):
    """Libellé (+ aide au survol, + lien) et champ : saisie, liste ou texte multiligne."""

    def __init__(self, parent, text: str, var: tk.StringVar, values: list = None,
                 width: int = 24, readonly: bool = False, show: str = None, hint: str = "",
                 help: str = "", url: tuple = None, multiline: bool = False):
        super().__init__(parent, bg=parent.cget("bg"))
        head = tk.Frame(self, bg=self.cget("bg"))
        head.pack(fill="x")
        label(head, text, fg=T.MUTED, font=T.F_SMALL_B).pack(side="left")
        if help:
            help_icon(head, help).pack(side="left", padx=(6, 0))
        if url:
            link(head, url[0], url[1]).pack(side="right")
        if multiline:
            self.text = tk.Text(self, height=5, bg=T.SURFACE2, fg=T.TEXT, insertbackground=T.TEXT,
                                relief="flat", padx=8, pady=6, font=T.F_UI, wrap="word",
                                highlightthickness=1, highlightbackground=T.BORDER, highlightcolor=T.ACCENT)
            self.text.insert("1.0", var.get())
            self.text.pack(fill="x", pady=(3, 0))
            sync = lambda e=None: var.set(self.text.get("1.0", "end-1c"))
            self.text.bind("<KeyRelease>", sync)
            self.text.bind("<FocusOut>", sync)
            self.text.bind("<<Paste>>", lambda e: self.after(10, sync))
            self.input = self.text
        elif values is not None:
            self.input = ttk.Combobox(self, textvariable=var, values=values, width=width,
                                      state="readonly" if readonly else "normal")
            self.input.pack(fill="x", pady=(3, 0))
        else:
            self.input = ttk.Entry(self, textvariable=var, width=width, show=show or "")
            self.input.pack(fill="x", pady=(3, 0))
        if hint:
            autowrap(label(self, hint, fg=T.FAINT, font=T.F_SMALL)).pack(fill="x", pady=(2, 0))


# ═══════════════════════════════════════════════════════════════════════════
# Images
# ═══════════════════════════════════════════════════════════════════════════

class Images:
    """Cache d'affiches (PIL requis) ; les références Tk restent vivantes ici."""

    _raw: dict = {}
    _tk: dict = {}

    @classmethod
    def placeholder(cls, w: int, h: int):
        key = ("ph", w, h)
        if key not in cls._tk and PIL_OK:
            img = Image.new("RGB", (w, h), T.SURFACE2)
            d = ImageDraw.Draw(img)
            d.rectangle([0, 0, w - 1, h - 1], outline=T.BORDER)
            cls._tk[key] = ImageTk.PhotoImage(img)
        return cls._tk.get(key)

    @classmethod
    def load(cls, url: str, w: int, h: int, on_ready: Callable, cover: bool = True):
        """Charge une image distante, redimensionnée (recadrée si cover) ; on_ready(photo)."""
        if not PIL_OK or not url:
            return
        key = (url, w, h)
        if key in cls._tk:
            on_ready(cls._tk[key])
            return

        def work():
            if url not in cls._raw:
                from ..lookup import fetch_image
                cls._raw[url] = fetch_image(url)
            img = Image.open(io.BytesIO(cls._raw[url])).convert("RGB")
            if cover:
                from PIL import ImageOps
                img = ImageOps.fit(img, (w, h), Image.LANCZOS)
            else:
                img.thumbnail((w, h), Image.LANCZOS)
            return img

        def done(img):
            cls._tk[key] = ImageTk.PhotoImage(img)
            on_ready(cls._tk[key])
        run_bg(work, done, lambda e: None)


class Meter(tk.Canvas):
    """Jauge horizontale arrondie (0 à 1), redessinée à chaque redimensionnement."""

    def __init__(self, parent, value: float = 0.0, color: str = None, height: int = 8, track: str = None):
        bg = parent.cget("bg")
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self.value, self.color, self.track, self.h = value, color or T.ACCENT, track or T.SURFACE2, height
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value: float):
        self.value = value
        self._draw()

    def _bar(self, x0, x1, color):
        r = self.h / 2
        if x1 - x0 < self.h:
            x1 = x0 + self.h
        self.create_oval(x0, 0, x0 + self.h, self.h, fill=color, outline=color)
        self.create_oval(x1 - self.h, 0, x1, self.h, fill=color, outline=color)
        self.create_rectangle(x0 + r, 0, x1 - r, self.h, fill=color, outline=color)

    def _draw(self):
        self.delete("all")
        w = max(self.winfo_width(), self.h)
        self._bar(0, w, self.track)
        v = max(0.0, min(1.0, self.value or 0.0))
        if v > 0:
            self._bar(0, max(self.h, w * v), self.color)
