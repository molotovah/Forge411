"""Visite guidée : bulles qui pointent les zones de l'interface, une par une."""

import tkinter as tk

from . import theme as T
from .widgets import Btn, label


class Tour:
    def __init__(self, app, steps: list, on_done=None):
        """steps : [(fonction renvoyant le widget cible, titre, texte)]."""
        self.app, self.steps, self.on_done = app, steps, on_done
        self.i = 0
        self.bubble = None
        self.frames = []

    def start(self):
        self.app.update_idletasks()
        self.show()

    def _clear(self):
        if self.bubble:
            self.bubble.destroy()
            self.bubble = None
        for f in self.frames:
            f.destroy()
        self.frames = []

    def _highlight(self, w):
        x = w.winfo_rootx() - self.app.winfo_rootx()
        y = w.winfo_rooty() - self.app.winfo_rooty()
        ww, hh, t = w.winfo_width(), w.winfo_height(), 3
        for (fx, fy, fw, fh) in ((x - t, y - t, ww + 2 * t, t), (x - t, y + hh, ww + 2 * t, t),
                                 (x - t, y, t, hh), (x + ww, y, t, hh)):
            f = tk.Frame(self.app, bg=T.ACCENT)
            f.place(x=fx, y=fy, width=fw, height=fh)
            f.lift()
            self.frames.append(f)

    def show(self):
        self._clear()
        if self.i >= len(self.steps):
            self.finish()
            return
        target_fn, title, text = self.steps[self.i]
        w = target_fn()
        if w is None or not w.winfo_ismapped():
            self.i += 1
            self.show()
            return
        self._highlight(w)
        b = self.bubble = tk.Toplevel(self.app)
        b.wm_overrideredirect(True)
        b.attributes("-topmost", True)
        outer = tk.Frame(b, bg=T.ACCENT)
        outer.pack()
        body = tk.Frame(outer, bg=T.SURFACE)
        body.pack(padx=2, pady=2)
        inner = tk.Frame(body, bg=T.SURFACE)
        inner.pack(padx=18, pady=16)
        label(inner, f"{self.i + 1} / {len(self.steps)}", fg=T.ACCENT, font=T.F_SMALL_B).pack(fill="x")
        label(inner, title, font=T.F_H2).pack(fill="x", pady=(4, 0))
        label(inner, text, fg=T.MUTED, wraplength=320).pack(fill="x", pady=(6, 14))
        row = tk.Frame(inner, bg=T.SURFACE)
        row.pack(fill="x")
        Btn(row, "Passer la visite", self.finish, kind="ghost", small=True).pack(side="left")
        last = self.i == len(self.steps) - 1
        Btn(row, "Terminer" if last else "Suivant  →", self.next, kind="primary", small=True).pack(side="right")
        if self.i:
            Btn(row, "←", self.prev, small=True).pack(side="right", padx=(0, 6))
        b.update_idletasks()
        bw, bh = b.winfo_width(), b.winfo_height()
        sx, sy = w.winfo_rootx(), w.winfo_rooty()
        ax, ay = self.app.winfo_rootx(), self.app.winfo_rooty()
        aw, ah = self.app.winfo_width(), self.app.winfo_height()
        if sx + w.winfo_width() + 16 + bw < ax + aw:            # à droite
            x, y = sx + w.winfo_width() + 16, sy
        elif sy + w.winfo_height() + 16 + bh < ay + ah:         # en dessous
            x, y = sx, sy + w.winfo_height() + 16
        else:                                                   # au-dessus
            x, y = sx + w.winfo_width() - bw, sy - bh - 16
        x = max(ax + 8, min(x, ax + aw - bw - 8))
        y = max(ay + 8, min(y, ay + ah - bh - 8))
        b.wm_geometry(f"+{x}+{y}")
        b.bind("<Escape>", lambda e: self.finish())
        b.focus_force()

    def next(self):
        self.i += 1
        self.show()

    def prev(self):
        self.i = max(0, self.i - 1)
        self.show()

    def finish(self):
        self._clear()
        if self.on_done:
            self.on_done()
