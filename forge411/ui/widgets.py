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

from ..model import fmt_size
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

# ── Formes arrondies (style C411) ─────────────────────────────────────────
# Tk ne sait pas arrondir un cadre : les quatre coins sont des images anticrénelées (Pillow, sur-échantillonnage
# x4, transparentes donc valables sur tout fond), mises en cache par rayon et couleurs ; les côtés sont des
# rectangles et des traits du canevas. Sans Pillow : coins droits.

_CORNERS: dict = {}
_FONTS: dict = {}


def _font(spec):
    """Police Tk mise en cache (mesure du texte des boutons sans recréer d'objet à chaque bouton)."""
    f = _FONTS.get(spec)
    if f is None:
        import tkinter.font as tkfont
        f = _FONTS[spec] = tkfont.Font(font=spec)
    return f


def _corners(r: int, fill: str, outline: Optional[str]):
    key = (r, fill, outline)
    if key in _CORNERS:
        return _CORNERS[key]
    k = 4
    big = Image.new("RGBA", (2 * r * k, 2 * r * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    if outline:
        d.ellipse([0, 0, 2 * r * k - 1, 2 * r * k - 1], fill=outline)
        d.ellipse([k, k, 2 * r * k - 1 - k, 2 * r * k - 1 - k], fill=fill)
    else:
        d.ellipse([0, 0, 2 * r * k - 1, 2 * r * k - 1], fill=fill)
    img = big.resize((2 * r, 2 * r), Image.LANCZOS)
    parts = {"nw": (0, 0, r, r), "ne": (r, 0, 2 * r, r), "sw": (0, r, r, 2 * r), "se": (r, r, 2 * r, 2 * r)}
    out = _CORNERS[key] = {a: ImageTk.PhotoImage(img.crop(box)) for a, box in parts.items()}
    return out


def round_rect(cv: tk.Canvas, w: int, h: int, r: int, fill: Optional[str], outline: Optional[str] = None,
               tag: str = "shape"):
    """Rectangle arrondi plein (et liseré d'un pixel) couvrant [0, w) x [0, h) du canevas, sous le reste."""
    cv.delete(tag)
    if not fill or w < 2 or h < 2:
        return
    r = max(0, min(r, w // 2, h // 2))
    if r < 2 or not PIL_OK:
        cv.create_rectangle(0, 0, w - 1, h - 1, fill=fill, outline=outline or fill, tags=tag)
        cv.tag_lower(tag)
        return
    c = _corners(r, fill, outline)
    cv.create_rectangle(r, 0, w - r, h, fill=fill, width=0, tags=tag)
    cv.create_rectangle(0, r, w, h - r, fill=fill, width=0, tags=tag)
    for anchor, x, y in (("nw", 0, 0), ("ne", w, 0), ("sw", 0, h), ("se", w, h)):
        cv.create_image(x, y, image=c[anchor], anchor=anchor, tags=tag)
    if outline:
        for x0, y0, x1, y1 in ((r, 0, w - r, 0), (r, h - 1, w - r, h - 1), (0, r, 0, h - r),
                               (w - 1, r, w - 1, h - r)):
            cv.create_line(x0, y0, x1, y1, fill=outline, tags=tag)
    cv.tag_lower(tag)


def _parent_bg(parent) -> str:
    try:
        return parent.cget("bg")
    except tk.TclError:
        return T.BG


class Btn(tk.Canvas):
    """Bouton arrondi (rayon 6, comme sur C411). Même interface qu'avant : set_enabled, set_text, command."""

    STYLES = {
        "primary": (T.ACCENT, T.ON_ACCENT, T.ACCENT_HOVER),
        "secondary": (T.SURFACE2, T.TEXT, T.HOVER),
        "ghost": (None, T.MUTED, T.SURFACE2),
        "danger": (T.ERROR_SOFT, T.ERROR, T.ERROR_HOVER),
        "success": (T.SUCCESS, T.ON_ACCENT, T.SUCCESS_HOVER),
        "soft": (T.ACCENT_SOFT, T.ACCENT, T.HOVER),
    }

    def __init__(self, parent, text: str, command: Callable = None, kind: str = "secondary",
                 small: bool = False, width: int = None, **kw):
        super().__init__(parent, bg=_parent_bg(parent), highlightthickness=0, bd=0, cursor="hand2", **kw)
        self.kind = kind
        self._bg, self._fg, self._hover = self.STYLES[kind]
        self.command = command
        self.enabled = True
        self._hovered = False
        self._spec = T.F_SMALL_B if small else T.F_UI_B
        self._padx, self._pady = T.px(self, 12 if small else 16), T.px(self, 5 if small else 8)
        self._r = T.px(self, 6)
        self._chars = width
        self._text = self.create_text(0, 0, text=text, fill=self._fg, font=self._spec, anchor="center")
        self._fit()
        self.bind("<Configure>", lambda e: self._paint(), add="+")
        self.bind("<Enter>", lambda e: self._set_hover(True), add="+")
        self.bind("<Leave>", lambda e: self._set_hover(False), add="+")
        self.bind("<ButtonRelease-1>", self._click, add="+")

    def _fit(self):
        f = _font(self._spec)
        tw = f.measure(self.itemcget(self._text, "text"))
        if self._chars:
            tw = max(tw, f.measure("0") * self._chars)
        self.configure(width=tw + 2 * self._padx, height=f.metrics("linespace") + 2 * self._pady)
        self._paint()

    def _paint(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:                                   # pas encore affiché : taille demandée
            w, h = int(self.cget("width")), int(self.cget("height"))
        if not self.enabled:
            fill, fg = (T.SURFACE2 if self._bg else None), T.FAINT
        else:
            fill, fg = (self._hover if self._hovered else self._bg), self._fg
        round_rect(self, w, h, self._r, fill)
        self.coords(self._text, w / 2, h / 2)
        self.itemconfigure(self._text, fill=fg)

    def _set_hover(self, on: bool):
        self._hovered = on and self.enabled
        self._paint()

    def _click(self, e):
        if not self.enabled or not self.command:
            return
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self._set_hover(False)        # sinon le survol reste affiché si une fenêtre s'ouvre par-dessus
            self.command()

    def set_enabled(self, on: bool):
        if on == self.enabled:
            return
        self.enabled = on
        self._hovered = False
        self.configure(cursor="hand2" if on else "arrow")
        self._paint()

    def set_text(self, text: str):
        if text != self.itemcget(self._text, "text"):
            self.itemconfigure(self._text, text=text)
            self._fit()


# ═══════════════════════════════════════════════════════════════════════════
# Conteneurs
# ═══════════════════════════════════════════════════════════════════════════

class Card(tk.Canvas):
    """Encadré arrondi (rayon 10, liseré d'un pixel). Le contenu va dans .body, qui fixe la hauteur ; la
    largeur suit celle donnée à l'encadré (pack fill="x", grid sticky…)."""

    def __init__(self, parent, padding: int = 16, bg: str = T.SURFACE, border: Optional[str] = T.BORDER,
                 radius: int = 10, **kw):
        super().__init__(parent, bg=_parent_bg(parent), highlightthickness=0, bd=0, width=1, height=1, **kw)
        self.fill, self.border = bg, border
        self._r = T.px(self, radius)
        # marge minimale : le contenu (rectangle) ne doit pas recouvrir l'arrondi ni le liseré
        self._pad = max(T.px(self, padding), int(self._r * 0.3) + 1)
        self.body = tk.Frame(self, bg=bg)
        self._win = self.create_window(self._pad, self._pad, window=self.body, anchor="nw")
        self._size = (0, 0)
        self.body.bind("<Configure>", lambda e: self._fit(), add="+")
        self.bind("<Configure>", self._resized, add="+")
        # Un canevas masque une fenêtre intégrée hors de sa zone visible : tant que l'encadré mesure 1 px, le
        # contenu n'est jamais affiché, donc jamais mesuré. Premier ajustement une fois le contenu construit.
        self.after_idle(self._fit)

    def _fit(self):
        """La hauteur suit le contenu. La largeur demandée ne fait que grandir : la laisser aussi rétrécir boucle
        avec les textes repliés (largeur → repli → largeur demandée → largeur de la fenêtre → …)."""
        if not self.winfo_exists():
            return
        h = self.body.winfo_reqheight() + 2 * self._pad
        if int(self.cget("height")) != h:
            self.configure(height=h)
        w = self.body.winfo_reqwidth() + 2 * self._pad
        if w > int(self.cget("width")):
            self.configure(width=w)

    def fit_now(self):
        """Ajuste tout de suite la taille au contenu (sinon fait à l'inactivité) : à appeler avant de mesurer
        une fenêtre pour la positionner (bulle de la visite guidée)."""
        self.update_idletasks()
        self._fit()
        self.update_idletasks()

    def _resized(self, e):
        if (e.width, e.height) == self._size:
            return
        if e.width != self._size[0]:
            self.itemconfigure(self._win, width=max(e.width - 2 * self._pad, 1))
        self._size = (e.width, e.height)
        round_rect(self, e.width, e.height, self._r, self.fill, self.border)

    def set_colors(self, fill: str = None, border: str = None):
        """Change le fond et/ou le liseré (survol, sélection)."""
        if fill:
            self.fill = fill
            self.body.configure(bg=fill)
        if border:
            self.border = border
        if self._size != (0, 0):
            round_rect(self, *self._size, self._r, self.fill, self.border)


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
        root = self.winfo_toplevel().nametowidget(".")
        if not getattr(root, "_forge_wheel", False):      # un seul gestionnaire global, quel que soit le nombre
            root._forge_wheel = True                      # de zones défilantes ouvertes depuis le lancement
            self.bind_all("<MouseWheel>", ScrollFrame._dispatch, add="+")

    @staticmethod
    def _dispatch(e):
        """Molette : fait défiler la zone défilante la plus proche du widget survolé qui peut défiler (une zone
        imbriquée sans barre de défilement laisse la main à celle qui la contient)."""
        w = e.widget
        if not isinstance(w, tk.Misc) or isinstance(w, (tk.Text, tk.Listbox)):
            return
        while w is not None:
            if isinstance(w, ScrollFrame) and w._wheel(e):
                return
            w = getattr(w, "master", None)

    def _on_scroll(self, lo, hi):
        if float(lo) <= 0 and float(hi) >= 1:
            self.vsb.pack_forget()
        elif not self.vsb.winfo_ismapped():
            self.vsb.pack(side="right", fill="y")
        self.vsb.set(lo, hi)

    def _wheel(self, e) -> bool:
        try:
            if self.vsb.winfo_ismapped():
                self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units")
                return True
        except tk.TclError:                 # zone détruite entre-temps
            pass
        return False

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
    f = _font(lbl.cget("font"))
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
    """Le texte se replie sur la largeur réellement disponible. Repli initial à 320 px en attendant la vraie
    largeur : sinon le libellé réclame d'abord tout son texte sur une ligne, et un encadré arrondi (qui ne
    rétrécit pas, voir Card) garderait cette largeur, au-delà de la fenêtre."""
    if str(lbl.cget("wraplength")) in ("0", ""):
        lbl.configure(wraplength=T.px(lbl, 320))
    lbl.bind("<Configure>", lambda e: lbl.configure(wraplength=max(e.width - 4, 40)))
    return lbl


class badge(tk.Canvas):
    """Pastille arrondie (type, statut…). Interface d'un libellé : configure(text=…) reste possible."""

    COLORS = {"accent": (T.ACCENT_SOFT, T.ACCENT_HOVER), "success": (T.SUCCESS_SOFT, T.SUCCESS),
              "warning": (T.WARNING_SOFT, T.WARNING), "error": (T.ERROR_SOFT, T.ERROR),
              "muted": (T.SURFACE2, T.MUTED)}

    def __init__(self, parent, text: str, tone: str = "accent"):
        super().__init__(parent, bg=_parent_bg(parent), highlightthickness=0, bd=0)
        self.fill, fg = self.COLORS[tone]
        self._t = self.create_text(0, 0, text=text, fill=fg, font=T.F_SMALL_B, anchor="center")
        self._fit()

    def _fit(self):
        f = _font(T.F_SMALL_B)
        w = f.measure(self.itemcget(self._t, "text")) + 2 * T.px(self, 9)
        h = f.metrics("linespace") + 2 * T.px(self, 2)
        self.configure(width=w, height=h)
        round_rect(self, w, h, h // 2, self.fill)
        self.coords(self._t, w / 2, h / 2)

    def configure(self, cnf=None, **kw):
        text = kw.pop("text", None)
        res = super().configure(cnf, **kw) if (cnf or kw) else None
        if text is not None:
            self.itemconfigure(self._t, text=text)
            self._fit()
        return res

    config = configure


class IssueList(tk.Frame):
    """Liste d'erreurs / avertissements / validations avec pictogrammes."""

    ICONS = {"error": ("✕", T.ERROR), "warning": ("!", T.WARNING), "ok": ("✓", T.SUCCESS),
             "info": ("i", T.ACCENT)}

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=parent.cget("bg"), **kw)

    def show(self, items: list[tuple[str, str]], wrap: int = 760):
        key = (tuple(items), wrap)
        if key == getattr(self, "_shown", None):      # rien de changé : pas de reconstruction
            return
        self._shown = key
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


class SpeedChart(tk.Canvas):
    """Courbe de vitesse (aire + trait) et vitesse moyenne en pointillé. Au plus `points` points : au-delà,
    les mesures voisines sont fusionnées deux à deux (coût constant, quelle que soit la durée). Une ligne et
    une aire réutilisées (coords) : moins d'une milliseconde par mise à jour."""

    def __init__(self, parent, height: int = 64, points: int = 150):
        bg = _parent_bg(parent)
        super().__init__(parent, height=T.px(parent, height), bg=bg, highlightthickness=0, bd=0)
        self.points = points
        self._area = self.create_polygon(0, 0, 0, 0, 0, 0, fill=T.ACCENT_SOFT, outline="")
        self._avg = self.create_line(0, 0, 0, 0, fill=T.MUTED, dash=(3, 3))
        self._line = self.create_line(0, 0, 0, 0, fill=T.ACCENT, width=2)
        self._max = self.create_text(0, 0, text="", fill=T.FAINT, font=T.F_SMALL, anchor="ne")
        self.reset()
        self.bind("<Configure>", lambda e: self._draw())

    def reset(self):
        self.vals: list = []          # vitesse par point (moyenne des mesures fusionnées)
        self._weight: list = []
        self._step = 1                # mesures par point
        self._pending = (0.0, 0)
        self.average = 0.0
        self._draw()

    def add(self, speed: float, average: float = 0.0):
        tot, n = self._pending
        tot, n = tot + speed, n + 1
        if n < self._step:
            self._pending = (tot, n)
        else:
            self._pending = (0.0, 0)
            self.vals.append(tot / n)
            if len(self.vals) >= 2 * self.points:          # deux fois trop de points : fusion deux à deux
                self.vals = [(a + b) / 2 for a, b in zip(self.vals[::2], self.vals[1::2])]
                self._step *= 2
        self.average = average
        self._draw()

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or len(self.vals) < 2:
            for item in (self._area, self._line, self._avg):
                self.coords(item, 0, 0, 0, 0)
            self.itemconfigure(self._max, text="")
            return
        top = max(max(self.vals), self.average) or 1
        head, pad = T.px(self, 16), 2                # bande du haut réservée à « max … »
        span = h - head - pad
        dx = (w - 1) / (len(self.vals) - 1)
        xy = []
        for i, v in enumerate(self.vals):
            xy += (i * dx, h - pad - v / top * span)
        self.coords(self._line, *xy)
        self.coords(self._area, 0, h, *xy, w - 1, h)
        if self.average:
            y = h - pad - self.average / top * span
            self.coords(self._avg, 0, y, w, y)
        self.coords(self._max, w - 2, 0)
        self.itemconfigure(self._max, text=f"max {fmt_size(int(top))}/s")


class StatsPanel(tk.Frame):
    """Rangée de tuiles « libellé / valeur » (vitesse, temps restant…) sous une barre de progression, et en
    option la courbe de vitesse."""

    def __init__(self, parent, fields: list[tuple[str, str]], chart: bool = False):
        super().__init__(parent, bg=parent.cget("bg"))
        self.values: dict[str, tk.Label] = {}
        for col, (key, caption) in enumerate(fields):
            card = Card(self, padding=10, bg=T.SURFACE2, border=None, radius=8)
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else T.px(self, 8), 0))
            self.columnconfigure(col, weight=1, uniform="tile")
            tile = card.body
            tk.Label(tile, text=caption.upper(), bg=T.SURFACE2, fg=T.FAINT, font=T.F_SMALL_B,
                     anchor="w").pack(fill="x")
            v = tk.Label(tile, text="…", bg=T.SURFACE2, fg=T.TEXT, font=T.F_H2, anchor="w")
            v.pack(fill="x")
            self.values[key] = v
        self.chart = None
        if chart:
            box = self._chart_box = Card(self, padding=8, bg=T.SURFACE2, border=None, radius=8)
            box.grid(row=1, column=0, columnspan=len(fields), sticky="ew", pady=(T.px(self, 8), 0))
            box.grid_remove()                        # affichée à la première mesure
            self.chart = SpeedChart(box.body)
            self.chart.pack(fill="x")
        self.note = tk.Label(self, text="", bg=self.cget("bg"), fg=T.MUTED, font=T.F_SMALL, anchor="w",
                             justify="left")
        self.note.grid(row=2, column=0, columnspan=len(fields), sticky="ew", pady=(T.px(self, 6), 0))

    def set(self, key: str, text: str, color: str = None):
        self.values[key].configure(text=text, fg=color or T.TEXT)

    def plot(self, speed: float, average: float = 0.0):
        if self.chart is not None:
            if not self._chart_box.winfo_ismapped():
                self._chart_box.grid()
            self.chart.add(speed, average)

    def finish(self):
        """Fin de l'opération : courbe masquée si elle n'a reçu aucune mesure (opération quasi instantanée)."""
        if self.chart is not None and len(self.chart.vals) < 2:
            self._chart_box.grid_remove()

    def reset(self):
        for v in self.values.values():
            v.configure(text="…", fg=T.TEXT)
        self.note.configure(text="")
        if self.chart is not None:
            self.chart.reset()


def reveal(path) -> None:
    """Ouvre l'explorateur sur un fichier (sélectionné) ou un dossier."""
    import subprocess
    import sys
    from pathlib import Path
    path = Path(path)
    if sys.platform == "win32":
        if path.is_dir():
            subprocess.Popen(["explorer", str(path)])
        else:
            subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        webbrowser.open((path if path.is_dir() else path.parent).as_uri())
